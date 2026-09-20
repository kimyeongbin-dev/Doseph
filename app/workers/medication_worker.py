"""Medication batch worker module.

Handles automatic expiry and deletion of prescriptions at 00:10 KST.

Two passes:
  1. end_date < today AND is_active=True             → is_active=False
  2. expiration_date < today - MEDICATION_PURGE_GRACE_DAYS → 행을 물리 삭제

이 배치는 **사용자가 누르지 않았는데 행을 지우는 유일한 경로**다. 그래서 만료
즉시가 아니라 유예기간이 지난 뒤에 지운다(QA-29, 기본 7일).

경위:
    QA-01(2026-09-15) 전에는 pass 2 가 ``deleted_at=now()`` 로 장부만 남기는
    soft delete 였다. 그 장부는 FK CASCADE 에 한 줄 뒤에서 덮이는 반쪽이었고,
    삭제 의미론을 hard delete 로 통일하며 **실제 삭제**가 됐다. 되돌릴 수단이
    0 이 됐으므로 QA-29 가 유예기간을 얹었다.

    유예는 **새 상태(컬럼)를 만들지 않고 날짜 산술로만** 표현한다 — 지울 시점을
    미루는 것이지 "지워진 척하는 행"을 만드는 것이 아니다. 후자가 QA-01 의
    형태였다. 자세한 비교는 ``docs-private/study/2026-09-15_tombstone-and-staged-deletion-study.md``.

    ⚠️ 유예는 **복구가 아니다.** 사용자가 되살릴 버튼은 없고, 삭제가 늦게 올 뿐이다.
"""

from datetime import date, datetime, timedelta
import logging

from app.core import config
from app.models.medication import Medication

logger = logging.getLogger(__name__)


# ── pass 1: 복용 종료일이 지난 복약 비활성화 ──────────────────────────
# 흐름: end_date < today 인 활성 행 조회 -> is_active=False 로 저장
async def _deactivate_ended_medications(today: date) -> int:
    """Deactivate medications whose ``end_date`` has passed.

    Args:
        today: Reference date (KST).

    Returns:
        Number of deactivated medications.
    """
    expired_active = await Medication.filter(
        is_active=True,
        end_date__lt=today,
        end_date__isnull=False,
    ).all()

    for medication in expired_active:
        medication.is_active = False
        await medication.save()

    return len(expired_active)


# ── pass 2: 유예기간이 끝난 복약 물리 삭제 ────────────────────────────
# 흐름: 삭제 기준일 계산(today - 유예일수) -> 그보다 먼저 만료된 행 DELETE
#       -> 자식(intake_logs)은 FK CASCADE 가 함께 정리
# 유예 중인 행은 "만료됐지만 아직 지우지 않은" 상태로 그대로 남는다.
async def _delete_expired_medications(today: date) -> tuple[int, date]:
    """Delete medications whose grace period after expiry has ended.

    Args:
        today: Reference date (KST).

    Returns:
        Deleted row count and the cutoff date used.
    """
    cutoff = today - timedelta(days=config.MEDICATION_PURGE_GRACE_DAYS)
    deleted = await Medication.filter(
        expiration_date__lt=cutoff,
        expiration_date__isnull=False,
    ).delete()
    return deleted, cutoff


# ── 만료 복약 정리 배치 ───────────────────────────────────────────────
# 흐름: end_date 지난 것 비활성화 -> expiration_date 지난 것 물리 삭제
# 매일 00:10 KST 실행. 삭제된 행의 자식은 FK CASCADE 가 함께 정리한다.
async def expire_medications(today: date | None = None) -> None:
    """Deactivate and delete expired medications.

    Pass 1: Medications whose end_date is in the past are deactivated.
    Pass 2: Medications whose expiration_date is in the past are deleted.

    Args:
        today: Reference date. Defaults to today in KST. 주입 가능하게 둔 것은
            테스트가 자정 경계에 흔들리지 않게 하기 위함이다.
    """
    if today is None:
        today = datetime.now(tz=config.TIMEZONE).date()

    deactivated_count = await _deactivate_ended_medications(today)
    deleted_count, cutoff = await _delete_expired_medications(today)

    # 삭제 영수증(tombstone) — 무엇이 몇 건 사라졌는지만 남긴다.
    # ⚠️ 약품명·프로필 등 개인정보는 넣지 않는다(로깅 규칙 §9-4). 개인정보를 넣으면
    #    그건 영수증이 아니라 백업이고, "지웠다"는 말이 거짓이 된다.
    logger.info(
        "expire_medications completed: date=%s deactivated=%d deleted=%d reason=batch_expiry grace_days=%d cutoff=%s",
        today,
        deactivated_count,
        deleted_count,
        config.MEDICATION_PURGE_GRACE_DAYS,
        cutoff,
    )

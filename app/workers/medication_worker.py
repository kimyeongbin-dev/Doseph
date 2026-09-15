"""Medication batch worker module.

Handles automatic expiry and deletion of prescriptions at 00:10 KST.

Two passes:
  1. end_date < today AND is_active=True  → is_active=False
  2. expiration_date < today              → 행을 물리 삭제

⚠️ 2026-09-15(QA-01): pass 2 는 ``deleted_at=now()`` 로 장부만 남기던 soft delete
였는데, 삭제 의미론이 hard delete 로 통일되면서 **실제 삭제**로 바뀌었다.
배치가 사용자 데이터를 되돌릴 수 없게 지우므로, 유예기간을 두는 설계는
후속 QA-29(단계적 삭제)에서 이 지점을 첫 번째로 다룬다.
"""

from datetime import datetime
import logging

from app.core import config
from app.models.medication import Medication

logger = logging.getLogger(__name__)


# ── 만료 복약 정리 배치 ───────────────────────────────────────────────
# 흐름: end_date 지난 것 비활성화 -> expiration_date 지난 것 물리 삭제
# 매일 00:10 KST 실행. 삭제된 행의 자식은 FK CASCADE 가 함께 정리한다.
async def expire_medications() -> None:
    """Deactivate and delete expired medications.

    Pass 1: Medications whose end_date is in the past are deactivated.
    Pass 2: Medications whose expiration_date is in the past are deleted.
    """
    today = datetime.now(tz=config.TIMEZONE).date()

    # Pass 1: deactivate medications past end_date
    expired_active = await Medication.filter(
        is_active=True,
        end_date__lt=today,
        end_date__isnull=False,
    ).all()

    deactivated_count = 0
    for medication in expired_active:
        medication.is_active = False
        await medication.save()
        deactivated_count += 1

    # Pass 2: delete medications past expiration_date
    deleted_count = await Medication.filter(
        expiration_date__lt=today,
        expiration_date__isnull=False,
    ).delete()

    logger.info(
        "expire_medications completed: date=%s deactivated=%d deleted=%d",
        today,
        deactivated_count,
        deleted_count,
    )

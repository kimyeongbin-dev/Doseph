"""만료 복약 정리 배치의 유예기간 계약 (QA-29).

이 배치는 **사용자가 누르지 않았는데 행을 지운다.** 매일 00:10 KST 에 돌고,
지워진 복약의 ``intake_logs`` 는 FK CASCADE 로 함께 사라진다. QA-01 로 삭제가
물리 삭제로 통일되면서 되돌릴 방법이 0 이 됐으므로, **유예기간**을 둔다.

계약:
    expiration_date < (today - GRACE_DAYS) 인 행만 지운다.

왜 mock 이 아니라 진짜 DB 인가:
    mock 은 "어떤 kwargs 로 filter 를 불렀는가"만 본다. 부호를 거꾸로 써도
    (``today + 7``) mock 단언은 통과시킬 수 있고, 무엇보다 **행이 남았는지**를
    못 본다. 유예기간은 "안 지워졌다"가 전부인 기능이라 행으로 확인해야 한다.

⚠️ 날짜는 ``expire_medications(today=...)`` 로 **주입**한다. 실행 시각에 의존하면
자정 근처에서 흔들린다(QA-09 freezegun 미착수).
"""

from datetime import date, timedelta

import pytest

from app.core import config
from app.models.medication import Medication
from app.tests.db.conftest import create_account, create_medication, create_profile
from app.workers.medication_worker import expire_medications

pytestmark = [pytest.mark.db, pytest.mark.asyncio(loop_scope="session")]

#: 기준일 — 주입하므로 실제 오늘과 무관하다.
TODAY = date(2026, 9, 15)

#: 유예일수를 **리터럴로** 적는다. ``config.MEDICATION_PURGE_GRACE_DAYS`` 를 참조하면
#: 테스트가 구현과 같은 값을 보게 되어 상수를 바꿔도 함께 움직인다 — 경계가
#: 어긋나도 영원히 초록인 구현복사 테스트(V-G)가 된다. 실제로 결핍 주입
#: (유예 0일)에서 이 테스트들이 무감각한 것이 드러나 리터럴로 바꿨다.
#: 기본값을 바꾸려면 이 숫자도 함께 바꿔야 한다 — **그 마찰이 의도된 것**이다.
GRACE_DAYS = 7

#: 다른 테스트 데이터와 절대 겹치지 않는 이름. 화면/픽스처의 흔한 문자열과
#: 겹치면 "무엇을 세고 있는지" 가 흐려진다(헛된 초록 V-B 예방).
SENTINEL = "유예검증정_QX7"


async def _make_expired_medication(days_ago: int) -> Medication:
    """``days_ago`` 일 전에 유효기간이 끝난 복약 1건을 만든다.

    Args:
        days_ago: 유효기간 만료 후 경과 일수.

    Returns:
        생성된 Medication.
    """
    account = await create_account()
    profile = await create_profile(account)
    return await create_medication(
        profile,
        medicine_name=SENTINEL,
        expiration_date=TODAY - timedelta(days=days_ago),
    )


# ── 기본 유예일수 계약 ────────────────────────────────────────────────
# 흐름: config 기본값이 이 파일의 GRACE_DAYS 와 같은지 확인
def test_default_grace_period_is_seven_days() -> None:
    """기본 유예일수는 7일이다.

    위 경계 테스트들이 리터럴 7 을 쓰므로, 기본값이 조용히 바뀌면 그 테스트들이
    **엉뚱한 경계를 검증하게 된다.** 여기서 둘을 묶어 둔다.
    """
    assert config.MEDICATION_PURGE_GRACE_DAYS == GRACE_DAYS


# ── 유예 중에는 지우지 않는다 ─────────────────────────────────────────
# 흐름: 어제 만료된 행 생성 -> 배치 실행 -> 행이 그대로 있어야 한다
async def test_recently_expired_medication_survives_grace_period(db: None) -> None:
    """유효기간이 막 지난 복약은 아직 지워지지 않는다."""
    medication = await _make_expired_medication(days_ago=1)

    await expire_medications(today=TODAY)

    assert await Medication.filter(id=medication.id).exists(), "만료 직후에 지워졌다 — 유예기간이 적용되지 않았다"


# ── 유예 경계: 마지막 날까지는 살아 있다 ──────────────────────────────
# 흐름: 정확히 GRACE_DAYS 일 전 만료 -> 배치 -> 아직 살아 있어야 한다
async def test_medication_on_last_grace_day_survives(db: None) -> None:
    """경계일(만료 후 정확히 7일)에는 아직 남아 있다."""
    medication = await _make_expired_medication(days_ago=GRACE_DAYS)

    await expire_medications(today=TODAY)

    assert await Medication.filter(id=medication.id).exists(), (
        f"유예 {GRACE_DAYS}일째에 지워졌다 — 경계가 하루 어긋났다"
    )


# ── 유예가 끝나면 지운다 ──────────────────────────────────────────────
# 흐름: GRACE_DAYS + 1 일 전 만료 -> 배치 -> 행이 사라져야 한다
async def test_medication_past_grace_period_is_deleted(db: None) -> None:
    """유예기간을 넘긴 복약은 물리 삭제된다."""
    medication = await _make_expired_medication(days_ago=GRACE_DAYS + 1)

    await expire_medications(today=TODAY)

    assert not await Medication.filter(id=medication.id).exists(), (
        "유예가 끝났는데도 남아 있다 — 배치가 아무것도 지우지 않는다"
    )


# ── 유효기간이 없는 복약은 배치 대상이 아니다 ─────────────────────────
# 흐름: expiration_date=None 생성 -> 배치 -> 영향받지 않아야 한다
async def test_medication_without_expiration_date_is_never_deleted(db: None) -> None:
    """``expiration_date`` 가 없으면 이 배치는 손대지 않는다.

    OCR 이 유효기간을 못 읽은 처방이 여기 해당한다. 기준이 없는 행을
    "언젠가" 지우기 시작하면 사용자는 이유를 알 수 없다.
    """
    account = await create_account()
    profile = await create_profile(account)
    medication = await create_medication(profile, medicine_name=SENTINEL, expiration_date=None)

    await expire_medications(today=TODAY)

    assert await Medication.filter(id=medication.id).exists(), "유효기간이 없는 복약이 지워졌다 — 기준 없는 삭제다"


# ── pass 1 은 유예와 무관하다 ─────────────────────────────────────────
# 흐름: end_date 지난 활성 복약 -> 배치 -> is_active 만 꺼지고 행은 남는다
async def test_ended_medication_is_deactivated_not_deleted(db: None) -> None:
    """복용 종료(pass 1)는 **비활성화일 뿐** 삭제가 아니다.

    pass 1 과 pass 2 는 **다른 컬럼**을 본다(end_date vs expiration_date).
    유예를 넣으면서 둘이 섞이지 않았는지 여기서 잠근다.
    """
    account = await create_account()
    profile = await create_profile(account)
    medication = await create_medication(
        profile,
        medicine_name=SENTINEL,
        end_date=TODAY - timedelta(days=1),
        expiration_date=None,
        is_active=True,
    )

    await expire_medications(today=TODAY)

    refreshed = await Medication.filter(id=medication.id).first()
    assert refreshed is not None, "복용이 끝났다고 행을 지우면 안 된다"
    assert refreshed.is_active is False, "복용 종료일이 지났는데 활성 상태로 남았다"

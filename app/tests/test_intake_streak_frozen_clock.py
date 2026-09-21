"""`IntakeLogService.get_streak` 를 **고정된 시계 위에서** 검증한다 (B-8 S2 · QA-09).

착수 전 실측(2026-09-21): `streak` 을 검증하는 테스트가 **0건**이었다.
유일한 등장은 다른 파일(`test_db_guide_delete_impact.py`)의 **docstring** 안이었다.

왜 시계를 고정하나
------------------
`get_streak` 은 ``datetime.now(tz=config.TIMEZONE).date()`` 를 **함수 안에서** 읽는다.
시계를 고정하지 않으면 *"연속 3일"* 같은 규칙을 **표현할 방법 자체가 없다** —
테스트가 오늘이 며칠인지 모르기 때문이다. 그래서 이 도메인의 핵심 규칙
(스트릭·챌린지 완료 판정·TTL)이 전부 검증 밖에 있었다.

``real_asyncio=True`` 를 쓰는 이유
----------------------------------
freezegun 이 ``time.monotonic()`` 까지 얼리면 **asyncio 이벤트 루프가 깨진다**.
이 옵션은 루프에만 실제 monotonic 시간을 보여 준다(freezegun 1.5.5 문서).

🔴 이 파일이 잠그는 것 중 하나는 **시간대(KST)** 다
---------------------------------------------------
`TestTimezoneBoundary` 는 **UTC 로는 어제, KST 로는 오늘**인 순간에 시계를 세운다.
코드가 `config.TIMEZONE` 을 안 쓰고 UTC 로 날짜를 뽑으면 **그 테스트만 빨개진다.**
이건 가설이 아니라 **자정 근처에 실제로 났을 flaky** 를 결정적으로 바꾼 것이다.
"""

from datetime import date, timedelta
from uuid import UUID, uuid4

from freezegun import freeze_time
import pytest

from app.services.intake_log_service import IntakeLogService

# ── 공용 헬퍼 ──────────────────────────────────────────────────────────


class _FakeIntakeLogRepository:
    """`get_taken_dates_by_profile` 만 돌려주는 대역.

    `unittest.mock` 을 쓰지 않는 이유 — 이 테스트가 보는 것은 **날짜 산술**이고,
    대역이 돌려줄 값은 `set[date]` 하나로 충분하다. 실물 타입을 그대로 쓰면
    반환 모양이 어긋날 때 **테스트가 아니라 타입 검사가 먼저 잡는다.**
    """

    def __init__(self, taken: set[date]) -> None:
        self._taken = taken

    async def get_taken_dates_by_profile(self, profile_id: UUID) -> set[date]:
        return self._taken


def _service(taken: set[date]) -> IntakeLogService:
    """저장소만 대역으로 바꾼 서비스. 나머지 협력자는 이 경로에서 안 쓰인다."""
    service = IntakeLogService()
    service.repository = _FakeIntakeLogRepository(taken)  # type: ignore[assignment]
    return service


_FROZEN = "2026-09-21 09:00:00+09:00"  # KST 기준 2026-09-21 오전 9시
_TODAY = date(2026, 9, 21)


def _days_back(*offsets: int) -> set[date]:
    """오늘로부터 n일 전 날짜 집합. 테스트가 «며칠 전»을 그대로 읽히게 한다."""
    return {_TODAY - timedelta(days=n) for n in offsets}


# ── 연속 일수 계산 ─────────────────────────────────────────────────────
# 흐름: 오늘 기록 유무로 시작점 결정 -> 하루씩 뒤로 가며 연속 카운트


class TestStreakCounting:
    @freeze_time(_FROZEN, real_asyncio=True)
    @pytest.mark.asyncio
    async def test_three_consecutive_days_including_today(self) -> None:
        """착수 전에는 이 규칙을 **표현할 방법이 없었다** — 오늘이 며칠인지 몰라서다."""
        service = _service(_days_back(0, 1, 2))

        assert await service.get_streak(uuid4()) == 3

    @freeze_time(_FROZEN, real_asyncio=True)
    @pytest.mark.asyncio
    async def test_streak_counts_from_yesterday_when_today_is_empty(self) -> None:
        """오늘 아직 안 먹었다고 어제까지의 연속이 깨지진 않는다(docstring 계약)."""
        service = _service(_days_back(1, 2))

        assert await service.get_streak(uuid4()) == 2

    @freeze_time(_FROZEN, real_asyncio=True)
    @pytest.mark.asyncio
    async def test_gap_breaks_the_streak(self) -> None:
        service = _service(_days_back(0, 2, 3))

        assert await service.get_streak(uuid4()) == 1, "그제·그끄제가 있어도 어제가 비면 끊긴다"

    @freeze_time(_FROZEN, real_asyncio=True)
    @pytest.mark.asyncio
    async def test_no_records_is_zero(self) -> None:
        service = _service(set())

        assert await service.get_streak(uuid4()) == 0

    @freeze_time(_FROZEN, real_asyncio=True)
    @pytest.mark.asyncio
    async def test_neither_today_nor_yesterday_is_zero(self) -> None:
        """그제까지만 먹었으면 연속은 **0** 이다 — 시작점이 어제인데 어제가 비었다."""
        service = _service(_days_back(2, 3, 4))

        assert await service.get_streak(uuid4()) == 0


# ── 🔴 시간대 경계 ─────────────────────────────────────────────────────
# 흐름: UTC 로는 어제인 순간에 시계를 세우고, KST 날짜로 판정되는지 본다


class TestTimezoneBoundary:
    @freeze_time("2026-09-21 15:30:00+00:00", real_asyncio=True)
    @pytest.mark.asyncio
    async def test_date_is_resolved_in_kst_not_utc(self) -> None:
        """UTC 2026-09-21 15:30 = **KST 2026-09-22 00:30**.

        `config.TIMEZONE`(Asia/Seoul)을 쓰므로 «오늘» 은 **9/22** 여야 한다.
        코드가 UTC 로 날짜를 뽑으면 «오늘» 이 9/21 이 되어 이 단언이 깨진다.
        자정 직후 실행에서 조용히 틀렸을 값을 **결정적으로** 바꾼 지점이다.
        """
        service = _service({date(2026, 9, 22)})

        assert await service.get_streak(uuid4()) == 1, "KST 로 9/22 이므로 오늘이 연속에 들어간다"

    @freeze_time("2026-09-21 14:30:00+00:00", real_asyncio=True)
    @pytest.mark.asyncio
    async def test_one_hour_earlier_is_still_the_previous_kst_day(self) -> None:
        """음성 대조 — UTC 14:30 = KST 23:30 이라 «오늘» 은 아직 **9/21** 이다.

        위 테스트가 *시간대를 실제로 보고 있다* 는 것을 이 짝이 증명한다.
        둘 다 통과해야 «KST 로 판정한다» 가 성립한다.
        """
        service = _service({date(2026, 9, 21)})

        assert await service.get_streak(uuid4()) == 1, "KST 로 아직 9/21 이다"

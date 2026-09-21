"""ChallengeService.complete_day_with_owner_check 동작 테스트 (⑤-3④).

체크오프는 서버가 단독 관리한다: 소유권 검증 후 오늘 날짜를 멱등하게 추가하고
target_days 도달 시 COMPLETED 로 전환. 클라이언트가 완료 날짜·진행 상태를 직접
보내던 경로(구 generic PATCH)를 대체해 완료/스트릭 위조를 차단한다.
"""

from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from fastapi import HTTPException
from freezegun import freeze_time
import pytest

from app.services.challenge_service import ChallengeService


def _challenge(owner_account_id, *, completed_dates: list[str], target_days: int) -> MagicMock:
    """소유 계정·완료 날짜·목표일수를 갖춘 Challenge mock 생성."""
    challenge = MagicMock()
    challenge.profile = MagicMock()
    challenge.profile.account_id = owner_account_id
    challenge.completed_dates = completed_dates
    challenge.target_days = target_days
    challenge.fetch_related = AsyncMock()
    return challenge


class TestCompleteDayWithOwnerCheck:
    """POST /challenges/{id}/check 가 호출하는 서비스 경로."""

    @pytest.mark.asyncio
    async def test_appends_today_and_stays_in_progress(self) -> None:
        account_id = uuid4()
        challenge = _challenge(account_id, completed_dates=[], target_days=7)
        service = ChallengeService()
        with (
            patch.object(service.repository, "get_by_id", new=AsyncMock(return_value=challenge)),
            patch.object(service.repository, "update", new=AsyncMock(return_value=challenge)) as mock_update,
        ):
            await service.complete_day_with_owner_check(uuid4(), account_id, completed_date=date(2026, 9, 12))

        _, kwargs = mock_update.call_args
        assert kwargs["completed_dates"] == ["2026-09-12"]
        # 목표 미달 → 상태는 건드리지 않는다.
        assert "challenge_status" not in kwargs

    @pytest.mark.asyncio
    async def test_auto_completes_when_target_reached(self) -> None:
        account_id = uuid4()
        challenge = _challenge(account_id, completed_dates=["2026-09-10", "2026-09-11"], target_days=3)
        service = ChallengeService()
        with (
            patch.object(service.repository, "get_by_id", new=AsyncMock(return_value=challenge)),
            patch.object(service.repository, "update", new=AsyncMock(return_value=challenge)) as mock_update,
        ):
            await service.complete_day_with_owner_check(uuid4(), account_id, completed_date=date(2026, 9, 12))

        _, kwargs = mock_update.call_args
        assert kwargs["challenge_status"] == "COMPLETED"
        assert len(kwargs["completed_dates"]) == 3

    @pytest.mark.asyncio
    async def test_idempotent_on_same_day(self) -> None:
        account_id = uuid4()
        challenge = _challenge(account_id, completed_dates=["2026-09-12"], target_days=7)
        service = ChallengeService()
        with (
            patch.object(service.repository, "get_by_id", new=AsyncMock(return_value=challenge)),
            patch.object(service.repository, "update", new=AsyncMock(return_value=challenge)) as mock_update,
        ):
            await service.complete_day_with_owner_check(uuid4(), account_id, completed_date=date(2026, 9, 12))

        _, kwargs = mock_update.call_args
        # 같은 날 재호출 → 중복 추가 없음.
        assert kwargs["completed_dates"] == ["2026-09-12"]

    @pytest.mark.asyncio
    async def test_raises_403_when_owner_mismatch(self) -> None:
        other_account_id = uuid4()
        challenge = _challenge(other_account_id, completed_dates=[], target_days=7)
        service = ChallengeService()
        with (
            patch.object(service.repository, "get_by_id", new=AsyncMock(return_value=challenge)),
            pytest.raises(HTTPException) as exc_info,
        ):
            await service.complete_day_with_owner_check(uuid4(), uuid4(), completed_date=date(2026, 9, 12))
        assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    async def test_raises_404_when_challenge_missing(self) -> None:
        service = ChallengeService()
        with (
            patch.object(service.repository, "get_by_id", new=AsyncMock(return_value=None)),
            pytest.raises(HTTPException) as exc_info,
        ):
            await service.complete_day_with_owner_check(uuid4(), uuid4())
        assert exc_info.value.status_code == 404


# ── 🔴 서버가 «오늘» 을 정하는 분기 (B-8 S2 · QA-09) ──────────────────
# 흐름: completed_date 생략 -> datetime.now(tz=KST).date() -> 멱등 추가 -> 목표 판정


class TestServerDecidesTheDate:
    """`completed_date` 를 **생략했을 때** 서버가 고르는 날짜를 잠근다.

    🔴 착수 전 실측(2026-09-21): 위 5개 테스트는 **전부 `completed_date` 를 명시**해서
    부른다. 즉 이 모듈의 존재 이유인 *"서버가 날짜를 결정한다"*(모듈 docstring) 의
    **바로 그 분기가 한 번도 실행되지 않았다.** 날짜를 넘겨 주면 `datetime.now(...)` 는
    건너뛰기 때문이다 — 시계를 고정할 수단이 없어서 생긴 공백이다.

    ⚠️ `test_appends_today_and_stays_in_progress` 는 이름에 *today* 가 들어 있지만
    실제로는 `2026-09-12` 를 건네준다. **이름이 검증 범위를 과장**하고 있었다.
    """

    @freeze_time("2026-09-21 09:00:00+09:00", real_asyncio=True)
    @pytest.mark.asyncio
    async def test_omitted_date_defaults_to_today_in_kst(self) -> None:
        account_id = uuid4()
        challenge = _challenge(account_id, completed_dates=[], target_days=7)
        service = ChallengeService()
        with (
            patch.object(service.repository, "get_by_id", new=AsyncMock(return_value=challenge)),
            patch.object(service.repository, "update", new=AsyncMock(return_value=challenge)) as mock_update,
        ):
            await service.complete_day_with_owner_check(uuid4(), account_id)

        _, kwargs = mock_update.call_args
        assert kwargs["completed_dates"] == ["2026-09-21"], "서버가 오늘(KST)을 골라야 한다"

    @freeze_time("2026-09-21 15:30:00+00:00", real_asyncio=True)
    @pytest.mark.asyncio
    async def test_date_is_resolved_in_kst_not_utc(self) -> None:
        """UTC 2026-09-21 15:30 = **KST 2026-09-22 00:30**.

        자정 직후에 체크한 사용자가 **전날로 기록되지 않는다**는 계약이다.
        코드가 UTC 로 날짜를 뽑으면 `2026-09-21` 이 들어가 이 단언이 깨진다.
        """
        account_id = uuid4()
        challenge = _challenge(account_id, completed_dates=[], target_days=7)
        service = ChallengeService()
        with (
            patch.object(service.repository, "get_by_id", new=AsyncMock(return_value=challenge)),
            patch.object(service.repository, "update", new=AsyncMock(return_value=challenge)) as mock_update,
        ):
            await service.complete_day_with_owner_check(uuid4(), account_id)

        _, kwargs = mock_update.call_args
        assert kwargs["completed_dates"] == ["2026-09-22"], "KST 로 이미 9/22 다"

    @freeze_time("2026-09-21 09:00:00+09:00", real_asyncio=True)
    @pytest.mark.asyncio
    async def test_omitted_date_is_idempotent_on_same_day(self) -> None:
        account_id = uuid4()
        challenge = _challenge(account_id, completed_dates=["2026-09-21"], target_days=7)
        service = ChallengeService()
        with (
            patch.object(service.repository, "get_by_id", new=AsyncMock(return_value=challenge)),
            patch.object(service.repository, "update", new=AsyncMock(return_value=challenge)) as mock_update,
        ):
            await service.complete_day_with_owner_check(uuid4(), account_id)

        _, kwargs = mock_update.call_args
        assert kwargs["completed_dates"] == ["2026-09-21"], "같은 날 재호출은 중복 추가 없음"

    @freeze_time("2026-09-21 09:00:00+09:00", real_asyncio=True)
    @pytest.mark.asyncio
    async def test_today_can_complete_the_target(self) -> None:
        account_id = uuid4()
        challenge = _challenge(account_id, completed_dates=["2026-09-19", "2026-09-20"], target_days=3)
        service = ChallengeService()
        with (
            patch.object(service.repository, "get_by_id", new=AsyncMock(return_value=challenge)),
            patch.object(service.repository, "update", new=AsyncMock(return_value=challenge)) as mock_update,
        ):
            await service.complete_day_with_owner_check(uuid4(), account_id)

        _, kwargs = mock_update.call_args
        assert kwargs["completed_dates"] == ["2026-09-19", "2026-09-20", "2026-09-21"]
        assert kwargs["challenge_status"] == "COMPLETED"

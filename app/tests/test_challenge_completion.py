"""ChallengeService.complete_day_with_owner_check 동작 테스트 (⑤-3④).

체크오프는 서버가 단독 관리한다: 소유권 검증 후 오늘 날짜를 멱등하게 추가하고
target_days 도달 시 COMPLETED 로 전환. 클라이언트가 완료 날짜·진행 상태를 직접
보내던 경로(구 generic PATCH)를 대체해 완료/스트릭 위조를 차단한다.
"""

from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from fastapi import HTTPException
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

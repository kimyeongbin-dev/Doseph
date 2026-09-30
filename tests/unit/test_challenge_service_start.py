"""Unit tests for ChallengeService.start_challenge_with_owner_check().

Tests verify that activating a challenge sets is_active=True and records
the started_at timestamp, and that ownership is correctly enforced.

All tests are RED until the method is implemented.
"""

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

from fastapi import HTTPException
import pytest

from app.services.challenge_service import ChallengeService

# ── Helpers ────────────────────────────────────────────────────────────────


def _make_profile(account_id=None):
  """Build a minimal mock Profile."""
  p = MagicMock()
  p.id = uuid4()
  p.account_id = account_id or uuid4()
  return p


def _make_challenge(profile=None):
  """Build a minimal mock Challenge."""
  c = MagicMock()
  c.id = uuid4()
  c.is_active = False
  c.started_at = None
  c.profile = profile or _make_profile()
  c.fetch_related = AsyncMock()
  return c


# ── Fixture ────────────────────────────────────────────────────────────────


@pytest.fixture
def service() -> ChallengeService:
  """ChallengeService with all external dependencies mocked."""
  svc = ChallengeService.__new__(ChallengeService)
  svc.repository = AsyncMock()
  svc.profile_repository = AsyncMock()
  return svc


# ── start_challenge_with_owner_check ──────────────────────────────────────


async def test_start_challenge_sets_is_active(
  service: ChallengeService,
) -> None:
  """start_challenge_with_owner_check은 is_active=True로 갱신해야 한다."""
  account_id = uuid4()
  profile = _make_profile(account_id=account_id)
  challenge = _make_challenge(profile=profile)
  updated = MagicMock()
  updated.is_active = True

  service.repository.get_by_id = AsyncMock(return_value=challenge)
  service.repository.update = AsyncMock(return_value=updated)

  result = await service.start_challenge_with_owner_check(challenge.id, account_id)

  assert result is updated
  call_kwargs = service.repository.update.call_args.kwargs
  assert call_kwargs["is_active"] is True


async def test_start_challenge_sets_started_at(
  service: ChallengeService,
) -> None:
  """start_challenge_with_owner_check은 started_at을 현재 시각으로 설정해야 한다."""
  account_id = uuid4()
  profile = _make_profile(account_id=account_id)
  challenge = _make_challenge(profile=profile)
  updated = MagicMock()

  service.repository.get_by_id = AsyncMock(return_value=challenge)
  service.repository.update = AsyncMock(return_value=updated)

  await service.start_challenge_with_owner_check(challenge.id, account_id)

  call_kwargs = service.repository.update.call_args.kwargs
  assert "started_at" in call_kwargs
  assert call_kwargs["started_at"] is not None


async def test_start_challenge_not_found(
  service: ChallengeService,
) -> None:
  """챌린지가 존재하지 않으면 HTTP 404를 발생시켜야 한다."""
  service.repository.get_by_id = AsyncMock(return_value=None)

  with pytest.raises(HTTPException) as exc_info:
    await service.start_challenge_with_owner_check(uuid4(), uuid4())

  assert exc_info.value.status_code == 404


async def test_start_challenge_forbidden(
  service: ChallengeService,
) -> None:
  """다른 계정의 챌린지이면 HTTP 403을 발생시켜야 한다."""
  profile = _make_profile(account_id=uuid4())  # different account
  challenge = _make_challenge(profile=profile)

  service.repository.get_by_id = AsyncMock(return_value=challenge)
  # fetch_related is called inside _verify_challenge_ownership — make it a no-op
  challenge.fetch_related = AsyncMock()

  with pytest.raises(HTTPException) as exc_info:
    await service.start_challenge_with_owner_check(challenge.id, uuid4())

  assert exc_info.value.status_code == 403

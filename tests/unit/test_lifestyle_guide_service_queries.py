"""Unit tests for LifestyleGuideService ownership-check query methods.

Tests cover:
- generate_guide_with_owner_check
- get_guide_with_owner_check
- get_latest_guide_with_owner_check
- list_guides_with_owner_check
- get_guide_challenges_with_owner_check

All tests are RED until the methods are implemented.
"""

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

from fastapi import HTTPException
import pytest

from app.services.lifestyle_guide_service import LifestyleGuideService

# ── Helpers ────────────────────────────────────────────────────────────────


def _make_profile(account_id=None):
    """Build a minimal mock Profile."""
    p = MagicMock()
    p.id = uuid4()
    p.account_id = account_id or uuid4()
    return p


def _make_guide(profile_id=None):
    """Build a minimal mock LifestyleGuide."""
    g = MagicMock()
    g.id = uuid4()
    g.profile_id = profile_id or uuid4()
    return g


def _make_challenge():
    """Build a minimal mock Challenge."""
    c = MagicMock()
    c.id = uuid4()
    return c


# ── Fixture ────────────────────────────────────────────────────────────────


@pytest.fixture
def service() -> LifestyleGuideService:
    """LifestyleGuideService with all external dependencies mocked."""
    svc = LifestyleGuideService.__new__(LifestyleGuideService)
    svc.medication_repo = AsyncMock()
    svc.guide_repo = AsyncMock()
    svc.challenge_repo = AsyncMock()
    svc.llm_client = AsyncMock()
    svc.profile_repo = AsyncMock()
    return svc


# ── enqueue_guide_with_owner_check ────────────────────────────────────────
# ⚠️ 2026-09-15 재작성(QA-27): `generate_guide_with_owner_check` 는 가이드 생성이
#    큐 기반으로 재설계되면서 `enqueue_guide_with_owner_check` 로 바뀌었다.
#    이 파일이 CI 에서 돌지 않아 옛 이름을 향한 채 4개월 반 빨간 상태였다.
#
# 이 래퍼의 책임은 **소유권 게이트 + 위임** 둘뿐이다. 실제 생성 흐름(dedupe·pending·enqueue)은
# test_lifestyle_guide_service.py 가 잠근다. 그래서 여기서는 내부를 대역으로 두고
# "막을 것을 막는가 / 통과시킨 뒤 그대로 넘기는가"만 본다.


async def test_enqueue_guide_with_owner_check_delegates_when_owned(
    service: LifestyleGuideService,
) -> None:
    """소유자면 enqueue_guide_generation 에 그대로 위임하고 결과를 돌려준다."""
    account_id = uuid4()
    profile = _make_profile(account_id=account_id)
    group_id = uuid4()
    expected = _make_guide(profile_id=profile.id)

    service.profile_repo.get_by_id = AsyncMock(return_value=profile)
    service.enqueue_guide_generation = AsyncMock(return_value=expected)

    result = await service.enqueue_guide_with_owner_check(profile.id, group_id, account_id)

    assert result is expected
    service.enqueue_guide_generation.assert_awaited_once_with(profile.id, group_id)


async def test_enqueue_guide_with_owner_check_profile_not_found(
    service: LifestyleGuideService,
) -> None:
    """프로필이 존재하지 않으면 404 — 위임까지 가지 않는다."""
    service.profile_repo.get_by_id = AsyncMock(return_value=None)
    service.enqueue_guide_generation = AsyncMock()

    with pytest.raises(HTTPException) as exc_info:
        await service.enqueue_guide_with_owner_check(uuid4(), uuid4(), uuid4())

    assert exc_info.value.status_code == 404
    service.enqueue_guide_generation.assert_not_awaited()


async def test_enqueue_guide_with_owner_check_forbidden(
    service: LifestyleGuideService,
) -> None:
    """남의 프로필이면 403 — 게이트가 실제로 막는지 위임 미발생으로도 확인한다."""
    profile = _make_profile(account_id=uuid4())  # different account
    service.profile_repo.get_by_id = AsyncMock(return_value=profile)
    service.enqueue_guide_generation = AsyncMock()

    with pytest.raises(HTTPException) as exc_info:
        await service.enqueue_guide_with_owner_check(profile.id, uuid4(), uuid4())

    assert exc_info.value.status_code == 403
    service.enqueue_guide_generation.assert_not_awaited()


# ── get_guide_with_owner_check ─────────────────────────────────────────────


async def test_get_guide_with_owner_check_success(
    service: LifestyleGuideService,
) -> None:
    """가이드와 소유권 확인 후 가이드를 반환해야 한다."""
    account_id = uuid4()
    profile = _make_profile(account_id=account_id)
    guide = _make_guide(profile_id=profile.id)

    service.guide_repo.get_by_id = AsyncMock(return_value=guide)
    service.profile_repo.get_by_id = AsyncMock(return_value=profile)

    result = await service.get_guide_with_owner_check(guide.id, account_id)

    assert result is guide


async def test_get_guide_with_owner_check_guide_not_found(
    service: LifestyleGuideService,
) -> None:
    """가이드가 없으면 HTTP 404를 발생시켜야 한다."""
    service.guide_repo.get_by_id = AsyncMock(return_value=None)

    with pytest.raises(HTTPException) as exc_info:
        await service.get_guide_with_owner_check(uuid4(), uuid4())

    assert exc_info.value.status_code == 404


async def test_get_guide_with_owner_check_forbidden(
    service: LifestyleGuideService,
) -> None:
    """다른 계정의 가이드이면 HTTP 403을 발생시켜야 한다."""
    profile = _make_profile(account_id=uuid4())  # different account
    guide = _make_guide(profile_id=profile.id)

    service.guide_repo.get_by_id = AsyncMock(return_value=guide)
    service.profile_repo.get_by_id = AsyncMock(return_value=profile)

    with pytest.raises(HTTPException) as exc_info:
        await service.get_guide_with_owner_check(guide.id, uuid4())

    assert exc_info.value.status_code == 403


# ── get_latest_guide_with_owner_check ─────────────────────────────────────


async def test_get_latest_guide_with_owner_check_success(
    service: LifestyleGuideService,
) -> None:
    """소유권 확인 후 최신 가이드를 반환해야 한다."""
    account_id = uuid4()
    profile = _make_profile(account_id=account_id)
    guide = _make_guide(profile_id=profile.id)

    service.profile_repo.get_by_id = AsyncMock(return_value=profile)
    service.guide_repo.get_latest_by_profile = AsyncMock(return_value=guide)

    result = await service.get_latest_guide_with_owner_check(profile.id, account_id)

    assert result is guide


async def test_get_latest_guide_with_owner_check_no_guide(
    service: LifestyleGuideService,
) -> None:
    """가이드가 없으면 HTTP 404를 발생시켜야 한다."""
    account_id = uuid4()
    profile = _make_profile(account_id=account_id)

    service.profile_repo.get_by_id = AsyncMock(return_value=profile)
    service.guide_repo.get_latest_by_profile = AsyncMock(return_value=None)

    with pytest.raises(HTTPException) as exc_info:
        await service.get_latest_guide_with_owner_check(profile.id, account_id)

    assert exc_info.value.status_code == 404


async def test_get_latest_guide_with_owner_check_forbidden(
    service: LifestyleGuideService,
) -> None:
    """다른 계정의 프로필이면 HTTP 403을 발생시켜야 한다."""
    profile = _make_profile(account_id=uuid4())
    service.profile_repo.get_by_id = AsyncMock(return_value=profile)

    with pytest.raises(HTTPException) as exc_info:
        await service.get_latest_guide_with_owner_check(profile.id, uuid4())

    assert exc_info.value.status_code == 403


# ── list_guides_with_owner_check ──────────────────────────────────────────


async def test_list_guides_with_owner_check_success(
    service: LifestyleGuideService,
) -> None:
    """소유권 확인 후 가이드 목록을 반환해야 한다."""
    account_id = uuid4()
    profile = _make_profile(account_id=account_id)
    guides = [_make_guide(profile_id=profile.id), _make_guide(profile_id=profile.id)]

    service.profile_repo.get_by_id = AsyncMock(return_value=profile)
    service.guide_repo.get_all_by_profile = AsyncMock(return_value=guides)

    result = await service.list_guides_with_owner_check(profile.id, account_id)

    assert result == guides
    assert len(result) == 2


async def test_list_guides_with_owner_check_forbidden(
    service: LifestyleGuideService,
) -> None:
    """다른 계정의 프로필이면 HTTP 403을 발생시켜야 한다."""
    profile = _make_profile(account_id=uuid4())
    service.profile_repo.get_by_id = AsyncMock(return_value=profile)

    with pytest.raises(HTTPException) as exc_info:
        await service.list_guides_with_owner_check(profile.id, uuid4())

    assert exc_info.value.status_code == 403


# ── get_guide_challenges_with_owner_check ─────────────────────────────────


async def test_get_guide_challenges_with_owner_check_success(
    service: LifestyleGuideService,
) -> None:
    """소유권 확인 후 가이드에 연결된 챌린지 목록을 반환해야 한다."""
    account_id = uuid4()
    profile = _make_profile(account_id=account_id)
    guide = _make_guide(profile_id=profile.id)
    challenges = [_make_challenge(), _make_challenge()]

    service.guide_repo.get_by_id = AsyncMock(return_value=guide)
    service.profile_repo.get_by_id = AsyncMock(return_value=profile)
    service.challenge_repo.get_by_guide_id = AsyncMock(return_value=challenges)

    result = await service.get_guide_challenges_with_owner_check(guide.id, account_id)

    assert result == challenges
    service.challenge_repo.get_by_guide_id.assert_called_once_with(guide.id)


async def test_get_guide_challenges_with_owner_check_guide_not_found(
    service: LifestyleGuideService,
) -> None:
    """가이드가 없으면 HTTP 404를 발생시켜야 한다."""
    service.guide_repo.get_by_id = AsyncMock(return_value=None)

    with pytest.raises(HTTPException) as exc_info:
        await service.get_guide_challenges_with_owner_check(uuid4(), uuid4())

    assert exc_info.value.status_code == 404


async def test_get_guide_challenges_with_owner_check_forbidden(
    service: LifestyleGuideService,
) -> None:
    """다른 계정의 가이드이면 HTTP 403을 발생시켜야 한다."""
    profile = _make_profile(account_id=uuid4())
    guide = _make_guide(profile_id=profile.id)

    service.guide_repo.get_by_id = AsyncMock(return_value=guide)
    service.profile_repo.get_by_id = AsyncMock(return_value=profile)

    with pytest.raises(HTTPException) as exc_info:
        await service.get_guide_challenges_with_owner_check(guide.id, uuid4())

    assert exc_info.value.status_code == 403

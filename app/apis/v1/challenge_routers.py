"""Challenge API router module.

This module contains HTTP endpoints for challenge-related operations
including creating, reading, updating, and deleting challenges.
"""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, status

from app.dependencies.security import get_current_account
from app.dtos.challenge import ChallengeCreate, ChallengeResponse, ChallengeStartRequest, ChallengeUpdate
from app.models.accounts import Account
from app.services.challenge_service import ChallengeService

router = APIRouter(prefix="/challenges", tags=["Challenges"])


def get_challenge_service() -> ChallengeService:
    """Get challenge service instance.

    Returns:
        ChallengeService: Challenge service instance.
    """
    return ChallengeService()


# Type aliases for dependency injection
ChallengeServiceDep = Annotated[ChallengeService, Depends(get_challenge_service)]
CurrentAccount = Annotated[Account, Depends(get_current_account)]


@router.post(
    "",
    response_model=ChallengeResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create challenge",
)
async def create_challenge(
    data: ChallengeCreate,
    current_account: CurrentAccount,
    service: ChallengeServiceDep,
) -> ChallengeResponse:
    """Create a new challenge.

    Args:
        data: Challenge creation data.
        current_account: Current authenticated account.
        service: Challenge service instance.

    Returns:
        ChallengeResponse: Created challenge information.
    """
    challenge = await service.create_challenge_with_owner_check(data.profile_id, current_account.id, data)
    return ChallengeResponse.model_validate(challenge)


@router.get(
    "",
    response_model=list[ChallengeResponse],
    summary="List challenges",
)
async def list_challenges(
    current_account: CurrentAccount,
    service: ChallengeServiceDep,
    profile_id: UUID | None = None,
    active_only: bool = False,
) -> list[ChallengeResponse]:
    """List challenges with optional filtering.

    Args:
        current_account: Current authenticated account.
        service: Challenge service instance.
        profile_id: Optional profile ID to filter by.
        active_only: Whether to return only active challenges.

    Returns:
        list[ChallengeResponse]: List of challenges.
    """
    if profile_id:
        if active_only:
            challenges = await service.get_active_challenges_with_owner_check(profile_id, current_account.id)
        else:
            challenges = await service.get_challenges_by_profile_with_owner_check(profile_id, current_account.id)
    else:
        challenges = await service.get_challenges_by_account(current_account.id)

    return [ChallengeResponse.model_validate(c) for c in challenges]


@router.get(
    "/{challenge_id}",
    response_model=ChallengeResponse,
    summary="Get challenge details",
)
async def get_challenge(
    challenge_id: UUID,
    current_account: CurrentAccount,
    service: ChallengeServiceDep,
) -> ChallengeResponse:
    """Get detailed information about a specific challenge.

    Args:
        challenge_id: Challenge ID to retrieve.
        current_account: Current authenticated account.
        service: Challenge service instance.

    Returns:
        ChallengeResponse: Challenge details.
    """
    challenge = await service.get_challenge_with_owner_check(challenge_id, current_account.id)
    return ChallengeResponse.model_validate(challenge)


@router.patch(
    "/{challenge_id}",
    response_model=ChallengeResponse,
    summary="Update challenge",
)
async def update_challenge(
    challenge_id: UUID,
    data: ChallengeUpdate,
    current_account: CurrentAccount,
    service: ChallengeServiceDep,
) -> ChallengeResponse:
    """Update challenge information.

    Args:
        challenge_id: Challenge ID to update.
        data: Challenge update data.
        current_account: Current authenticated account.
        service: Challenge service instance.

    Returns:
        ChallengeResponse: Updated challenge information.
    """
    challenge = await service.update_challenge_with_owner_check(challenge_id, current_account.id, data)
    return ChallengeResponse.model_validate(challenge)


@router.patch(
    "/{challenge_id}/start",
    response_model=ChallengeResponse,
    summary="Start challenge",
)
async def start_challenge(
    challenge_id: UUID,
    current_account: CurrentAccount,
    service: ChallengeServiceDep,
    data: ChallengeStartRequest | None = None,
) -> ChallengeResponse:
    """Activate a challenge and record its start time.

    Optionally accepts difficulty and target_days to override the
    AI-generated defaults before starting.

    Args:
        challenge_id: Challenge ID to activate.
        current_account: Current authenticated account.
        service: Challenge service instance.
        data: Optional user customization (difficulty, target_days).

    Returns:
        ChallengeResponse: Updated challenge with is_active=True.
    """
    challenge = await service.start_challenge_with_owner_check(challenge_id, current_account.id, data)
    return ChallengeResponse.model_validate(challenge)


# ── 오늘 완료 체크 (서버 단독 진행상태 관리) ──────────────────────────
# 흐름: 소유권 검증 -> 오늘 날짜 멱등 append -> target_days 도달 시 COMPLETED
#       클라이언트는 완료 날짜·상태를 보내지 않는다 (완료/스트릭 위조 방지).
@router.post(
    "/{challenge_id}/check",
    response_model=ChallengeResponse,
    summary="Check today's challenge completion",
)
async def check_challenge_today(
    challenge_id: UUID,
    current_account: CurrentAccount,
    service: ChallengeServiceDep,
) -> ChallengeResponse:
    """오늘 완료를 기록한다.

    완료 날짜와 진행 상태는 서버가 단독으로 결정한다 (오늘 날짜 멱등 추가,
    target_days 도달 시 COMPLETED). 클라이언트는 트리거만 보낸다.

    Args:
        challenge_id: 완료 체크할 챌린지 ID.
        current_account: 현재 인증 계정 (소유권 검증).
        service: Challenge service instance.

    Returns:
        ChallengeResponse: 완료가 반영된 챌린지.
    """
    challenge = await service.complete_day_with_owner_check(challenge_id, current_account.id)
    return ChallengeResponse.model_validate(challenge)


@router.delete(
    "/{challenge_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete challenge",
)
async def delete_challenge(
    challenge_id: UUID,
    current_account: CurrentAccount,
    service: ChallengeServiceDep,
) -> None:
    """Delete a challenge.

    Args:
        challenge_id: Challenge ID to delete.
        current_account: Current authenticated account.
        service: Challenge service instance.
    """
    await service.delete_challenge_with_owner_check(challenge_id, current_account.id)

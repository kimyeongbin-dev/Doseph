"""Profile API router module.

This module contains HTTP endpoints for user profile operations
including creating, reading, updating, and deleting profiles.
"""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, status

from app.dependencies.security import get_current_account
from app.dtos.profile import ProfileCreate, ProfileResponse, ProfileUpdate
from app.models.accounts import Account
from app.services.profile_service import ProfileService

router = APIRouter(prefix="/profiles", tags=["Profiles"])


def get_profile_service() -> ProfileService:
  """Get profile service instance.

  Returns:
      ProfileService: Profile service instance.
  """
  return ProfileService()


# Type aliases for dependency injection
ProfileServiceDep = Annotated[ProfileService, Depends(get_profile_service)]
CurrentAccount = Annotated[Account, Depends(get_current_account)]


@router.post(
  "",
  response_model=ProfileResponse,
  status_code=status.HTTP_201_CREATED,
  summary="Create profile",
)
async def create_profile(
  data: ProfileCreate,
  current_account: CurrentAccount,
  service: ProfileServiceDep,
) -> ProfileResponse:
  """Create a new user profile.

  Args:
      data: Profile creation data.
      current_account: Current authenticated account.
      service: Profile service instance.

  Returns:
      ProfileResponse: Created profile information.
  """
  # Use authenticated account ID (ignore account_id from request body)
  profile = await service.create_profile(current_account.id, data)
  return ProfileResponse.model_validate(profile)


@router.get(
  "/{profile_id}",
  response_model=ProfileResponse,
  summary="Get profile details",
)
async def get_profile(
  profile_id: UUID,
  current_account: CurrentAccount,
  service: ProfileServiceDep,
) -> ProfileResponse:
  """Get detailed information about a specific profile.

  Args:
      profile_id: Profile ID to retrieve.
      current_account: Current authenticated account.
      service: Profile service instance.

  Returns:
      ProfileResponse: Profile details.
  """
  profile = await service.get_profile_with_owner_check(profile_id, current_account.id)
  return ProfileResponse.model_validate(profile)


@router.get(
  "",
  response_model=list[ProfileResponse],
  summary="List profiles",
)
async def list_profiles(
  current_account: CurrentAccount,
  service: ProfileServiceDep,
) -> list[ProfileResponse]:
  """Get all profile list for the current account.

  Returns full profile including health_survey — mypage 의 건강 정보 카드와
  lifestyle guide / chatbot persona 가 health_survey 를 직접 사용하므로 list
  응답에 포함시켜 cache refetch 시 데이터 누락 회귀 차단.

  Args:
      current_account: Current authenticated account.
      service: Profile service instance.

  Returns:
      list[ProfileResponse]: Full profile list (with health_survey).
  """
  # 이전 ProfileSummaryResponse (health_survey 누락) 흐름의 절반 refactor 잔재
  # 였으나, mypage 에서 list refetch 직후 health_survey 가 사라지는 회귀를
  # 일으켜 ProfileResponse 로 통일. payload 약간 커지지만 list 길이 작음
  # (가족 수 수준) 이라 영향 미미.
  profiles = await service.get_profiles_by_account(current_account.id)
  return [ProfileResponse.model_validate(p) for p in profiles]


@router.patch(
  "/{profile_id}",
  response_model=ProfileResponse,
  summary="Update profile",
)
async def update_profile(
  profile_id: UUID,
  data: ProfileUpdate,
  current_account: CurrentAccount,
  service: ProfileServiceDep,
) -> ProfileResponse:
  """Update profile information.

  Args:
      profile_id: Profile ID to update.
      data: Profile update data.
      current_account: Current authenticated account.
      service: Profile service instance.

  Returns:
      ProfileResponse: Updated profile information.
  """
  profile = await service.update_profile_with_owner_check(profile_id, current_account.id, data)
  return ProfileResponse.model_validate(profile)


@router.delete(
  "/{profile_id}",
  status_code=status.HTTP_204_NO_CONTENT,
  summary="Delete profile",
)
async def delete_profile(
  profile_id: UUID,
  current_account: CurrentAccount,
  service: ProfileServiceDep,
) -> None:
  """Delete a profile.

  Args:
      profile_id: Profile ID to delete.
      current_account: Current authenticated account.
      service: Profile service instance.
  """
  await service.delete_profile_with_owner_check(profile_id, current_account.id)

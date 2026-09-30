"""Intake log API router module.

This module contains HTTP endpoints for medication intake log operations
including creating, reading, updating, and deleting intake records.
"""

from datetime import date
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, status

from app.dependencies.security import get_current_account
from app.dtos.intake_log import IntakeLogCreate, IntakeLogResponse, StreakResponse
from app.models.accounts import Account
from app.services.intake_log_service import IntakeLogService

router = APIRouter(prefix="/intake-logs", tags=["Intake Logs"])


def get_intake_log_service() -> IntakeLogService:
  """Get intake log service instance.

  Returns:
      IntakeLogService: Intake log service instance.
  """
  return IntakeLogService()


# Type aliases for dependency injection
IntakeLogServiceDep = Annotated[IntakeLogService, Depends(get_intake_log_service)]
CurrentAccount = Annotated[Account, Depends(get_current_account)]


@router.post(
  "",
  response_model=IntakeLogResponse,
  status_code=status.HTTP_201_CREATED,
  summary="Create intake log",
)
async def create_intake_log(
  data: IntakeLogCreate,
  current_account: CurrentAccount,
  service: IntakeLogServiceDep,
) -> IntakeLogResponse:
  """Create a new medication intake log.

  Args:
      data: Intake log creation data.
      current_account: Current authenticated account.
      service: Intake log service instance.

  Returns:
      IntakeLogResponse: Created intake log information.
  """
  intake_log = await service.create_intake_log_with_owner_check(
    medication_id=data.medication_id,
    profile_id=data.profile_id,
    account_id=current_account.id,
    scheduled_date=data.scheduled_date,
    scheduled_time=data.scheduled_time,
  )
  return IntakeLogResponse.model_validate(intake_log)


@router.get(
  "",
  response_model=list[IntakeLogResponse],
  summary="List intake logs",
)
async def list_intake_logs(
  current_account: CurrentAccount,
  service: IntakeLogServiceDep,
  profile_id: UUID | None = None,
  target_date: date | None = None,
) -> list[IntakeLogResponse]:
  """List medication intake logs with optional filtering.

  Args:
      current_account: Current authenticated account.
      service: Intake log service instance.
      profile_id: Optional profile ID to filter by.
      target_date: Optional target date to filter by.

  Returns:
      list[IntakeLogResponse]: List of intake logs.
  """
  if profile_id and target_date:
    logs = await service.get_logs_by_profile_and_date_with_owner_check(profile_id, target_date, current_account.id)
  elif profile_id:
    logs = await service.get_today_logs_with_owner_check(profile_id, current_account.id)
  else:
    logs = await service.get_logs_by_account(current_account.id)
  return [IntakeLogResponse.model_validate(log) for log in logs]


@router.get(
  "/streak",
  response_model=StreakResponse,
  summary="Get medication streak",
)
async def get_streak(
  current_account: CurrentAccount,
  service: IntakeLogServiceDep,
  profile_id: UUID | None = None,
) -> StreakResponse:
  """Get consecutive medication days for a profile.

  Args:
      current_account: Current authenticated account.
      service: Intake log service instance.
      profile_id: Profile ID to calculate streak for.

  Returns:
      StreakResponse: Consecutive medication days count.
  """
  if not profile_id:
    return StreakResponse(streak_days=0)
  streak = await service.get_streak_with_owner_check(profile_id, current_account.id)
  return StreakResponse(streak_days=streak)


@router.get(
  "/{log_id}",
  response_model=IntakeLogResponse,
  summary="Get intake log details",
)
async def get_intake_log(
  log_id: UUID,
  current_account: CurrentAccount,
  service: IntakeLogServiceDep,
) -> IntakeLogResponse:
  """Get detailed information about a specific intake log.

  Args:
      log_id: Intake log ID to retrieve.
      current_account: Current authenticated account.
      service: Intake log service instance.

  Returns:
      IntakeLogResponse: Intake log details.
  """
  intake_log = await service.get_intake_log_with_owner_check(log_id, current_account.id)
  return IntakeLogResponse.model_validate(intake_log)


@router.post(
  "/{log_id}/take",
  response_model=IntakeLogResponse,
  summary="Mark as taken",
)
async def mark_as_taken(
  log_id: UUID,
  current_account: CurrentAccount,
  service: IntakeLogServiceDep,
) -> IntakeLogResponse:
  """Mark medication intake as completed.

  Args:
      log_id: Intake log ID to mark as taken.
      current_account: Current authenticated account.
      service: Intake log service instance.

  Returns:
      IntakeLogResponse: Updated intake log information.
  """
  intake_log = await service.mark_as_taken_with_owner_check(log_id, current_account.id)
  return IntakeLogResponse.model_validate(intake_log)


@router.post(
  "/{log_id}/skip",
  response_model=IntakeLogResponse,
  summary="Mark as skipped",
)
async def mark_as_skipped(
  log_id: UUID,
  current_account: CurrentAccount,
  service: IntakeLogServiceDep,
) -> IntakeLogResponse:
  """Mark medication intake as skipped.

  Args:
      log_id: Intake log ID to mark as skipped.
      current_account: Current authenticated account.
      service: Intake log service instance.

  Returns:
      IntakeLogResponse: Updated intake log information.
  """
  intake_log = await service.mark_as_skipped_with_owner_check(log_id, current_account.id)
  return IntakeLogResponse.model_validate(intake_log)


@router.delete(
  "/{log_id}",
  status_code=status.HTTP_204_NO_CONTENT,
  summary="Delete intake log",
)
async def delete_intake_log(
  log_id: UUID,
  current_account: CurrentAccount,
  service: IntakeLogServiceDep,
) -> None:
  """Delete an intake log.

  Args:
      log_id: Intake log ID to delete.
      current_account: Current authenticated account.
      service: Intake log service instance.
  """
  await service.delete_intake_log_with_owner_check(log_id, current_account.id)

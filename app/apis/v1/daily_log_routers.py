"""Daily symptom log API router module.

This module contains HTTP endpoints for daily symptom log operations
including creation and retrieval of user-reported symptom entries.
"""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, status

from app.dependencies.security import get_current_account
from app.dtos.lifestyle_guide import DailySymptomLogCreate, DailySymptomLogResponse
from app.models.accounts import Account
from app.services.daily_symptom_log_service import DailySymptomLogService

router = APIRouter(prefix="/daily-logs", tags=["Daily Symptom Logs"])


def get_daily_log_service() -> DailySymptomLogService:
  """Get daily symptom log service instance.

  Returns:
      DailySymptomLogService: Daily symptom log service instance.
  """
  return DailySymptomLogService()


# Type aliases for dependency injection
DailyLogServiceDep = Annotated[DailySymptomLogService, Depends(get_daily_log_service)]
CurrentAccount = Annotated[Account, Depends(get_current_account)]


@router.post(
  "",
  response_model=DailySymptomLogResponse,
  status_code=status.HTTP_201_CREATED,
  summary="Create daily symptom log",
)
async def create_daily_log(
  data: DailySymptomLogCreate,
  current_account: CurrentAccount,
  service: DailyLogServiceDep,
) -> DailySymptomLogResponse:
  """Record a daily symptom log for a profile.

  Args:
      data: Log creation payload including profile_id, log_date, symptoms, note.
      current_account: Current authenticated account.
      service: Daily symptom log service instance.

  Returns:
      DailySymptomLogResponse: Created symptom log.
  """
  log = await service.create_log_with_owner_check(data.profile_id, current_account.id, data)
  return DailySymptomLogResponse.model_validate(log)


@router.get(
  "",
  response_model=list[DailySymptomLogResponse],
  summary="List recent daily symptom logs",
)
async def list_daily_logs(
  profile_id: UUID,
  current_account: CurrentAccount,
  service: DailyLogServiceDep,
  days: int = 30,
) -> list[DailySymptomLogResponse]:
  """Get recent symptom logs for a profile.

  Args:
      profile_id: Target profile UUID.
      current_account: Current authenticated account.
      service: Daily symptom log service instance.
      days: Number of days to look back (default 30).

  Returns:
      list[DailySymptomLogResponse]: Logs ordered newest first.
  """
  logs = await service.get_recent_logs_with_owner_check(profile_id, current_account.id, days)
  return [DailySymptomLogResponse.model_validate(log) for log in logs]

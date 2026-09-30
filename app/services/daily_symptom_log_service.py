"""Daily symptom log service module.

This module provides business logic for creating and retrieving
user-reported daily symptom log entries, with ownership verification.
"""

import logging
from uuid import UUID

from fastapi import HTTPException, status

from app.dtos.lifestyle_guide import DailySymptomLogCreate
from app.models.daily_symptom_log import DailySymptomLog
from app.repositories.daily_symptom_log_repository import DailySymptomLogRepository
from app.repositories.profile_repository import ProfileRepository

logger = logging.getLogger(__name__)


class DailySymptomLogService:
  """Business logic service for daily symptom log management."""

  def __init__(self) -> None:
    self.log_repo = DailySymptomLogRepository()
    self.profile_repo = ProfileRepository()

  async def _verify_profile_ownership(self, profile_id: UUID, account_id: UUID) -> None:
    """Verify that the account owns the given profile.

    Args:
        profile_id: Profile UUID to verify.
        account_id: Account UUID that should own the profile.

    Raises:
        HTTPException: 404 if profile not found, 403 if access denied.
    """
    profile = await self.profile_repo.get_by_id(profile_id)
    if not profile:
      raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="Profile not found.",
      )
    if profile.account_id != account_id:
      raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Access denied to this profile.",
      )

  async def create_log_with_owner_check(
    self,
    profile_id: UUID,
    account_id: UUID,
    data: DailySymptomLogCreate,
  ) -> DailySymptomLog:
    """Create a daily symptom log after verifying profile ownership.

    Args:
        profile_id: Owner profile UUID.
        account_id: Requesting account UUID.
        data: Log creation payload.

    Returns:
        DailySymptomLog: Created log instance.
    """
    await self._verify_profile_ownership(profile_id, account_id)
    log = await self.log_repo.upsert(
      profile_id=profile_id,
      log_date=data.log_date,
      symptoms=data.symptoms,
      note=data.note,
    )
    logger.info(
      "[LOG] 증상 기록 upsert 완료 profile_id=%s log_date=%s symptoms=%d",
      profile_id,
      data.log_date,
      len(data.symptoms or []),
    )
    return log

  async def get_recent_logs_with_owner_check(
    self,
    profile_id: UUID,
    account_id: UUID,
    days: int,
  ) -> list[DailySymptomLog]:
    """Get recent symptom logs after verifying profile ownership.

    Args:
        profile_id: Owner profile UUID.
        account_id: Requesting account UUID.
        days: Number of days to look back.

    Returns:
        list[DailySymptomLog]: Logs ordered newest first.
    """
    await self._verify_profile_ownership(profile_id, account_id)
    return await self.log_repo.get_recent_by_profile(profile_id=profile_id, days=days)

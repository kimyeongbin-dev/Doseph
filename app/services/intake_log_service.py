"""Intake log service module.

This module provides business logic for medication intake tracking operations
including creation, status updates, and ownership verification.
"""

from datetime import date, datetime, time, timedelta
from uuid import UUID

from fastapi import HTTPException, status

from app.core import config
from app.models.intake_log import IntakeLog
from app.repositories.intake_log_repository import IntakeLogRepository
from app.repositories.profile_repository import ProfileRepository
from app.services.medication_service import MedicationService


class IntakeLogService:
  """Intake log business logic service for medication tracking."""

  def __init__(self) -> None:
    self.repository = IntakeLogRepository()
    self.profile_repository = ProfileRepository()
    self.medication_service = MedicationService()

  async def _verify_profile_ownership(self, profile_id: UUID, account_id: UUID) -> None:
    """Verify profile ownership.

    Args:
        profile_id: Profile UUID to verify.
        account_id: Account UUID that should own the profile.

    Raises:
        HTTPException: If profile not found or access denied.
    """
    profile = await self.profile_repository.get_by_id(profile_id)
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

  async def _verify_intake_log_ownership(self, intake_log: IntakeLog, account_id: UUID) -> None:
    """Verify intake log ownership through profile.

    Args:
        intake_log: Intake log to verify ownership for.
        account_id: Account UUID that should own the intake log.

    Raises:
        HTTPException: If access denied to intake log.
    """
    await intake_log.fetch_related("profile")
    if intake_log.profile.account_id != account_id:
      raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Access denied to this intake log.",
      )

  async def get_intake_log(self, intake_log_id: UUID) -> IntakeLog:
    """Get intake log by ID.

    Args:
        intake_log_id: Intake log UUID.

    Returns:
        IntakeLog: Intake log object.

    Raises:
        HTTPException: If intake log not found.
    """
    intake_log = await self.repository.get_by_id(intake_log_id)
    if not intake_log:
      raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="Intake log not found.",
      )
    return intake_log

  async def get_intake_log_with_owner_check(self, intake_log_id: UUID, account_id: UUID) -> IntakeLog:
    """Get intake log with ownership verification.

    Args:
        intake_log_id: Intake log UUID.
        account_id: Account UUID for ownership check.

    Returns:
        IntakeLog: Intake log if owned by account.
    """
    intake_log = await self.get_intake_log(intake_log_id)
    await self._verify_intake_log_ownership(intake_log, account_id)
    return intake_log

  async def get_logs_by_profile_and_date(self, profile_id: UUID, target_date: date) -> list[IntakeLog]:
    """Get intake logs for a profile on a specific date.

    Args:
        profile_id: Profile UUID.
        target_date: Target date for intake logs.

    Returns:
        list[IntakeLog]: List of intake logs for the date.
    """
    return await self.repository.get_by_profile_and_date(profile_id, target_date)

  async def get_logs_by_profile_and_date_with_owner_check(
    self, profile_id: UUID, target_date: date, account_id: UUID
  ) -> list[IntakeLog]:
    """Get intake logs for a profile on a specific date with ownership verification.

    Args:
        profile_id: Profile UUID.
        target_date: Target date for intake logs.
        account_id: Account UUID for ownership check.

    Returns:
        list[IntakeLog]: List of intake logs if profile is owned by account.
    """
    await self._verify_profile_ownership(profile_id, account_id)
    return await self.repository.get_by_profile_and_date(profile_id, target_date)

  async def get_today_logs(self, profile_id: UUID) -> list[IntakeLog]:
    """Get today's intake logs for a profile.

    Args:
        profile_id: Profile UUID.

    Returns:
        list[IntakeLog]: List of today's intake logs.
    """
    return await self.repository.get_by_profile_and_date(profile_id, datetime.now(tz=config.TIMEZONE).date())

  async def get_today_logs_with_owner_check(self, profile_id: UUID, account_id: UUID) -> list[IntakeLog]:
    """Get today's intake logs for a profile with ownership verification.

    Args:
        profile_id: Profile UUID.
        account_id: Account UUID for ownership check.

    Returns:
        list[IntakeLog]: List of today's intake logs if profile is owned by account.
    """
    await self._verify_profile_ownership(profile_id, account_id)
    return await self.repository.get_by_profile_and_date(profile_id, datetime.now(tz=config.TIMEZONE).date())

  async def get_logs_by_account(self, account_id: UUID) -> list[IntakeLog]:
    """Get intake logs for all profiles of an account.

    Args:
        account_id: Account UUID.

    Returns:
        list[IntakeLog]: List of intake logs for all account profiles.
    """
    profiles = await self.profile_repository.get_all_by_account(account_id)
    profile_ids = [p.id for p in profiles]
    return await self.repository.get_by_profiles(profile_ids)

  async def get_streak(self, profile_id: UUID) -> int:
    """Calculate consecutive medication days for a profile.

    A day counts if at least one intake log has TAKEN status.
    If today has a TAKEN log, the streak includes today.
    If today has no TAKEN logs, the streak is calculated from yesterday.

    Args:
        profile_id: Profile UUID.

    Returns:
        int: Number of consecutive days with at least one taken medication.
    """
    taken_dates = await self.repository.get_taken_dates_by_profile(profile_id)
    today = datetime.now(tz=config.TIMEZONE).date()
    start = today if today in taken_dates else today - timedelta(days=1)

    streak = 0
    current = start
    while current in taken_dates:
      streak += 1
      current -= timedelta(days=1)
    return streak

  async def get_streak_with_owner_check(self, profile_id: UUID, account_id: UUID) -> int:
    """Calculate consecutive medication days with ownership verification.

    Args:
        profile_id: Profile UUID.
        account_id: Account UUID for ownership check.

    Returns:
        int: Number of consecutive days with at least one taken medication.
    """
    await self._verify_profile_ownership(profile_id, account_id)
    return await self.get_streak(profile_id)

  async def get_pending_logs(self, profile_id: UUID) -> list[IntakeLog]:
    """Get pending intake logs for a profile.

    Args:
        profile_id: Profile UUID.

    Returns:
        list[IntakeLog]: List of pending intake logs.
    """
    return await self.repository.get_pending_by_profile(profile_id)

  async def create_intake_log(
    self,
    medication_id: UUID,
    profile_id: UUID,
    scheduled_date: date,
    scheduled_time: time,
  ) -> IntakeLog:
    """복용 기록 생성"""
    return await self.repository.create(
      medication_id=medication_id,
      profile_id=profile_id,
      scheduled_date=scheduled_date,
      scheduled_time=scheduled_time,
    )

  async def create_intake_log_with_owner_check(
    self,
    medication_id: UUID,
    profile_id: UUID,
    account_id: UUID,
    scheduled_date: date,
    scheduled_time: time,
  ) -> IntakeLog:
    """소유권 검증 후 복용 기록 생성"""
    await self._verify_profile_ownership(profile_id, account_id)
    return await self.create_intake_log(
      medication_id=medication_id,
      profile_id=profile_id,
      scheduled_date=scheduled_date,
      scheduled_time=scheduled_time,
    )

  @staticmethod
  def _ensure_aware(dt: datetime | None) -> datetime | None:
    """Return timezone-aware datetime; assume KST if tzinfo is missing.

    Args:
        dt: Datetime to normalize.

    Returns:
        datetime | None: Timezone-aware datetime, or None.
    """
    if dt is None:
      return dt
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=config.TIMEZONE)

  async def mark_as_taken(self, intake_log_id: UUID, taken_at: datetime | None = None) -> IntakeLog:
    """Mark intake log as taken.

    Args:
        intake_log_id: Intake log UUID.
        taken_at: Actual intake time. Defaults to now if None.

    Returns:
        IntakeLog: Updated intake log.

    Raises:
        HTTPException: If intake log already processed.
    """
    intake_log = await self.get_intake_log(intake_log_id)

    if intake_log.intake_status != "SCHEDULED":
      raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail="이미 처리된 복용 기록입니다.",
      )

    # _ensure_aware: naive datetime이 들어올 경우 KST로 보정 (DB timezone 오염 방지)
    return await self.repository.mark_as_taken(intake_log, self._ensure_aware(taken_at))

  async def mark_as_taken_with_owner_check(
    self, intake_log_id: UUID, account_id: UUID, taken_at: datetime | None = None
  ) -> IntakeLog:
    """Mark intake log as taken with ownership verification.

    복용 완료 처리 후 해당 약의 잔여 복용 횟수를 1 감소시키고,
    잔여 횟수가 0이 되면 약을 자동으로 비활성화합니다.

    Args:
        intake_log_id: Intake log UUID.
        account_id: Account UUID for ownership check.
        taken_at: Actual intake time. Defaults to now if None.

    Returns:
        IntakeLog: Updated intake log if owned by account.

    Raises:
        HTTPException: If intake log already processed or access denied.
    """
    intake_log = await self.get_intake_log_with_owner_check(intake_log_id, account_id)

    if intake_log.intake_status != "SCHEDULED":
      raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail="이미 처리된 복용 기록입니다.",
      )

    # 복용 완료 기록 저장 (taken_at naive → KST aware 보정)
    result = await self.repository.mark_as_taken(intake_log, self._ensure_aware(taken_at))
    # 해당 약 잔여 횟수 감소 → 0이 되면 is_active=False 자동 처리
    medication = await self.medication_service.get_medication(intake_log.medication_id)
    await self.medication_service.decrement_and_deactivate_if_exhausted(medication)
    return result

  async def mark_as_skipped(self, intake_log_id: UUID) -> IntakeLog:
    """Mark intake log as skipped.

    Args:
        intake_log_id: Intake log UUID.

    Returns:
        IntakeLog: Updated intake log.

    Raises:
        HTTPException: If intake log already processed.
    """
    intake_log = await self.get_intake_log(intake_log_id)

    if intake_log.intake_status != "SCHEDULED":
      raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail="이미 처리된 복용 기록입니다.",
      )

    return await self.repository.mark_as_skipped(intake_log)

  async def mark_as_skipped_with_owner_check(self, intake_log_id: UUID, account_id: UUID) -> IntakeLog:
    """Mark intake log as skipped with ownership verification.

    Args:
        intake_log_id: Intake log UUID.
        account_id: Account UUID for ownership check.

    Returns:
        IntakeLog: Updated intake log if owned by account.

    Raises:
        HTTPException: If intake log already processed.
    """
    intake_log = await self.get_intake_log_with_owner_check(intake_log_id, account_id)

    if intake_log.intake_status != "SCHEDULED":
      raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail="이미 처리된 복용 기록입니다.",
      )

    return await self.repository.mark_as_skipped(intake_log)

  async def delete_intake_log(self, intake_log_id: UUID) -> None:
    """Delete intake log (hard delete).

    Args:
        intake_log_id: Intake log UUID to delete.
    """
    intake_log = await self.get_intake_log(intake_log_id)
    await self.repository.delete(intake_log)

  async def delete_intake_log_with_owner_check(self, intake_log_id: UUID, account_id: UUID) -> None:
    """Delete intake log with ownership verification (hard delete).

    Args:
        intake_log_id: Intake log UUID to delete.
        account_id: Account UUID for ownership check.
    """
    intake_log = await self.get_intake_log_with_owner_check(intake_log_id, account_id)
    await self.repository.delete(intake_log)

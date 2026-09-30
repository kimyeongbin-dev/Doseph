"""Unit tests for IntakeLogService — mark_as_taken triggers medication decrement."""

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.services.intake_log_service import IntakeLogService


@pytest.fixture
def service() -> IntakeLogService:
  svc = IntakeLogService.__new__(IntakeLogService)
  svc.repository = AsyncMock()
  svc.profile_repository = AsyncMock()
  svc.medication_service = AsyncMock()
  return svc


@pytest.fixture
def mock_intake_log() -> MagicMock:
  account_id = uuid4()
  log = MagicMock()
  log.id = uuid4()
  log.intake_status = "SCHEDULED"
  log.medication_id = uuid4()
  log.profile = MagicMock()
  log.profile.account_id = account_id
  log.fetch_related = AsyncMock()
  return log


async def test_mark_as_taken_triggers_medication_decrement(
  service: IntakeLogService,
  mock_intake_log: MagicMock,
) -> None:
  """복용 완료 처리 시 medication.decrement_and_deactivate_if_exhausted가 호출되어야 한다."""
  account_id = mock_intake_log.profile.account_id
  mock_medication = MagicMock()

  service.repository.get_by_id = AsyncMock(return_value=mock_intake_log)
  service.repository.mark_as_taken = AsyncMock(return_value=mock_intake_log)
  service.medication_service.get_medication = AsyncMock(return_value=mock_medication)
  service.medication_service.decrement_and_deactivate_if_exhausted = AsyncMock()

  await service.mark_as_taken_with_owner_check(mock_intake_log.id, account_id)

  service.medication_service.decrement_and_deactivate_if_exhausted.assert_called_once_with(mock_medication)


async def test_mark_as_skipped_does_not_decrement(
  service: IntakeLogService,
  mock_intake_log: MagicMock,
) -> None:
  """복용 건너뜀 처리 시 medication decrement가 호출되지 않아야 한다."""
  account_id = mock_intake_log.profile.account_id

  service.repository.get_by_id = AsyncMock(return_value=mock_intake_log)
  service.repository.mark_as_skipped = AsyncMock(return_value=mock_intake_log)

  await service.mark_as_skipped_with_owner_check(mock_intake_log.id, account_id)

  service.medication_service.decrement_and_deactivate_if_exhausted.assert_not_called()

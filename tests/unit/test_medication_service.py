"""Unit tests for MedicationService — decrement_and_deactivate_if_exhausted, get_prescription_dates_with_owner_check."""

from datetime import date
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.dtos.medication import PrescriptionDateItem
from app.services.medication_service import MedicationService


@pytest.fixture
def service() -> MedicationService:
  svc = MedicationService.__new__(MedicationService)
  svc.repository = AsyncMock()
  svc.profile_repository = AsyncMock()
  return svc


@pytest.fixture
def mock_medication() -> MagicMock:
  med = MagicMock()
  med.id = uuid4()
  med.remaining_intake_count = 3
  med.is_active = True
  return med


async def test_decrement_calls_repository(
  service: MedicationService,
  mock_medication: MagicMock,
) -> None:
  """repository.decrement_remaining_count가 반드시 호출되어야 한다."""
  service.repository.decrement_remaining_count = AsyncMock(return_value=mock_medication)

  await service.decrement_and_deactivate_if_exhausted(mock_medication)

  service.repository.decrement_remaining_count.assert_called_once_with(mock_medication)


async def test_deactivates_when_count_reaches_zero(
  service: MedicationService,
  mock_medication: MagicMock,
) -> None:
  """remaining_intake_count가 0이 되면 is_active=False로 업데이트되어야 한다."""
  mock_medication.remaining_intake_count = 1

  async def decrement(med: MagicMock) -> MagicMock:
    med.remaining_intake_count -= 1
    return med

  service.repository.decrement_remaining_count = decrement
  service.repository.update = AsyncMock(return_value=mock_medication)

  await service.decrement_and_deactivate_if_exhausted(mock_medication)

  service.repository.update.assert_called_once_with(mock_medication, is_active=False)


async def test_does_not_deactivate_when_count_above_zero(
  service: MedicationService,
  mock_medication: MagicMock,
) -> None:
  """remaining_intake_count가 0보다 크면 is_active를 변경하지 않아야 한다."""
  mock_medication.remaining_intake_count = 3

  async def decrement(med: MagicMock) -> MagicMock:
    med.remaining_intake_count -= 1
    return med

  service.repository.decrement_remaining_count = decrement
  service.repository.update = AsyncMock(return_value=mock_medication)

  await service.decrement_and_deactivate_if_exhausted(mock_medication)

  service.repository.update.assert_not_called()


# ── get_prescription_dates_with_owner_check ────────────────────────────────


async def test_get_prescription_dates_verifies_ownership(
  service: MedicationService,
) -> None:
  """소유권 검증이 먼저 수행되어야 한다."""
  profile_id = uuid4()
  account_id = uuid4()
  service._verify_profile_ownership = AsyncMock()
  service.repository.get_prescription_dates_by_profile = AsyncMock(return_value=[])

  await service.get_prescription_dates_with_owner_check(profile_id, account_id)

  service._verify_profile_ownership.assert_called_once_with(profile_id, account_id)


async def test_get_prescription_dates_returns_repository_result(
  service: MedicationService,
) -> None:
  """리포지터리의 결과를 그대로 반환해야 한다."""
  profile_id = uuid4()
  account_id = uuid4()
  expected = [PrescriptionDateItem(prescription_date=date(2026, 3, 15), department="내과", count=2)]
  service._verify_profile_ownership = AsyncMock()
  service.repository.get_prescription_dates_by_profile = AsyncMock(return_value=expected)

  result = await service.get_prescription_dates_with_owner_check(profile_id, account_id)

  assert result == expected
  service.repository.get_prescription_dates_by_profile.assert_called_once_with(profile_id)

"""Unit tests for MedicationRepository — decrement_remaining_count, get_prescription_dates_by_profile."""

from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.repositories.medication_repository import MedicationRepository


@pytest.fixture
def repository() -> MedicationRepository:
  return MedicationRepository()


@pytest.fixture
def mock_medication() -> MagicMock:
  med = MagicMock()
  med.id = uuid4()
  med.remaining_intake_count = 3
  med.is_active = True
  med.save = AsyncMock()
  return med


async def test_decrement_remaining_count_decrements_by_one(
  repository: MedicationRepository,
  mock_medication: MagicMock,
) -> None:
  """remaining_intake_count가 1 감소하고 저장되어야 한다."""
  initial_count = mock_medication.remaining_intake_count

  result = await repository.decrement_remaining_count(mock_medication)

  assert result.remaining_intake_count == initial_count - 1
  mock_medication.save.assert_called_once()


async def test_decrement_remaining_count_does_not_go_below_zero(
  repository: MedicationRepository,
  mock_medication: MagicMock,
) -> None:
  """remaining_intake_count가 이미 0이면 감소 없이 그대로 반환해야 한다."""
  mock_medication.remaining_intake_count = 0

  result = await repository.decrement_remaining_count(mock_medication)

  assert result.remaining_intake_count == 0
  mock_medication.save.assert_not_called()


# ── get_prescription_dates_by_profile ──────────────────────────────────────


def _make_med(dispensed: date | None, start: date, department: str | None) -> MagicMock:
  med = MagicMock()
  med.dispensed_date = dispensed
  med.start_date = start
  med.department = department
  return med


async def test_prescription_dates_groups_by_date_and_department(
  repository: MedicationRepository,
) -> None:
  """dispensed_date + department 기준으로 그룹화되어 count가 올바르게 집계되어야 한다."""
  profile_id = uuid4()
  date1 = date(2026, 3, 15)
  date2 = date(2026, 2, 1)
  medications = [
    _make_med(date1, date1, "내과"),
    _make_med(date1, date1, "내과"),
    _make_med(date2, date2, "정형외과"),
  ]

  with patch("app.repositories.medication_repository.Medication") as mock_med:
    mock_med.filter.return_value.all = AsyncMock(return_value=medications)
    result = await repository.get_prescription_dates_by_profile(profile_id)

  assert len(result) == 2
  internal_item = next(item for item in result if item.department == "내과")
  assert internal_item.count == 2
  assert internal_item.prescription_date == date1
  orthopedic_item = next(item for item in result if item.department == "정형외과")
  assert orthopedic_item.count == 1


async def test_prescription_dates_falls_back_to_start_date(
  repository: MedicationRepository,
) -> None:
  """dispensed_date가 None이면 start_date를 날짜 기준으로 사용해야 한다."""
  profile_id = uuid4()
  start = date(2026, 1, 10)
  medications = [_make_med(None, start, "외과")]

  with patch("app.repositories.medication_repository.Medication") as mock_med:
    mock_med.filter.return_value.all = AsyncMock(return_value=medications)
    result = await repository.get_prescription_dates_by_profile(profile_id)

  assert len(result) == 1
  assert result[0].prescription_date == start


async def test_prescription_dates_sorted_descending(
  repository: MedicationRepository,
) -> None:
  """결과는 날짜 내림차순으로 정렬되어야 한다."""
  profile_id = uuid4()
  medications = [
    _make_med(date(2026, 1, 1), date(2026, 1, 1), "내과"),
    _make_med(date(2026, 3, 1), date(2026, 3, 1), "외과"),
    _make_med(date(2026, 2, 1), date(2026, 2, 1), "정형외과"),
  ]

  with patch("app.repositories.medication_repository.Medication") as mock_med:
    mock_med.filter.return_value.all = AsyncMock(return_value=medications)
    result = await repository.get_prescription_dates_by_profile(profile_id)

  assert result[0].prescription_date == date(2026, 3, 1)
  assert result[1].prescription_date == date(2026, 2, 1)
  assert result[2].prescription_date == date(2026, 1, 1)


async def test_prescription_dates_returns_empty_list_when_no_medications(
  repository: MedicationRepository,
) -> None:
  """복약이 없으면 빈 리스트를 반환해야 한다."""
  profile_id = uuid4()

  with patch("app.repositories.medication_repository.Medication") as mock_med:
    mock_med.filter.return_value.all = AsyncMock(return_value=[])
    result = await repository.get_prescription_dates_by_profile(profile_id)

  assert result == []

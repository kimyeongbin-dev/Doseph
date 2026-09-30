"""F3 — `create_medication` 시 즉시 회수 체크 hook 통합 테스트 (PLAN §16.3.2).

리팩터 후 양쪽 service 의 hook 은 `check_and_alert_on_medication_save`
헬퍼 호출 한 줄로 축소되었으므로, 이 테스트는 다음만 검증한다:

- F3-1: create_medication 가 헬퍼를 정확히 1회 호출 (medication 인자 그대로)
- F3-2: 헬퍼 예외는 medication 등록 흐름을 망치지 않는다 (격리)

매칭 로직 자체의 정확성은 `test_recall_notification_service.py::TestCheckAndAlertOnMedicationSave`
에서 단위 테스트로 커버.
"""

from __future__ import annotations

from datetime import date
from typing import Any, Self
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

_HELPER = "app.services.medication_service.check_and_alert_on_medication_save"
_TRANSACTION = "app.services.medication_service.in_transaction"


class _NoopTransaction:
  """Tortoise init 없이 ``async with in_transaction()`` 을 통과시키는 더미."""

  async def __aenter__(self) -> Self:
    return self

  async def __aexit__(self, *_args: object) -> None:
    return None


def _build_medication() -> Any:
  med = MagicMock()
  med.id = uuid4()
  med.profile_id = uuid4()
  med.medicine_name = "마데카솔케어연고"
  return med


def _build_group() -> Any:
  group = MagicMock()
  group.id = uuid4()
  return group


def _build_create_dto() -> Any:
  """`MedicationCreate` 형태의 가벼운 stub."""
  dto = MagicMock()
  dto.medicine_name = "마데카솔케어연고"
  dto.dose_per_intake = "1정"
  dto.intake_instruction = "식후 30분"
  dto.intake_times = ["08:00"]
  dto.total_intake_count = 30
  dto.remaining_intake_count = None
  dto.start_date = date(2026, 4, 27)
  dto.end_date = None
  dto.dispensed_date = None
  dto.expiration_date = None
  return dto


@pytest.mark.asyncio
async def test_f3_1_create_medication_invokes_helper_once() -> None:
  """create_medication 은 신규 row 와 함께 헬퍼를 단 1회 호출해야 한다."""
  from app.services.medication_service import MedicationService

  service = MedicationService()
  medication = _build_medication()
  service.repository = MagicMock(create=AsyncMock(return_value=medication))
  service.prescription_group_repository = MagicMock(
    create=AsyncMock(return_value=_build_group()),
  )

  with (
    patch(_HELPER, new=AsyncMock(return_value=None)) as helper,
    patch(_TRANSACTION, return_value=_NoopTransaction()),
  ):
    result = await service.create_medication(profile_id=uuid4(), data=_build_create_dto())

  assert result is medication
  helper.assert_awaited_once()
  args, kwargs = helper.await_args
  # 헬퍼가 받은 medication 인스턴스가 repository 가 만든 그것과 동일한지
  assert (args[0] if args else kwargs["medication"]) is medication


@pytest.mark.asyncio
async def test_f3_2_helper_exception_does_not_break_create() -> None:
  """헬퍼 raise 시에도 medication 자체는 정상 반환되어야 한다 (격리)."""
  from app.services.medication_service import MedicationService

  service = MedicationService()
  medication = _build_medication()
  service.repository = MagicMock(create=AsyncMock(return_value=medication))
  service.prescription_group_repository = MagicMock(
    create=AsyncMock(return_value=_build_group()),
  )

  async def boom(*_args: Any, **_kwargs: Any) -> Any:
    msg = "boom"
    raise RuntimeError(msg)

  with (
    patch(_HELPER, new=AsyncMock(side_effect=boom)),
    patch(_TRANSACTION, return_value=_NoopTransaction()),
  ):
    result = await service.create_medication(profile_id=uuid4(), data=_build_create_dto())

  # 예외가 위로 새지 않고 medication 객체가 그대로 반환됨
  assert result is medication

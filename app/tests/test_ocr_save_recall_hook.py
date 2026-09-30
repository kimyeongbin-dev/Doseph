"""F3 — `OCRService._save_one_medication` 회수 hook 통합 테스트 (PLAN §16.3.1).

OCR 경로는 `medication_service.create_medication` 을 거치지 않고
`Medication.create()` 를 직접 호출하므로 별도 hook 이 필요하다.
리팩터 후 양쪽 모두 동일한 `check_and_alert_on_medication_save`
헬퍼를 호출한다 — 본 테스트는 mock 으로 그 호출만 검증한다.

- F3-3: OCR 확정으로 만들어진 medication 마다 헬퍼가 정확히 1회 호출
- 격리: 헬퍼 예외는 OCR 흐름을 망치지 않는다
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

_HELPER = "app.services.ocr_service.check_and_alert_on_medication_save"


def _extracted_medicine() -> Any:
  em = MagicMock()
  em.medicine_name = "마데카솔케어연고"
  em.department = "내과"
  em.category = "외용제"
  em.dose_per_intake = "적당량"
  em.intake_instruction = None
  em.daily_intake_count = 1
  em.total_intake_days = 5
  em.dispensed_date = None
  return em


@pytest.mark.asyncio
async def test_save_one_medication_invokes_helper() -> None:
  """OCR 경로의 medication 등록도 헬퍼를 1회 호출해야 한다."""
  from app.services.ocr_service import OCRService

  fake_medication = MagicMock()
  fake_medication.id = "med-id"
  fake_medication.profile_id = "p-1"
  fake_medication.medicine_name = "마데카솔케어연고"

  service = OCRService.__new__(OCRService)  # __init__ 우회 — Redis/Queue 의존성 회피

  with (
    patch("app.services.ocr_service.Medication.create", new=AsyncMock(return_value=fake_medication)),
    patch(_HELPER, new=AsyncMock(return_value=None)) as helper,
  ):
    result = await service._save_one_medication(
      _extracted_medicine(),
      profile_id="p-1",
      group_id=uuid4(),
    )

  assert result is fake_medication
  helper.assert_awaited_once()
  args, kwargs = helper.await_args
  assert (args[0] if args else kwargs["medication"]) is fake_medication


@pytest.mark.asyncio
async def test_helper_exception_does_not_break_save() -> None:
  """헬퍼 raise 시에도 medication 은 정상 반환 (격리)."""
  from app.services.ocr_service import OCRService

  fake_medication = MagicMock()
  fake_medication.id = "med-id"
  fake_medication.profile_id = "p-1"

  async def boom(*_args: Any, **_kwargs: Any) -> Any:
    msg = "boom"
    raise RuntimeError(msg)

  service = OCRService.__new__(OCRService)

  with (
    patch("app.services.ocr_service.Medication.create", new=AsyncMock(return_value=fake_medication)),
    patch(_HELPER, new=AsyncMock(side_effect=boom)),
  ):
    result = await service._save_one_medication(
      _extracted_medicine(),
      profile_id="p-1",
      group_id=uuid4(),
    )

  assert result is fake_medication

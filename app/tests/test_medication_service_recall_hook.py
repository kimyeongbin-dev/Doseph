"""medication_service.create_medication 의 recall_alert 첨부 통합 테스트
(Phase 7 — §A.5.3, 시연 봉투 §D.1·§D.2·§D.3·§D.4 + §D.5 mixed).

본 PR 의 디자인 선택 (단건 응답):
    create_medication 응답의 recall_alert 는 **해당 medication 의 매칭만**
    포함한다. §D.3 (cross-product) / §D.5 (mixed) 의 봉투 단위 items 합산은
    FE 측 모달이 같은 prescription_group_id 응답들을 모아 표시하는 책임으로
    분리한다 (시연 시 마지막 응답 시점에 토스트 1회).

검증:
- 시연 시나리오 7건(아래 ``_ENVELOPE``) — 매칭 없음은 None, 매칭은 severity·item_seq
- 회수 조회에 **등록된 약의 이름**이 넘어간다(가짜 저장소가 인자를 무시하면
  시나리오 이름이 아무것도 확인하지 않는다 — B-18 배치 3 에서 결함 주입으로 확인)
- 빌더 실패는 등록을 깨지 않고 recall_alert=None 으로 떨어진다

⚠️ 직접입력 경로만 다룬다. OCR 확정 경로(``OCRService._save_one_medication``)는
recall_alert 를 만들지 않는다(``QA-71``) — 그 경로의 회수 후크는
``test_ocr_save_recall_hook.py`` 가 본다.

Tortoise ORM / RQ / 외부 API 호출 X — 모든 의존성 mock 으로 주입.
"""

from __future__ import annotations

from datetime import date
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest

from app.models.medication import Medication
from app.tests.mock_data.drug_recall_seed import SEED_RECALL_PRODUCTION_20

# ── 공용 헬퍼 ────────────────────────────────────────────────────────


def _make_medication_create(medicine_name: str, profile_id: UUID) -> Any:
  """MedicationCreate DTO 인스턴스를 최소 필드로 만든다."""
  from app.dtos.medication import MedicationCreate

  return MedicationCreate(
    profile_id=profile_id,
    medicine_name=medicine_name,
    intake_times=["08:00"],
    total_intake_count=10,
    start_date=date(2026, 4, 30),
  )


def _make_recall_row_from_seed(seed_idx: int) -> Any:
  """SEED_RECALL_PRODUCTION_20[seed_idx] 의 dict 를 ORM-like MagicMock 으로 변환."""
  s = SEED_RECALL_PRODUCTION_20[seed_idx]
  return MagicMock(
    item_seq=s["ITEM_SEQ"],
    product_name=s["PRDUCT"],
    entrps_name=s["ENTRPS"],
    recall_reason=s["RTRVL_RESN"],
    recall_command_date=s["RECALL_COMMAND_DATE"],
    sale_stop_yn=s["SALE_STOP_YN"],
  )


def _build_service_with_mocks(monkeypatch: pytest.MonkeyPatch, medicine_name: str) -> tuple[Any, Any]:
  """Service 인스턴스를 만들고 저장 의존성을 mock 으로 교체한다.

  medication 가짜는 ``spec=Medication`` 이다 — 모델에 없는 속성(예: ``item_seq``)을
  읽으면 운영처럼 없다고 답하게 해서, 가짜가 아무 값이나 돌려주는 차이를 없앤다.

  Returns:
      (service, medication) — 저장소가 돌려줄 medication 은 등록한 이름을 갖는다.
  """
  from app.services.medication_service import MedicationService

  service = MedicationService()
  medication = MagicMock(spec=Medication, id=uuid4(), medicine_name=medicine_name)
  monkeypatch.setattr(service.prescription_group_repository, "create", AsyncMock(return_value=MagicMock(id=uuid4())))
  monkeypatch.setattr(service.repository, "create", AsyncMock(return_value=medication))
  return service, medication


# ── 시연 봉투 시나리오 (§D.1 ~ §D.5) ─────────────────────────────────
# (등록 이름, 저장소가 돌려줄 seed 번호 또는 None, 기대 severity, 기대 item_seq)
_ENVELOPE = [
  pytest.param("이부프로펜정200밀리그램", None, None, None, id="D1-no-match"),
  pytest.param("데모라니티딘정150밀리그램", 0, "critical", "202504001", id="D2-ndma-critical"),
  pytest.param("테스트솔정4밀리그램(메틸프레드니솔론)", 2, "critical", "202504003", id="D3-gmp-first"),
  pytest.param("테스트프레드정5밀리그램(프레드니솔론)", 3, "critical", "202504004", id="D3-gmp-second"),
  pytest.param("데이오웬크림0.05%(데소나이드)", 5, "advisory", "202504006", id="D4-advisory"),
  pytest.param("샘플발사르탄정80밀리그램", 1, "critical", "202504002", id="D5-critical"),
  pytest.param("알파아세트아미노펜정500밀리그램", 6, "advisory", "202504007", id="D5-advisory"),
]


@pytest.mark.asyncio
@pytest.mark.parametrize(("name", "seed_idx", "severity", "item_seq"), _ENVELOPE)
async def test_create_attaches_recall_alert_for_envelope(
  monkeypatch: pytest.MonkeyPatch,
  name: str,
  seed_idx: int | None,
  severity: str | None,
  item_seq: str | None,
) -> None:
  """등록한 약의 이름으로 회수를 조회하고, 그 결과를 recall_alert 로 붙인다."""
  service, medication = _build_service_with_mocks(monkeypatch, name)
  rows = [] if seed_idx is None else [_make_recall_row_from_seed(seed_idx)]

  with (
    patch("app.services.medication_service.in_transaction"),
    patch("app.services.medication_service.check_and_alert_on_medication_save", new=AsyncMock()),
    patch("app.services.medication_service.DrugRecallRepository") as repo_cls,
  ):
    lookup = AsyncMock(return_value=rows)
    repo_cls.return_value.find_by_item_seq_or_name = lookup
    result = await service.create_medication(uuid4(), _make_medication_create(name, uuid4()))

  assert result is medication
  lookup.assert_awaited_once_with(item_seq=None, product_name=name)
  alert = medication.recall_alert
  if severity is None:
    assert alert is None
    return
  assert alert.severity == severity
  assert [item.item_seq for item in alert.items] == [item_seq]


# ── 격리: 빌더 실패는 등록을 깨지 않는다 ─────────────────────────────


@pytest.mark.asyncio
async def test_lookup_failure_falls_back_to_none(monkeypatch: pytest.MonkeyPatch) -> None:
  """회수 조회가 예외를 내도 medication 은 반환되고 recall_alert=None 이다."""
  service, medication = _build_service_with_mocks(monkeypatch, "데모라니티딘정150밀리그램")

  with (
    patch("app.services.medication_service.in_transaction"),
    patch("app.services.medication_service.check_and_alert_on_medication_save", new=AsyncMock()),
    patch("app.services.medication_service.DrugRecallRepository") as repo_cls,
  ):
    repo_cls.return_value.find_by_item_seq_or_name = AsyncMock(side_effect=RuntimeError("db down"))
    result = await service.create_medication(uuid4(), _make_medication_create("데모라니티딘정150밀리그램", uuid4()))

  assert result is medication
  assert medication.recall_alert is None

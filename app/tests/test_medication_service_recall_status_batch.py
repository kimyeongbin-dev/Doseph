"""medication_service 의 마이페이지 batch lookup 통합 테스트
(Phase 7 — §A.5.4, GET /api/v1/medications 응답에 recall_status 첨부).

검증 포인트:
- 등록된 약 N=5 (§D.1·§D.2·§D.3·§D.4 + 일반약) 중
  회수 매칭 4건은 recall_status != None, 일반약 1건은 None.
- N+1 회피: ``find_recalls_for_medications`` 호출 1회만.
- 같은 medication 에 매칭 2건 (§8 동일 ITEM_SEQ) → 라벨에 강한 severity +
  최근 날짜, ``alert_payload.items`` 길이 2.
- ``recall_status.alert_payload`` 와 등록 시점 ``recall_alert`` 동일 구조
  (라벨 클릭 시 모달 재발화 일관성 검증).

Tortoise ORM / 외부 API 호출 X — DI 로 mock 주입.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest

from app.tests.mock_data.drug_recall_seed import SEED_RECALL_PRODUCTION_20

# ── 공용 헬퍼 ────────────────────────────────────────────────────────


def _make_medication(medicine_name: str) -> Any:
  """ORM-like Medication mock — id 자동 부여."""
  return MagicMock(id=uuid4(), medicine_name=medicine_name)


def _make_recall_row(seed_idx: int) -> Any:
  s = SEED_RECALL_PRODUCTION_20[seed_idx]
  return MagicMock(
    item_seq=s["ITEM_SEQ"],
    product_name=s["PRDUCT"],
    entrps_name=s["ENTRPS"],
    recall_reason=s["RTRVL_RESN"],
    recall_command_date=s["RECALL_COMMAND_DATE"],
    sale_stop_yn=s["SALE_STOP_YN"],
  )


# ── batch 분기: 5건 medication 중 4건 매칭 ──────────────────────────


class TestBatchRecallStatusForFiveMedications:
  @pytest.mark.asyncio
  async def test_returns_status_for_matched_and_none_for_unmatched(self) -> None:
    """N=5 중 D.1 (이부프로펜) 만 None, 나머지 4건 recall_status != None."""
    from app.services.medication_service import MedicationService

    service = MedicationService()
    profile_id = uuid4()

    med_d1 = _make_medication("이부프로펜정200밀리그램")  # 매칭 없음
    med_d2 = _make_medication("데모라니티딘정150밀리그램")  # critical
    med_d3 = _make_medication("테스트솔정4밀리그램(메틸프레드니솔론)")  # critical
    med_d4 = _make_medication("데이오웬크림0.05%(데소나이드)")  # advisory
    med_extra = _make_medication("샘플발사르탄정80밀리그램")  # critical

    meds = [med_d1, med_d2, med_d3, med_d4, med_extra]
    grouping: dict[UUID, list[Any]] = {
      med_d2.id: [_make_recall_row(0)],  # §1 NDMA
      med_d3.id: [_make_recall_row(2)],  # §2 GMP
      med_d4.id: [_make_recall_row(5)],  # §3 자율회수
      med_extra.id: [_make_recall_row(1)],  # §1 NDEA
    }

    service.repository.get_all_by_profile = AsyncMock(return_value=meds)
    service._verify_profile_ownership = AsyncMock()

    with patch("app.services.medication_service.DrugRecallRepository") as repo_cls:
      repo_cls.return_value.find_recalls_for_medications = AsyncMock(return_value=grouping)
      results = await service.list_medications_with_recall_status_with_owner_check(profile_id, account_id=uuid4())

    # 응답은 [(medication, recall_status), ...] 또는 medication.recall_status attach
    # 형태와 무관하게 medication_id 별 recall_status 매핑이 정확해야 한다.
    statuses = {r.medication.id: r.recall_status for r in results}
    assert statuses[med_d1.id] is None
    assert statuses[med_d2.id] is not None
    assert statuses[med_d2.id].severity == "critical"
    assert statuses[med_d3.id] is not None
    assert statuses[med_d3.id].severity == "critical"
    assert statuses[med_d4.id] is not None
    assert statuses[med_d4.id].severity == "advisory"
    assert statuses[med_extra.id] is not None
    assert statuses[med_extra.id].severity == "critical"


# ── N+1 회피 ────────────────────────────────────────────────────────


class TestBatchAvoidsNPlusOne:
  @pytest.mark.asyncio
  async def test_find_recalls_for_medications_called_exactly_once(self) -> None:
    """N=5 medication 입력 시 repo.find_recalls_for_medications 1회만 호출."""
    from app.services.medication_service import MedicationService

    service = MedicationService()
    profile_id = uuid4()
    meds = [_make_medication(f"약{i}") for i in range(5)]

    service.repository.get_all_by_profile = AsyncMock(return_value=meds)
    service._verify_profile_ownership = AsyncMock()

    with patch("app.services.medication_service.DrugRecallRepository") as repo_cls:
      batch_mock = AsyncMock(return_value={})
      repo_cls.return_value.find_recalls_for_medications = batch_mock
      await service.list_medications_with_recall_status_with_owner_check(profile_id, account_id=uuid4())

    assert batch_mock.await_count == 1


# ── 같은 medication 에 매칭 2건 (§8) ───────────────────────────────


class TestBatchSameMedicationMultipleRecalls:
  @pytest.mark.asyncio
  async def test_label_picks_latest_date_and_payload_keeps_all_items(self) -> None:
    """§8 동일 ITEM_SEQ 2 사유 → label 에 최근 날짜, alert_payload.items 길이 2."""
    from app.services.medication_service import MedicationService

    service = MedicationService()
    profile_id = uuid4()
    med = _make_medication("오미크론케어연고")

    older = MagicMock(
      item_seq="202504018",
      product_name="오미크론케어연고",
      entrps_name="(주)오미크론바이오",
      recall_reason="포장재 불량(코팅 벗겨짐)",
      recall_command_date="20260326",
      sale_stop_yn="N",
    )
    newer = MagicMock(
      item_seq="202504018",
      product_name="오미크론케어연고",
      entrps_name="(주)오미크론바이오",
      recall_reason="안정성시험 일부항목(성상)",
      recall_command_date="20260330",
      sale_stop_yn="N",
    )

    service.repository.get_all_by_profile = AsyncMock(return_value=[med])
    service._verify_profile_ownership = AsyncMock()

    with patch("app.services.medication_service.DrugRecallRepository") as repo_cls:
      repo_cls.return_value.find_recalls_for_medications = AsyncMock(return_value={med.id: [older, newer]})
      results = await service.list_medications_with_recall_status_with_owner_check(profile_id, account_id=uuid4())

    status = results[0].recall_status
    assert status is not None
    # 라벨 텍스트의 날짜 분기는 최신 row 기준
    assert status.recall_command_date == "20260330"
    # 모달 재발화용 alert_payload 에 매칭 row 모두 보존
    assert len(status.alert_payload.items) == 2


# ── 라벨 클릭 모달 재발화 — alert_payload 구조 일관성 ───────────────


class TestRecallStatusAlertPayloadParityWithEntryAlert:
  @pytest.mark.asyncio
  async def test_alert_payload_matches_recall_alert_shape(self) -> None:
    """recall_status.alert_payload 와 등록 시점 recall_alert 가 동일 구조 (RecallAlertDTO).

    라벨 클릭 → 동일 모달 재발화의 핵심 회귀 가드.
    """
    from app.services.medication_service import MedicationService

    service = MedicationService()
    profile_id = uuid4()
    med = _make_medication("데모라니티딘정150밀리그램")
    recall = _make_recall_row(0)  # §1 NDMA critical

    service.repository.get_all_by_profile = AsyncMock(return_value=[med])
    service._verify_profile_ownership = AsyncMock()

    with patch("app.services.medication_service.DrugRecallRepository") as repo_cls:
      repo_cls.return_value.find_recalls_for_medications = AsyncMock(return_value={med.id: [recall]})
      results = await service.list_medications_with_recall_status_with_owner_check(profile_id, account_id=uuid4())

    status = results[0].recall_status
    assert status is not None
    # alert_payload 는 RecallAlertDTO — 등록 시점 recall_alert 와 동일 클래스.
    from app.dtos.recall import RecallAlertDTO

    assert isinstance(status.alert_payload, RecallAlertDTO)
    assert status.alert_payload.severity == "critical"
    assert len(status.alert_payload.items) == 1
    assert status.alert_payload.items[0].item_seq == "202504001"

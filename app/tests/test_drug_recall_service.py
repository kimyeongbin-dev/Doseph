"""DrugRecallService 단위 테스트 (Phase 7 Step 4).

검증 포인트 (§14.5 시드 + 발견 #1, #3 반영):
- _transform_item: API row → repository dict 매핑
- _apply_filters: 3중 필터 (item_seq IN medicine_info / NON_DRUG / HOSPITAL_ONLY)
- 환경변수 RECALL_FILTER_NON_DRUG=False 토글 시 2차 필터 비활성
- env-driven endpoint URL (메서드명 변경 시 URL 반영)
- 복합 UNIQUE 충돌 회피 — `202007244` 3건 모두 적재됨
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.tests.mock_data.drug_recall_seed import SEED_RECALL_30

# ── _transform_item ──────────────────────────────────────────────────


class TestTransformItem:
  def test_maps_basic_fields(self) -> None:
    from app.services.drug_recall_service import DrugRecallService

    api_row = SEED_RECALL_30[19]  # 마데카솔케어연고
    out = DrugRecallService._transform_item(api_row)

    assert out["item_seq"] == "200903973"
    assert out["product_name"] == "마데카솔케어연고"
    assert out["entrps_name"] == "동국제약(주)"
    assert out["recall_reason"] == "포장재 불량(코팅 벗겨짐)"
    assert out["recall_command_date"] == "20260401"
    assert out["sale_stop_yn"] == "N"  # default
    assert out["is_hospital_only"] is False
    assert out["is_non_drug"] is False

  def test_hospital_only_flag_set_for_injection(self) -> None:
    from app.services.drug_recall_service import DrugRecallService

    api_row = SEED_RECALL_30[15]  # 부광미다졸람주사
    out = DrugRecallService._transform_item(api_row)
    assert out["is_hospital_only"] is True

  def test_non_drug_flag_set_for_toothpaste(self) -> None:
    from app.services.drug_recall_service import DrugRecallService

    api_row = SEED_RECALL_30[1]  # 그린파인치약
    out = DrugRecallService._transform_item(api_row)
    assert out["is_non_drug"] is True


# ── _apply_filters: 3중 필터 ─────────────────────────────────────────


class TestApplyFilters:
  @pytest.fixture
  def service(self) -> Any:
    from app.services.drug_recall_service import DrugRecallService

    return DrugRecallService(api_key="dummy")

  @pytest.mark.asyncio
  async def test_non_drug_blocked_by_default(self, service: Any) -> None:
    """RECALL_FILTER_NON_DRUG=True 면 치약 회수가 걸러진다."""
    valid_seqs = {item["ITEM_SEQ"] for item in SEED_RECALL_30}
    with patch("app.services.drug_recall_service.config") as cfg:
      cfg.RECALL_FILTER_NON_DRUG = True
      kept = await service._apply_filters(SEED_RECALL_30, valid_seqs)

    names = [item["PRDUCT"] for item in kept]
    assert not any("치약" in n for n in names), names

  @pytest.mark.asyncio
  async def test_non_drug_kept_when_toggle_off(self, service: Any) -> None:
    """RECALL_FILTER_NON_DRUG=False 면 치약도 통과 (의약외품 영역 확장 시나리오)."""
    valid_seqs = {item["ITEM_SEQ"] for item in SEED_RECALL_30}
    with patch("app.services.drug_recall_service.config") as cfg:
      cfg.RECALL_FILTER_NON_DRUG = False
      kept = await service._apply_filters(SEED_RECALL_30, valid_seqs)

    names = [item["PRDUCT"] for item in kept]
    assert any("치약" in n for n in names)

  @pytest.mark.asyncio
  async def test_hospital_only_blocked(self, service: Any) -> None:
    """주사제는 항상 차단."""
    valid_seqs = {item["ITEM_SEQ"] for item in SEED_RECALL_30}
    with patch("app.services.drug_recall_service.config") as cfg:
      cfg.RECALL_FILTER_NON_DRUG = True
      kept = await service._apply_filters(SEED_RECALL_30, valid_seqs)

    names = [item["PRDUCT"] for item in kept]
    assert "부광미다졸람주사" not in names

  @pytest.mark.asyncio
  async def test_item_seq_match_required_when_medicine_info_seeded(self, service: Any) -> None:
    """medicine_info 가 비어있지 않으면 그 안에 있는 item_seq 만 통과."""
    # 마데카솔만 medicine_info 에 등록되어 있는 상황
    valid_seqs = {"200903973"}
    with patch("app.services.drug_recall_service.config") as cfg:
      cfg.RECALL_FILTER_NON_DRUG = True
      kept = await service._apply_filters(SEED_RECALL_30, valid_seqs)

    seqs = {item["ITEM_SEQ"] for item in kept}
    assert seqs == {"200903973"}

  @pytest.mark.asyncio
  async def test_no_match_filter_disabled_when_seqs_empty(self, service: Any) -> None:
    """medicine_info 가 텅 비어 있으면 1차 필터를 비활성 (모든 row 보존)."""
    with patch("app.services.drug_recall_service.config") as cfg:
      cfg.RECALL_FILTER_NON_DRUG = False
      kept = await service._apply_filters(SEED_RECALL_30, set())

    # 주사 한 건만 hospital_only 로 빠지므로 30 - 1 = 29 (다른 차단 없음)
    # is_hospital_only 매칭은 _apply_filters 단계에서도 수행
    assert len(kept) == 29

  @pytest.mark.asyncio
  async def test_composite_unique_seed_preserved(self, service: Any) -> None:
    """🔴 `202007244` 3건 모두 필터를 통과해 적재 후보로 남는지.

    본 테스트는 RECALL_FILTER_NON_DRUG=False (치약도 통과) 가정.
    """
    valid_seqs = {item["ITEM_SEQ"] for item in SEED_RECALL_30}
    with patch("app.services.drug_recall_service.config") as cfg:
      cfg.RECALL_FILTER_NON_DRUG = False
      kept = await service._apply_filters(SEED_RECALL_30, valid_seqs)

    same_seq = [item for item in kept if item["ITEM_SEQ"] == "202007244"]
    assert len(same_seq) == 3


# ── env-driven endpoint URL ──────────────────────────────────────────


class TestEndpointFromEnv:
  @pytest.mark.asyncio
  async def test_list_url_uses_env_method(self) -> None:
    """env 의 RECALL_LIST_METHOD 가 URL 마지막 path-segment 로 사용됨."""
    from app.services.drug_recall_service import DrugRecallService

    with patch("app.services.drug_recall_service.config") as cfg:
      cfg.DATA_GO_KR_RECALL_BASE_URL = "http://example/path"
      cfg.DATA_GO_KR_RECALL_LIST_METHOD = "getMdcinRtrvlSleStpgeList99"
      cfg.DATA_GO_KR_RECALL_API_KEY = "k"
      cfg.DATA_GO_KR_API_KEY = None
      cfg.RECALL_FILTER_NON_DRUG = True

      svc = DrugRecallService(api_key="k")
      assert svc._list_url.endswith("/getMdcinRtrvlSleStpgeList99")


# ── sync 통합 시나리오 ───────────────────────────────────────────────


class TestSyncFlow:
  @pytest.mark.asyncio
  async def test_sync_records_data_sync_log_on_success(self) -> None:
    """sync 가 정상 종료되면 DataSyncLog SUCCESS row INSERT."""
    from app.services.drug_recall_service import DrugRecallService

    repo = MagicMock(bulk_upsert=AsyncMock(return_value={"inserted": 5, "updated": 0}))
    svc = DrugRecallService(api_key="k", repository=repo)

    with (
      patch.object(svc, "_fetch_all_pages", new=AsyncMock(return_value=SEED_RECALL_30)),
      patch.object(svc, "_load_valid_item_seqs", new=AsyncMock(return_value={"200903973"})),
      patch("app.services.drug_recall_service.DataSyncLog.create", new=AsyncMock()) as create,
      patch("app.services.drug_recall_service.config") as cfg,
    ):
      cfg.RECALL_FILTER_NON_DRUG = True
      stats = await svc.sync()

    assert stats == {"fetched": 30, "inserted": 5, "updated": 0}
    create.assert_awaited_once()
    kw = create.await_args.kwargs
    assert kw["sync_type"] == "drug_recalls"
    assert kw["status"] == "SUCCESS"

  @pytest.mark.asyncio
  async def test_sync_records_failure_on_http_error(self) -> None:
    """API 호출 실패 시 FAILED row INSERT 후 예외 재발."""
    import httpx

    from app.services.drug_recall_service import DrugRecallService

    svc = DrugRecallService(api_key="k", repository=MagicMock())

    async def boom() -> list[dict]:
      req = httpx.Request("GET", "http://x/y")
      raise httpx.HTTPStatusError("503", request=req, response=httpx.Response(503, request=req))

    with (
      patch.object(svc, "_fetch_all_pages", new=AsyncMock(side_effect=boom)),
      patch("app.services.drug_recall_service.DataSyncLog.create", new=AsyncMock()) as create,
      pytest.raises(httpx.HTTPStatusError),
    ):
      await svc.sync()

    kw = create.await_args.kwargs
    assert kw["status"] == "FAILED"

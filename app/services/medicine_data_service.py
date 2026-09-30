"""Medicine data synchronization service module.

This module provides business logic for fetching drug data from the
Food and Drug Safety public API and synchronizing it with the local
medicine_info database using incremental update strategy.

Reference:
    - API Docs: data.go.kr dDrugPrdtPrmsnInfoService07 (2025)
    - Best Practice: data.go.kr bulk sync pattern with httpx pagination
"""

from collections.abc import AsyncIterator
from datetime import UTC, datetime
import json
import logging
from pathlib import Path

import httpx

from app.models.data_sync_log import DataSyncLog
from app.repositories.medicine_info_repository import MedicineInfoRepository
from app.repositories.medicine_ingredient_repository import MedicineIngredientRepository
from app.services.medicine_doc_parser import (
  flatten_doc_plaintext,
  parse_nb_categories,
  parse_ud_plaintext,
)
from app.utils.medicine_filters import is_hospital_only

logger = logging.getLogger(__name__)

# ── 공공데이터 API 설정 ──────────────────────────────────────────────
# 식약처 의약품 허가정보 서비스 (DrugPrdtPrmsnInfoService07)
_BASE_URL = "https://apis.data.go.kr/1471000/DrugPrdtPrmsnInfoService07"
_DETAIL_ENDPOINT = f"{_BASE_URL}/getDrugPrdtPrmsnDtlInq06"  # 허가 상세정보
_INGREDIENT_ENDPOINT = f"{_BASE_URL}/getDrugPrdtMcpnDtlInq07"  # 약품-성분 1:N

# ── 백업 저장 경로 및 HTTP 설정 ──────────────────────────────────────
_DATA_DIR = Path(__file__).resolve().parent.parent.parent / "ai_worker" / "data"
_REQUEST_TIMEOUT = 30.0
_MAX_ROWS_PER_PAGE = 100


def _split_nb_to_columns(nb_xml: str | None) -> dict:
  """NB_DOC_DATA XML 을 medicine_info 의 precautions/side_effects 컬럼 dict 로 변환.

  parse_nb_categories 의 (dict, list) 튜플을 컬럼 매핑 dict 로 wrap. None / 빈 결과는
  None 으로 통일해 NULL 보장.
  """
  precautions, side_effects = parse_nb_categories(nb_xml)
  return {
    "precautions": precautions or None,
    "side_effects": side_effects or None,
  }


class MedicineDataService:
  """Service for public API drug data collection and synchronization.

  Handles full and incremental sync operations between
  the public API and the local medicine_info database.
  """

  def __init__(self, api_key: str) -> None:
    self.api_key = api_key
    self.repository = MedicineInfoRepository()
    self.ingredient_repository = MedicineIngredientRepository()

  # ── 메인 동기화 메서드 (page-streaming) ─────────────────────────
  # 전체 흐름:
  #   1. 파라미터 구성 (전체 or 증분)
  #   2. ndjson 백업 파일 open (페이지마다 한 줄씩 append, 메모리 X)
  #   3. _iter_pages 로 페이지 단위 (100건) 수신
  #      → 병원전용 skip + 컬럼 매핑 + 3컬럼 정합 필터
  #      → 페이지 단위 bulk_upsert 후 즉시 discard (raw 누적 X)
  #   4. 동기화 결과 로그 기록 (_record_sync_log)
  # 메모리 피크: 1 페이지(100 items) + 페이지의 transformed 만큼.

  async def sync(self, full_sync: bool = False) -> dict[str, int]:
    """Execute full or incremental data synchronization.

    Page-streaming 방식. raw_items 전체를 메모리에 적재하지 않고
    100건 단위 page 로 받아 즉시 transform + UPSERT 후 discard.

    Args:
        full_sync: If True, fetches all records. If False,
            fetches only records changed since last sync.

    Returns:
        Dictionary with sync statistics.

    Raises:
        httpx.HTTPStatusError: If API request fails.
    """
    # Step 1: 전체/증분에 따라 API 요청 파라미터 구성
    params = await self._build_params(full_sync)
    sync_start = datetime.now(tz=UTC)

    logger.info(
      "Starting %s sync for medicine_info (page-streaming)",
      "full" if full_sync else "incremental",
    )

    fetched = 0
    inserted = 0
    updated = 0
    hospital_skipped = 0
    empty_doc_skipped = 0
    is_hospital = self._is_hospital_only_injectable
    transform = self._transform_item

    # Step 2: ndjson 백업 파일 open (page 단위 streaming append)
    _DATA_DIR.mkdir(parents=True, exist_ok=True)
    backup_path = _DATA_DIR / f"medicines_{sync_start.strftime('%Y%m%d_%H%M%S')}.ndjson"

    try:
      with backup_path.open("w", encoding="utf-8") as backup_file:
        # Step 3: 페이지 단위 수신 → 즉시 변환/upsert
        async for page_items in self._iter_pages(params):
          fetched += len(page_items)

          # 백업: 한 줄씩 append (메모리 X)
          for item in page_items:
            backup_file.write(json.dumps(item, ensure_ascii=False))
            backup_file.write("\n")

          # 변환 + 정합 필터
          transformed: list[dict] = []
          for item in page_items:
            if is_hospital(item):
              hospital_skipped += 1
              continue
            row = transform(item)
            if not (row["dosage"] and row["precautions"] and row["side_effects"]):
              empty_doc_skipped += 1
              continue
            transformed.append(row)

          if transformed:
            stats = await self.repository.bulk_upsert(transformed)
            inserted += stats["inserted"]
            updated += stats["updated"]
    except httpx.HTTPStatusError:
      await self._record_sync_log(
        sync_start,
        fetched,
        inserted,
        updated,
        "FAILED",
        "API request failed",
      )
      raise

    if fetched == 0:
      logger.info("No new data to sync")
      backup_path.unlink(missing_ok=True)  # 빈 백업 파일 정리
      await self._record_sync_log(sync_start, 0, 0, 0, "SUCCESS")
      return {"fetched": 0, "inserted": 0, "updated": 0}

    logger.info(
      "Filtered: raw=%d, hospital_only=%d, empty_doc=%d, upserted=%d (inserted=%d, updated=%d)",
      fetched,
      hospital_skipped,
      empty_doc_skipped,
      inserted + updated,
      inserted,
      updated,
    )
    logger.info("Saved backup: %s", backup_path)

    # Step 4: 동기화 결과를 data_sync_log 테이블에 기록
    await self._record_sync_log(sync_start, fetched, inserted, updated, "SUCCESS")

    logger.info("Sync complete: fetched=%d, inserted=%d, updated=%d", fetched, inserted, updated)
    return {"fetched": fetched, "inserted": inserted, "updated": updated}

  # ── 약품-성분(Mcpn07) 동기화 (page-streaming) ───────────────────────
  # 흐름:
  #   1. Mcpn07 endpoint 페이지 단위 수신
  #   2. 페이지 단위 ITEM_SEQ → medicine_info_id batch lookup
  #   3. 매칭 안 되는 row 는 skip (medicine_info 미등록 약품)
  #   4. 페이지 단위 (medicine_info_id, mtral_sn) UPSERT 후 discard

  async def sync_ingredients(self) -> dict[str, int]:
    """식약처 Mcpn07 응답을 받아 medicine_ingredient 테이블을 채움.

    Page-streaming 방식. 페이지(100건) 단위로 lookup + transform + upsert
    후 즉시 discard 하여 메모리 누적을 막는다. medicine_info 가 먼저
    sync 되어 있어야 FK 해석 가능. 모르는 item_seq 는 skip.

    Returns:
        {"fetched": n, "inserted": i, "updated": u, "skipped": s}.
    """
    params = {
      "serviceKey": self.api_key,
      "type": "json",
      "numOfRows": _MAX_ROWS_PER_PAGE,
      "pageNo": 1,
    }
    logger.info("Starting ingredient sync (Mcpn07, page-streaming)")

    fetched = 0
    inserted = 0
    updated = 0
    skipped = 0

    async for page_items in self._iter_pages(params, endpoint=_INGREDIENT_ENDPOINT):
      fetched += len(page_items)

      # 페이지 단위 ITEM_SEQ → medicine_info.id batch lookup
      item_seqs = [item.get("ITEM_SEQ", "") for item in page_items]
      id_map = await self.ingredient_repository.get_medicine_id_map(item_seqs)

      transformed: list[dict] = []
      for item in page_items:
        row = self._transform_ingredient_item(item, id_map)
        if row is None:
          skipped += 1
          continue
        transformed.append(row)

      if transformed:
        stats = await self.ingredient_repository.bulk_upsert(transformed)
        inserted += stats["inserted"]
        updated += stats["updated"]

    if fetched == 0:
      logger.info("No ingredient data to sync")
      return {"fetched": 0, "inserted": 0, "updated": 0, "skipped": 0}

    if inserted + updated == 0:
      logger.warning("All ingredient rows skipped — medicine_info empty?")

    logger.info(
      "Ingredient sync complete: fetched=%d, inserted=%d, updated=%d, skipped=%d",
      fetched,
      inserted,
      updated,
      skipped,
    )
    return {"fetched": fetched, "inserted": inserted, "updated": updated, "skipped": skipped}

  # ── API 파라미터 구성 (전체: 필터 없음 / 증분: start_change_date 설정) ──

  async def _build_params(self, full_sync: bool) -> dict:
    """Build API request parameters for full or incremental sync.

    Args:
        full_sync: Whether to perform full sync.

    Returns:
        Dictionary of API request parameters.
    """
    params: dict = {
      "serviceKey": self.api_key,
      "type": "json",
      "numOfRows": _MAX_ROWS_PER_PAGE,
      "pageNo": 1,
    }

    if full_sync:
      return params

    last_date = await self.repository.get_last_sync_date()
    if last_date:
      params["start_change_date"] = last_date
      logger.info("Incremental sync from date: %s", last_date)
    else:
      logger.info("No previous sync found, falling back to full sync")

    return params

  # ── 페이징 streaming (page 단위 yield, 메모리 누적 없음) ───────────

  async def _iter_pages(
    self,
    params: dict,
    endpoint: str = _DETAIL_ENDPOINT,
  ) -> AsyncIterator[list[dict]]:
    """페이지 단위로 API 응답 items 를 yield.

    호출자는 한 페이지(100건) 처리 후 즉시 discard 가능 — raw 누적이
    없어 메모리 피크가 페이지 크기로 제한된다.

    Args:
        params: Base API request parameters (mutated: pageNo).
        endpoint: API endpoint URL (default: Dtl06 — 허가 상세).

    Yields:
        한 페이지의 item dict 리스트.
    """
    async with httpx.AsyncClient(timeout=_REQUEST_TIMEOUT) as client:
      page = 1
      accumulated = 0
      total_count: int | None = None
      while True:
        params["pageNo"] = page
        response = await client.get(endpoint, params=params)
        response.raise_for_status()

        body = response.json().get("body", {})
        items = body.get("items", [])
        if not items:
          break

        if total_count is None:
          total_count = body.get("totalCount", 0)
        accumulated += len(items)

        logger.info(
          "Fetched page %d: %d items (total so far: %d/%d)",
          page,
          len(items),
          accumulated,
          total_count,
        )

        yield items

        if total_count and accumulated >= total_count:
          break
        page += 1

  # ── 필터링: 병원 전용 주사제 판별 ──────────────────────────────
  # 흐름: API row → ITEM_NAME 추출 → 공용 medicine_filters 위임

  @staticmethod
  def _is_hospital_only_injectable(item: dict) -> bool:
    """Check if the item is a hospital-only injectable drug.

    Thin wrapper that delegates to the reusable predicate in
    ``app.utils.medicine_filters``. Kept as a method to preserve
    the existing call signature used by `fetch_sample.py` and
    downstream tests.

    Args:
        item: Raw API response item dictionary (Dtl06 schema).

    Returns:
        True if the item should be excluded from the consumer DB.
    """
    return is_hospital_only(item.get("ITEM_NAME", ""))

  # ── API 응답 필드 -> DB 모델 필드 매핑 변환 ────────────────────

  @staticmethod
  def _transform_item(item: dict) -> dict:
    """Transform raw Dtl06 API item to medicine_info model field format.

    Maps every Dtl06 response field with a corresponding MedicineInfo
    column. XML document bodies (EE_DOC_DATA, UD_DOC_DATA, NB_DOC_DATA)
    are intentionally NOT transformed here — they are consumed by a
    later chunking step that produces medicine_chunk rows.

    Args:
        item: Raw API response item dictionary.

    Returns:
        Dictionary with model-compatible field names and values.
        Missing or empty-string API fields are normalized to None.
    """
    return {
      # 기본 식별
      "item_seq": item.get("ITEM_SEQ", ""),
      "medicine_name": item.get("ITEM_NAME", ""),
      "item_eng_name": item.get("ITEM_ENG_NAME") or None,
      "entp_name": item.get("ENTP_NAME") or None,
      "product_type": item.get("PRDUCT_TYPE") or None,
      "spclty_pblc": item.get("SPCLTY_PBLC") or None,
      "permit_date": item.get("ITEM_PERMIT_DATE") or None,
      "cancel_name": item.get("CANCEL_NAME") or None,
      # 성분/저장/메타
      "main_item_ingr": item.get("MAIN_ITEM_INGR") or None,
      "storage_method": item.get("STORAGE_METHOD") or None,
      "edi_code": item.get("EDI_CODE") or None,
      "bizrno": item.get("BIZRNO") or None,
      "change_date": item.get("CHANGE_DATE") or None,
      "chart": item.get("CHART") or None,
      "material_name": item.get("MATERIAL_NAME") or None,
      "valid_term": item.get("VALID_TERM") or None,
      # pack_unit max_length=2048 — 식약처 raw 가 종종 2k+ 콤마나열을 보내므로 잘라냄
      "pack_unit": (item.get("PACK_UNIT") or "")[:2048] or None,
      "atc_code": item.get("ATC_CODE") or None,
      # 허가 문서 PDF URL (EE_DOC_ID/UD_DOC_ID/NB_DOC_ID → *_doc_url)
      "ee_doc_url": item.get("EE_DOC_ID") or None,
      "ud_doc_url": item.get("UD_DOC_ID") or None,
      "nb_doc_url": item.get("NB_DOC_ID") or None,
      # 원본 DOC XML (재임베딩/재청크 시 API 재호출 회피용 스냅샷)
      "ee_doc_data": item.get("EE_DOC_DATA") or None,
      "ud_doc_data": item.get("UD_DOC_DATA") or None,
      "nb_doc_data": item.get("NB_DOC_DATA") or None,
      # UI 표시용 평문 / 카테고리 분류 (XML → drug-info 응답 직결)
      "efficacy": flatten_doc_plaintext(item.get("EE_DOC_DATA")) or None,
      "dosage": parse_ud_plaintext(item.get("UD_DOC_DATA")) or None,
      **_split_nb_to_columns(item.get("NB_DOC_DATA")),
      # 동기화 타임스탬프 (tz-aware UTC — CLAUDE.md 4.2)
      "last_synced_at": datetime.now(tz=UTC),
    }

  # ── Mcpn07 응답 -> medicine_ingredient row 변환 ─────────────────

  @staticmethod
  def _transform_ingredient_item(item: dict, id_map: dict[str, int]) -> dict | None:
    """Mcpn07 한 row 를 medicine_ingredient UPSERT 입력 dict 로 변환.

    Args:
        item: Mcpn07 API item (ITEM_SEQ / MTRAL_SN / MTRAL_NM 등).
        id_map: ITEM_SEQ -> MedicineInfo.id 매핑.

    Returns:
        UPSERT dict 또는 None (medicine_info 미존재 / 필수 필드 누락 시).
    """
    item_seq = item.get("ITEM_SEQ", "")
    medicine_info_id = id_map.get(item_seq)
    if medicine_info_id is None:
      return None

    try:
      mtral_sn = int(item.get("MTRAL_SN") or 0)
    except (ValueError, TypeError):
      return None

    mtral_name = (item.get("MTRAL_NM") or "").strip()
    if not mtral_name or mtral_sn <= 0:
      return None

    return {
      "medicine_info_id": medicine_info_id,
      "mtral_sn": mtral_sn,
      "mtral_code": item.get("MTRAL_CODE") or None,
      "mtral_name": mtral_name,
      # main_ingr_eng max_length=256 — 식약처 raw 가 슬래시 나열로 종종 256+ 보내므로 잘라냄
      "main_ingr_eng": (item.get("MAIN_INGR_ENG") or "")[:256] or None,
      "quantity": str(item.get("QNT")) if item.get("QNT") not in (None, "") else None,
      "unit": item.get("INGD_UNIT_CD") or None,
    }

  # ── 동기화 결과 로그 기록 (data_sync_log 테이블) ────────────────

  @staticmethod
  async def _record_sync_log(
    sync_date: datetime,
    total_fetched: int,
    total_inserted: int,
    total_updated: int,
    status: str,
    error_message: str | None = None,
  ) -> DataSyncLog:
    """Record sync operation result in DataSyncLog.

    Args:
        sync_date: When the sync started.
        total_fetched: Number of records fetched from API.
        total_inserted: Number of new records inserted.
        total_updated: Number of existing records updated.
        status: Sync result (SUCCESS or FAILED).
        error_message: Error details if status is FAILED.

    Returns:
        Created DataSyncLog instance.
    """
    return await DataSyncLog.create(
      sync_type="medicine_info",
      sync_date=sync_date,
      total_fetched=total_fetched,
      total_inserted=total_inserted,
      total_updated=total_updated,
      status=status,
      error_message=error_message,
    )

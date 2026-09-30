"""Drug recall service module (Phase 7).

Business logic for synchronizing MFDS recall and sale-stop notices
into the local `drug_recalls` table. Mirrors the design of
`MedicineDataService` but with three Phase-7-specific concerns:

1. **Endpoint method names are env-driven** (§14.5 finding #3) — the
   path-tail (`getMdcinRtrvlSleStpgeList03` etc.) is read from
   `app.core.config` so a future MFDS bump (`…04`) needs no code change.
2. **3-stage filter** before persistence:
   - Stage 1: `item_seq` must exist in `medicine_info` (strongest;
     consumer-oriented).
   - Stage 2: non-drug keyword block (toothpaste, sanitary pads, …),
     toggleable via `RECALL_FILTER_NON_DRUG`.
   - Stage 3: hospital-only keyword block (injectables, IV fluids).
3. **Composite UNIQUE-aware bulk_upsert** — `DrugRecallRepository`
   already handles `(item_seq, recall_command_date, recall_reason)`
   correctly so multiple reasons for the same product on the same day
   are preserved.

DataSyncLog entries are recorded under `sync_type="drug_recalls"` so
the existing `data_sync_log` infrastructure (admin UI / cron audit)
covers this without schema additions.
"""

from __future__ import annotations

from datetime import UTC, datetime
import logging

import httpx

from app.core.config import config
from app.models.data_sync_log import DataSyncLog
from app.models.medicine_info import MedicineInfo
from app.repositories.drug_recall_repository import DrugRecallRepository
from app.utils.medicine_filters import is_hospital_only, is_non_drug_product

logger = logging.getLogger(__name__)

_REQUEST_TIMEOUT = 30.0
_MAX_ROWS_PER_PAGE = 100


class DrugRecallService:
  """Service for syncing MFDS recall data into `drug_recalls`."""

  def __init__(
    self,
    api_key: str | None = None,
    repository: DrugRecallRepository | None = None,
  ) -> None:
    self.api_key = api_key or config.DATA_GO_KR_RECALL_API_KEY or config.DATA_GO_KR_API_KEY
    self.repository = repository or DrugRecallRepository()

  # ── 메인 동기화 ───────────────────────────────────────────────────
  # 흐름: API 페이징 수집 -> 3중 필터 -> bulk_upsert -> DataSyncLog 기록

  async def sync(self) -> dict[str, int]:
    """Fetch + filter + upsert MFDS recall data.

    Returns:
        ``{"fetched": int, "inserted": int, "updated": int}``.
    """
    sync_start = datetime.now(tz=UTC)
    logger.info("Starting drug_recalls sync")

    try:
      raw_items = await self._fetch_all_pages()
    except httpx.HTTPStatusError:
      await self._record_sync_log(sync_start, 0, 0, 0, "FAILED", "API request failed")
      raise

    if not raw_items:
      await self._record_sync_log(sync_start, 0, 0, 0, "SUCCESS")
      return {"fetched": 0, "inserted": 0, "updated": 0}

    valid_seqs = await self._load_valid_item_seqs()
    filtered = await self._apply_filters(raw_items, valid_seqs)
    transformed = [self._transform_item(item) for item in filtered]

    stats = await self.repository.bulk_upsert(transformed)
    await self._record_sync_log(
      sync_start,
      len(raw_items),
      stats["inserted"],
      stats["updated"],
      "SUCCESS",
    )

    logger.info(
      "drug_recalls sync complete: fetched=%d kept=%d inserted=%d updated=%d",
      len(raw_items),
      len(filtered),
      stats["inserted"],
      stats["updated"],
    )
    return {
      "fetched": len(raw_items),
      "inserted": stats["inserted"],
      "updated": stats["updated"],
    }

  # ── HTTP 페이징 ──────────────────────────────────────────────────

  @property
  def _list_url(self) -> str:
    """Endpoint URL is composed from env-driven base + method."""
    return f"{config.DATA_GO_KR_RECALL_BASE_URL}/{config.DATA_GO_KR_RECALL_LIST_METHOD}"

  async def _fetch_all_pages(self) -> list[dict]:
    """Fetch every recall row across all pages.

    The MFDS recall API never exceeds a few hundred rows so we
    stream them all in one call. Pagination loop keeps the same
    shape as `MedicineDataService._fetch_all_pages` for parity.
    """
    all_items: list[dict] = []
    params: dict = {
      "serviceKey": self.api_key,
      "type": "json",
      "numOfRows": _MAX_ROWS_PER_PAGE,
      "pageNo": 1,
    }

    async with httpx.AsyncClient(timeout=_REQUEST_TIMEOUT) as client:
      page = 1
      while True:
        params["pageNo"] = page
        response = await client.get(self._list_url, params=params)
        response.raise_for_status()

        body = response.json().get("body", {})
        items = body.get("items", [])
        if isinstance(items, dict):
          items = [items]

        if not items:
          break

        all_items.extend(items)
        total_count = body.get("totalCount", 0)
        logger.info(
          "drug_recalls fetched page %d: %d items (%d/%d)",
          page,
          len(items),
          len(all_items),
          total_count,
        )

        if len(all_items) >= total_count:
          break
        page += 1

    return all_items

  # ── 3중 필터 ─────────────────────────────────────────────────────

  async def _load_valid_item_seqs(self) -> set[str]:
    """Return the set of `medicine_info.item_seq` values (Stage-1 filter)."""
    rows = await MedicineInfo.all().values("item_seq")
    return {row["item_seq"] for row in rows if row.get("item_seq")}

  async def _apply_filters(self, raw_items: list[dict], valid_seqs: set[str]) -> list[dict]:
    """Apply Stage 1/2/3 filters in order.

    Stage 1: `item_seq` in `medicine_info`. If empty, keep going so
        we can still surface unmatched rows (recall happened on a
        drug we have not synced yet) — but always block if Stage 2
        or Stage 3 hits.
    """
    kept: list[dict] = []
    skip_no_match = bool(valid_seqs)
    non_drug_filter_enabled = config.RECALL_FILTER_NON_DRUG
    skipped_non_drug = 0
    skipped_hospital = 0
    skipped_no_match = 0

    for item in raw_items:
      name = item.get("PRDUCT") or ""
      seq = item.get("ITEM_SEQ") or ""
      if not name or not seq:
        continue

      if non_drug_filter_enabled and is_non_drug_product(name):
        skipped_non_drug += 1
        continue

      if is_hospital_only(name):
        skipped_hospital += 1
        continue

      if skip_no_match and seq not in valid_seqs:
        skipped_no_match += 1
        continue

      kept.append(item)

    logger.info(
      "drug_recalls filters: kept=%d skipped_non_drug=%d skipped_hospital=%d skipped_no_match=%d",
      len(kept),
      skipped_non_drug,
      skipped_hospital,
      skipped_no_match,
    )
    return kept

  # ── API 응답 → 모델 dict 변환 ───────────────────────────────────

  @staticmethod
  def _transform_item(item: dict) -> dict:
    """Map raw API row to repository-friendly dict.

    `entrps_name_normalized` is computed by the repository inside
    `bulk_upsert`, so we don't double-normalize here.
    """
    name = item.get("PRDUCT") or ""
    return {
      "item_seq": item.get("ITEM_SEQ") or "",
      "std_code": item.get("STDR_CODE") or None,
      "product_name": name,
      "entrps_name": item.get("ENTRPS") or "",
      "recall_reason": item.get("RTRVL_RESN") or "",
      "recall_command_date": item.get("RECALL_COMMAND_DATE") or "",
      "sale_stop_yn": item.get("SALE_STOP_YN") or "N",
      "is_hospital_only": is_hospital_only(name),
      "is_non_drug": is_non_drug_product(name),
    }

  # ── DataSyncLog 기록 ────────────────────────────────────────────

  @staticmethod
  async def _record_sync_log(
    sync_start: datetime,
    total_fetched: int,
    total_inserted: int,
    total_updated: int,
    status: str,
    error_message: str | None = None,
  ) -> None:
    """Persist a sync attempt to `data_sync_log` with sync_type=drug_recalls."""
    await DataSyncLog.create(
      sync_type="drug_recalls",
      sync_date=sync_start,
      total_fetched=total_fetched,
      total_inserted=total_inserted,
      total_updated=total_updated,
      status=status,
      error_message=error_message,
    )

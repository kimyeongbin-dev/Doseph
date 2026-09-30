"""Drug recall repository module (Phase 7).

Data access layer for the `drug_recalls` table. Operates against the
composite-UNIQUE key `(item_seq, recall_command_date, recall_reason)`
and the normalized manufacturer column `entrps_name_normalized`
populated by `app.utils.company_name_normalizer.normalize_company_name`.

Public methods:
    - bulk_upsert: ingest API rows, populating both raw and normalized
      manufacturer columns.
    - find_by_item_seqs: Q1 — recalls whose `item_seq` matches the
      user's medication codes.
    - find_by_manufacturers: Q2 — recalls whose normalized manufacturer
      matches the normalized user manufacturer set.
    - diff_new_recalls: cron diff — rows created after a given moment.
    - find_match: F3 / cron alert match — `item_seq` first, then
      `product_name` ILIKE fallback (S7).
"""

from __future__ import annotations

from datetime import datetime
import logging
from typing import TYPE_CHECKING, Any

from app.models.drug_recall import DrugRecall
from app.models.medicine_info import MedicineInfo
from app.utils.company_name_normalizer import normalize_company_name
from app.utils.product_name_normalizer import normalize_product_name

if TYPE_CHECKING:  # pragma: no cover - typing only
  from collections.abc import Iterable
  from uuid import UUID

logger = logging.getLogger(__name__)


class DrugRecallRepository:
  """Data access for `drug_recalls`."""

  # ── 대량 UPSERT (복합 UNIQUE 키 기반) ────────────────────────────
  # 흐름: items 순회 -> entrps_name_normalized 자동 산출
  #       -> update_or_create(복합키 lookup, defaults=나머지)
  #       -> 실패 시 다음 row 계속 (개별 row 격리)

  async def bulk_upsert(
    self,
    items: list[dict[str, Any]],
    batch_size: int = 100,
  ) -> dict[str, int]:
    """Insert or update recall rows using the composite UNIQUE key.

    Args:
        items: API-derived dicts. Each must contain `item_seq`,
            `recall_command_date`, `recall_reason`, `product_name`,
            `entrps_name`. Optional: `std_code`, `sale_stop_yn`,
            `is_hospital_only`, `is_non_drug`. The normalized
            manufacturer column is computed here so callers don't
            need to pre-normalize.
        batch_size: Logging cadence; processing is row-by-row.

    Returns:
        Dict with `inserted` and `updated` counts.
    """
    inserted = 0
    updated = 0
    total = len(items)

    for idx, raw in enumerate(items, start=1):
      payload = dict(raw)
      try:
        lookup = {
          "item_seq": payload.pop("item_seq"),
          "recall_command_date": payload.pop("recall_command_date"),
          "recall_reason": payload.pop("recall_reason"),
        }
        payload["entrps_name_normalized"] = normalize_company_name(payload.get("entrps_name"))

        _, created = await DrugRecall.update_or_create(defaults=payload, **lookup)
        if created:
          inserted += 1
        else:
          updated += 1
      except Exception:
        logger.exception("Failed to upsert drug_recall row item_seq=%s", raw.get("item_seq"))
        continue

      if idx % batch_size == 0:
        logger.info(
          "drug_recalls upsert progress: %d/%d (inserted=%d, updated=%d)",
          idx,
          total,
          inserted,
          updated,
        )

    return {"inserted": inserted, "updated": updated}

  # ── Q1: item_seq 매칭 ────────────────────────────────────────────

  async def find_by_item_seqs(self, item_seqs: Iterable[str]) -> list[DrugRecall]:
    """Return recall rows whose `item_seq` is in the given set.

    Multiple recall reasons for the same `item_seq` all surface here.
    """
    seqs = {s for s in item_seqs if s}
    if not seqs:
      return []

    return await DrugRecall.filter(item_seq__in=seqs).all()

  # ── Q2: 제조사명 정규화 매칭 ─────────────────────────────────────

  async def find_by_manufacturers(self, names: Iterable[str]) -> list[DrugRecall]:
    """Return recall rows whose normalized manufacturer is in `names`.

    Inputs are normalized via `normalize_company_name` before the
    query so the caller may pass raw `entp_name` strings from the
    permits API.
    """
    normalized = {normalize_company_name(n) for n in names if n}
    normalized.discard("")
    if not normalized:
      return []

    return await DrugRecall.filter(entrps_name_normalized__in=normalized).all()

  # ── cron diff: 신규 row 만 ───────────────────────────────────────

  async def diff_new_recalls(self, since: datetime) -> list[DrugRecall]:
    """Return recall rows created strictly after `since`."""
    return await DrugRecall.filter(created_at__gt=since).all()

  # ── F3 / cron 알림 매칭 (item_seq 1순위 → product_name ILIKE 2순위) ──

  # ── A.5.1: 단건 등록 매칭 (item_seq 우선, product_name 정규화 fallback) ──
  # 흐름: item_seq 존재 -> 그 대로 매칭
  #       -> 없으면 product_name 정규화 후 후보 행들과 메모리 비교
  # 의약외품(is_non_drug)·병원전용(is_hospital_only) 행은 항상 제외.

  async def find_by_item_seq_or_name(
    self,
    item_seq: str | None = None,
    product_name: str | None = None,
  ) -> list[DrugRecall]:
    """Match a single medication against ``drug_recalls`` for registration time.

    Args:
        item_seq: Exact ``item_seq`` to match. When provided this takes
            precedence and ``product_name`` is ignored.
        product_name: Fallback product name. Normalized via
            ``normalize_product_name`` and compared in memory against
            each candidate row's normalized ``product_name``.

    Returns:
        All matching rows (multiple reasons for the same product all
        surface). Empty list when nothing matches or both arguments are
        falsy. ``is_non_drug=True`` / ``is_hospital_only=True`` rows are
        excluded so consumer-medication registration never surfaces
        non-drug or hospital-only items.
    """
    if not item_seq and not product_name:
      return []

    if item_seq:
      return await DrugRecall.filter(
        item_seq=item_seq,
        is_non_drug=False,
        is_hospital_only=False,
      ).all()

    norm_input = normalize_product_name(product_name)
    if not norm_input:
      return []

    candidates = await DrugRecall.filter(
      is_non_drug=False,
      is_hospital_only=False,
    ).all()
    return [c for c in candidates if normalize_product_name(c.product_name) == norm_input]

  # ── A.5.4: 마이페이지 batch lookup (단일 쿼리 + 메모리 그룹핑) ──
  # 흐름: medications 의 medicine_name 셋 정규화
  #       -> DrugRecall 후보 SELECT 1회 (사전 필터 포함)
  #       -> 정규화 비교로 medication_id 별 그룹핑

  async def find_recalls_for_medications(
    self,
    medications: list[Any],
  ) -> dict[UUID, list[DrugRecall]]:
    """Return ``{medication_id: [matching DrugRecall, ...]}`` in 1 query.

    Args:
        medications: ORM ``Medication`` instances. Each must expose
            ``id`` and ``medicine_name``.

    Returns:
        Dict keyed by ``medication.id``. Medications without a match
        are *omitted* from the dict — callers should treat absence as
        "no recall" (the service layer normalizes via ``dict.get``).
        ``is_non_drug`` / ``is_hospital_only`` rows are excluded as in
        ``find_by_item_seq_or_name``.
    """
    if not medications:
      return {}

    # 정규화된 medicine_name 별로 medication 들을 묶어 후보 매칭 시 O(1) lookup.
    name_to_meds: dict[str, list[Any]] = {}
    for med in medications:
      raw_name = getattr(med, "medicine_name", None)
      if not raw_name:
        continue
      normalized = normalize_product_name(raw_name)
      if not normalized:
        continue
      name_to_meds.setdefault(normalized, []).append(med)

    if not name_to_meds:
      return {}

    candidates = await DrugRecall.filter(
      is_non_drug=False,
      is_hospital_only=False,
    ).all()

    grouped: dict[UUID, list[DrugRecall]] = {}
    for recall in candidates:
      recall_norm = normalize_product_name(getattr(recall, "product_name", None))
      if not recall_norm or recall_norm not in name_to_meds:
        continue
      for med in name_to_meds[recall_norm]:
        grouped.setdefault(med.id, []).append(recall)
    return grouped

  async def find_match(self, medication: Any) -> list[DrugRecall]:
    """Match a single medication against the recall table.

    The `medications` table stores only `medicine_name` (no FK to
    `medicine_info`) so the strategy resolves the medicine_info
    row by name first, then falls back to a fuzzy product_name
    ILIKE match for OCR-only entries (S7).

    Strategy:
        1) `medicine_info` lookup by exact `medicine_name` →
           `item_seq` → `DrugRecall.item_seq` match.
        2) `medicine_info` row missing or item_seq empty →
           `DrugRecall.product_name ILIKE %medicine_name%` fallback.
        3) Empty / missing `medicine_name` short-circuits to `[]`.

    Returns:
        All matching recall rows (possibly multiple reasons for the
        same product). Empty list when nothing matches.
    """
    name = (getattr(medication, "medicine_name", "") or "").strip()
    if not name:
      return []

    mi = await MedicineInfo.filter(medicine_name=name).first()
    if mi is not None and mi.item_seq:
      return await DrugRecall.filter(item_seq__in={mi.item_seq}).all()

    return await DrugRecall.filter(product_name__icontains=name).all()

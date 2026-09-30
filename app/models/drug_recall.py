"""Drug recall model module.

This module defines the DrugRecall model for storing recall and
sale-stop notices issued by the Ministry of Food and Drug Safety
(MFDS) public API (`MdcinRtrvlSleStpgeInfoService04`).

Design notes:
    - Composite UNIQUE on (item_seq, recall_command_date, recall_reason)
      because a single ITEM_SEQ can appear with multiple recall reasons
      issued on the same date (observed in the 2026-04-27 seed: ITEM_SEQ
      `202007244` x3, `201904809` x2). A single-column UNIQUE on
      `item_seq` would block bulk_upsert.
    - `entrps_name_normalized` stores the output of
      `app.utils.company_name_normalizer.normalize_company_name` and is
      the matching key for the Q2 manufacturer-recall tool. The original
      `entrps_name` is preserved verbatim for audit and display.
    - No ForeignKey to `medicine_info`. Recall rows may reference drugs
      missing from the local `medicine_info` cache (verified by the
      2026-04-27 seed that the 5 recalled drugs are all marked
      `CANCEL_NAME=정상` in the permits API). Joins are performed via
      raw SQL on `item_seq` when needed (loose join policy).
"""

from tortoise import fields, models


class DrugRecall(models.Model):
  """Recall / sale-stop notice from the MFDS public API.

  Stores one row per (drug, recall date, recall reason) tuple. A drug
  that is recalled multiple times — or for multiple reasons on the
  same day — produces multiple rows.

  Attributes:
      id: Auto-increment primary key.
      item_seq: Drug product code (matches `medicine_info.item_seq`,
          but loose join — no FK constraint).
      std_code: Drug standard code (`stdrCode`), nullable.
      product_name: Recalled product name (`prdtName`).
      entrps_name: Manufacturer name as returned by the API (audit).
      entrps_name_normalized: Manufacturer name after normalization,
          used as the matching key for the Q2 recall-by-manufacturer
          tool.
      recall_reason: Recall reason text (`rtrvlResn`). Part of the
          composite UNIQUE so it cannot be NULL.
      recall_command_date: Recall command date (`recallCommandDate`)
          in YYYYMMDD format. Part of the composite UNIQUE.
      sale_stop_yn: Sale-stop flag (Y / N).
      is_hospital_only: True when the product matches the hospital-only
          keyword filter (set at ingestion time).
      is_non_drug: True when the product matches the non-drug keyword
          filter (toothpaste, sanitary pads, etc.). Driven by the
          `RECALL_FILTER_NON_DRUG` env toggle.
      created_at: Record creation timestamp (aware UTC).
      updated_at: Record update timestamp (aware UTC).
  """

  # ── 기본 식별자 ────────────────────────────────────────────────────
  id = fields.BigIntField(pk=True)

  # ── 회수·판매중지 식별 컬럼 (복합 UNIQUE 키 구성요소) ──────────────
  # item_seq + recall_command_date + recall_reason 3-tuple 이 자연키.
  # 동일 ITEM_SEQ 가 여러 회수 사유로 등장하므로 단독 UNIQUE 금지.
  item_seq = fields.CharField(
    max_length=20,
    description="Drug product code (matches medicine_info.item_seq, loose join)",
  )
  std_code = fields.CharField(
    max_length=32,
    null=True,
    description="Drug standard code (stdrCode)",
  )
  product_name = fields.CharField(
    max_length=200,
    description="Recalled product name (prdtName)",
  )

  # ── 제조사 (원문 + 정규화) ────────────────────────────────────────
  # 원문은 감사·표시 / 정규화는 Q2 매칭 키.
  entrps_name = fields.CharField(
    max_length=128,
    description="Manufacturer name (entrpsName) — raw audit copy",
  )
  entrps_name_normalized = fields.CharField(
    max_length=128,
    description="Manufacturer name after normalize_company_name (Q2 matching key)",
  )

  # ── 회수 사유·일자·판매중지 플래그 ─────────────────────────────────
  # recall_reason 은 복합 UNIQUE 의 일부라 NOT NULL.
  recall_reason = fields.TextField(
    description="Recall reason text (rtrvlResn) — part of composite UNIQUE",
  )
  recall_command_date = fields.CharField(
    max_length=8,
    description="Recall command date (recallCommandDate) in YYYYMMDD",
  )
  sale_stop_yn = fields.CharField(
    max_length=1,
    default="N",
    description="Sale-stop flag (Y / N)",
  )

  # ── 분류 플래그 (수집 단계 필터링 결과) ────────────────────────────
  # is_hospital_only: 3차 필터 (주사·수액·이식 키워드)
  # is_non_drug: 2차 필터 (의약외품 — 칫솔/치약/생리대 등)
  is_hospital_only = fields.BooleanField(
    default=False,
    description="Hospital-only formulation flag (keyword filter result)",
  )
  is_non_drug = fields.BooleanField(
    default=False,
    description="Non-drug product flag (toothbrush / sanitary pad / etc.)",
  )

  # ── 타임스탬프 ─────────────────────────────────────────────────────
  created_at = fields.DatetimeField(auto_now_add=True)
  updated_at = fields.DatetimeField(auto_now=True)

  class Meta:
    table = "drug_recalls"
    table_description = "MFDS recall and sale-stop notices (loose join with medicine_info)"
    unique_together = (("item_seq", "recall_command_date", "recall_reason"),)
    indexes = (
      ("entrps_name_normalized",),
      ("recall_command_date",),
      ("product_name",),
      ("item_seq",),
    )

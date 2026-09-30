"""Medicine information model module.

This module defines the MedicineInfo model for the pharmaceutical
knowledge base, integrating public API data and acting as the parent
record for RAG embedding chunks (medicine_chunk) and active-ingredient
details (medicine_ingredient).
"""

from tortoise import fields, models


class MedicineInfo(models.Model):
  """Pharmaceutical knowledge base parent row.

  Stores drug permit data from the Food and Drug Safety public API
  (DrugPrdtPrmsnInfoService07). Dense vector embeddings for RAG
  are stored in the child `medicine_chunk` table. Active ingredient
  1:N details are stored in the child `medicine_ingredient` table.

  Attributes:
      id: Auto-increment primary key.
      item_seq: Unique drug product code from public API (UPSERT key).
      medicine_name: Drug product name in Korean.
      item_eng_name: Drug product name in English.
      entp_name: Manufacturer name.
      product_type: Product classification code.
      spclty_pblc: Professional/OTC drug classification.
      permit_date: Permit date in YYYYMMDD format.
      cancel_name: Current status (normal/cancelled).
      main_item_ingr: Active ingredients with standard codes (raw string).
      storage_method: Storage instructions.
      edi_code: Insurance billing codes.
      bizrno: Business registration number.
      change_date: Last change date from API in YYYYMMDD format.
      category: Drug category for search filtering.
      efficacy: Drug efficacy and effects.
      side_effects: Known side effects.
      precautions: Usage precautions.
      chart: Physical appearance description (CHART).
      material_name: Total/portion raw string (MATERIAL_NAME).
      valid_term: Shelf-life description (VALID_TERM).
      pack_unit: Packaging unit description (PACK_UNIT).
      atc_code: WHO ATC classification code (ATC_CODE).
      ee_doc_url: Efficacy PDF source URL (EE_DOC_ID).
      ud_doc_url: Usage PDF source URL (UD_DOC_ID).
      nb_doc_url: Precaution PDF source URL (NB_DOC_ID).
      last_synced_at: Last sync timestamp from public API.
      created_at: Record creation timestamp.
      updated_at: Record update timestamp.
  """

  id = fields.IntField(pk=True)

  # ── 공공데이터 API 필드 (getDrugPrdtPrmsnDtlInq06에서 수집) ──────────
  # item_seq를 UPSERT 기준 키로 사용하여 증분 업데이트 시 중복 방지
  item_seq = fields.CharField(
    max_length=20,
    unique=True,
    null=True,
    description="Drug product code from public API (UPSERT key)",
  )
  medicine_name = fields.CharField(
    max_length=200,
    unique=True,
    description="Drug product name in Korean",
  )
  item_eng_name = fields.CharField(
    max_length=256,
    null=True,
    description="Drug product name in English",
  )
  entp_name = fields.CharField(
    max_length=128,
    null=True,
    description="Manufacturer name",
  )
  product_type = fields.CharField(
    max_length=64,
    null=True,
    description="Product classification code",
  )
  spclty_pblc = fields.CharField(
    max_length=32,
    null=True,
    description="Professional or OTC drug classification",
  )
  permit_date = fields.CharField(
    max_length=8,
    null=True,
    description="Permit date in YYYYMMDD format",
  )
  cancel_name = fields.CharField(
    max_length=16,
    null=True,
    description="Current status (normal or cancelled)",
  )
  main_item_ingr = fields.TextField(
    null=True,
    description="Active ingredients with standard codes",
  )
  storage_method = fields.TextField(
    null=True,
    description="Storage method and instructions",
  )
  edi_code = fields.CharField(
    max_length=256,
    null=True,
    description="Insurance billing codes (comma-separated)",
  )
  bizrno = fields.CharField(
    max_length=16,
    null=True,
    description="Business registration number",
  )
  change_date = fields.CharField(
    max_length=8,
    null=True,
    description="Last change date from API in YYYYMMDD format",
  )

  # ── RAG 지식 베이스 필드 (LLM 호출 또는 수동 큐레이션으로 채워짐) ───
  category = fields.CharField(
    max_length=64,
    null=True,
    description="Drug category for search filtering",
  )
  efficacy = fields.TextField(
    null=True,
    description="Drug efficacy and effects",
  )
  side_effects = fields.JSONField(
    null=True,
    description="이상반응 PARAGRAPH list (NB_DOC_DATA 4번 이상반응 카테고리)",
  )
  precautions = fields.JSONField(
    null=True,
    description="식약처 9 카테고리(이상반응 제외) dict",
  )
  dosage = fields.TextField(
    null=True,
    description="용법용량 평문화 (UD_DOC_DATA → flatten plaintext)",
  )

  # ── 공공데이터 API 추가 메타 필드 (RAG 품질 강화용) ─────────────────
  # CHART / MATERIAL_NAME / VALID_TERM / PACK_UNIT / ATC_CODE
  # EE_DOC_ID / UD_DOC_ID / NB_DOC_ID 원본 URL
  chart = fields.TextField(
    null=True,
    description="Physical appearance (CHART)",
  )
  material_name = fields.TextField(
    null=True,
    description="Total/portion raw string (MATERIAL_NAME)",
  )
  valid_term = fields.CharField(
    max_length=64,
    null=True,
    description="Shelf-life description (VALID_TERM)",
  )
  pack_unit = fields.CharField(
    max_length=2048,
    null=True,
    description="Packaging unit description (PACK_UNIT) — 일부 품목은 256 자 초과 가능",
  )
  atc_code = fields.CharField(
    max_length=32,
    null=True,
    description="WHO ATC classification code (ATC_CODE)",
  )
  ee_doc_url = fields.CharField(
    max_length=256,
    null=True,
    description="Efficacy PDF source URL (EE_DOC_ID)",
  )
  ud_doc_url = fields.CharField(
    max_length=256,
    null=True,
    description="Usage PDF source URL (UD_DOC_ID)",
  )
  nb_doc_url = fields.CharField(
    max_length=256,
    null=True,
    description="Precaution PDF source URL (NB_DOC_ID)",
  )

  # ── Dtl06 원본 XML 본문 (재임베딩/재청크 시 API 재호출 회피) ──────────
  ee_doc_data = fields.TextField(
    null=True,
    description="Raw EE_DOC_DATA XML (효능효과 원문)",
  )
  ud_doc_data = fields.TextField(
    null=True,
    description="Raw UD_DOC_DATA XML (용법용량 원문)",
  )
  nb_doc_data = fields.TextField(
    null=True,
    description="Raw NB_DOC_DATA XML (사용상주의사항 원문)",
  )

  # ── 동기화 추적 및 타임스탬프 ──────────────────────────────────────
  last_synced_at = fields.DatetimeField(
    null=True,
    description="Last synchronization timestamp from public API",
  )
  created_at = fields.DatetimeField(auto_now_add=True)
  updated_at = fields.DatetimeField(auto_now=True)

  class Meta:
    table = "medicine_info"
    table_description = "Pharmaceutical knowledge base for RAG search and public API data"

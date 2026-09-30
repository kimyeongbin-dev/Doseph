"""Medicine ingredient model module.

This module defines the MedicineIngredient model storing the 1:N
active ingredient details sourced from the public Korean Drug
Ingredient Detail API (총 ~127k rows, keyed by `ITEM_SEQ:MTRAL_SN`).
"""

from tortoise import fields, models


class MedicineIngredient(models.Model):
  """Active-ingredient row for a medicine_info record (1:N relation).

  One medicine_info row can have multiple ingredient rows
  (e.g. a saline-glucose solution has both Glucose and NaCl).
  UPSERT key is the composite (medicine_info_id, mtral_sn).

  Attributes:
      id: Auto-increment primary key.
      medicine_info: FK to parent drug (ON DELETE CASCADE).
      mtral_sn: Ingredient sequence number within the drug.
      mtral_code: Standardised ingredient code (e.g. M040702).
      mtral_name: Korean ingredient name (e.g. 포도당).
      main_ingr_eng: English ingredient name (e.g. Glucose).
      quantity: Ingredient amount per unit.
      unit: Quantity unit (e.g. 그램, 밀리그램).
      created_at: Record creation timestamp.
  """

  # ── 기본 식별자 및 부모 FK ─────────────────────────────────────────
  id = fields.BigIntField(pk=True)
  medicine_info = fields.ForeignKeyField(
    "models.MedicineInfo",
    related_name="ingredients",
    on_delete=fields.CASCADE,
    description="Parent medicine_info reference",
  )

  # ── 주성분 순번 및 코드 ────────────────────────────────────────────
  # API 필드: MTRAL_SN / MTRAL_CODE / MTRAL_NM / MAIN_INGR_ENG
  mtral_sn = fields.IntField(
    description="Ingredient sequence number within the drug (API MTRAL_SN)",
  )
  mtral_code = fields.CharField(
    max_length=16,
    null=True,
    description="Ingredient standard code (API MTRAL_CODE)",
  )
  mtral_name = fields.CharField(
    max_length=128,
    description="Korean ingredient name (API MTRAL_NM)",
  )
  main_ingr_eng = fields.CharField(
    max_length=256,
    null=True,
    description="English ingredient name (API MAIN_INGR_ENG)",
  )

  # ── 분량 및 단위 ───────────────────────────────────────────────────
  # 원본 API가 문자열이므로 VARCHAR 유지 (단위 혼재 대응)
  quantity = fields.CharField(
    max_length=32,
    null=True,
    description="Ingredient quantity (API QNT)",
  )
  unit = fields.CharField(
    max_length=16,
    null=True,
    description="Quantity unit (API INGD_UNIT_CD)",
  )

  # ── 타임스탬프 ─────────────────────────────────────────────────────
  created_at = fields.DatetimeField(auto_now_add=True)

  class Meta:
    table = "medicine_ingredient"
    table_description = "Drug active ingredients (1:N from medicine_info)"
    unique_together = (("medicine_info", "mtral_sn"),)
    indexes = (
      ("mtral_name",),
      ("mtral_code",),
    )

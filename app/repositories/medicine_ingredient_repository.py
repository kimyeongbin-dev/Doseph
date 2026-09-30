"""MedicineIngredient repository — 약품-성분 1:N 마스터 CRUD.

식약처 ``getDrugPrdtMcpnDtlInq07`` 응답을 받아 ``medicine_info`` 부모 row 와
연결된 1:N 성분 row 를 UPSERT 한다. UPSERT 키는 (medicine_info_id, mtral_sn).
"""

from collections.abc import Iterable
import logging

from app.models.medicine_info import MedicineInfo
from app.models.medicine_ingredient import MedicineIngredient

logger = logging.getLogger(__name__)


class MedicineIngredientRepository:
  """MedicineIngredient bulk UPSERT 담당."""

  async def get_medicine_id_map(self, item_seqs: Iterable[str]) -> dict[str, int]:
    """item_seq -> MedicineInfo.id 매핑 dict 반환 (FK 해석용).

    모르는 item_seq 는 결과에 누락 — 호출자가 skip 처리.
    """
    seqs = list({s for s in item_seqs if s})
    if not seqs:
      return {}
    rows = await MedicineInfo.filter(item_seq__in=seqs).values("id", "item_seq")
    return {r["item_seq"]: r["id"] for r in rows}

  async def bulk_upsert(self, ingredients: list[dict]) -> dict[str, int]:
    """성분 row 일괄 UPSERT — (medicine_info_id, mtral_sn) 기준.

    한 row 가 ValidationError / IntegrityError 등으로 실패해도 다음 row 진행.
    실패 사유는 로그로만 남기고 카운트는 정상 처리분만 반영.

    Args:
        ingredients: medicine_info_id, mtral_sn, mtral_code, mtral_name,
            main_ingr_eng, quantity, unit 키를 가진 dict list.

    Returns:
        {"inserted": n, "updated": m} — 신규 / 갱신 row 수.
    """
    inserted = 0
    updated = 0
    for row in ingredients:
      try:
        _, created = await MedicineIngredient.update_or_create(
          medicine_info_id=row["medicine_info_id"],
          mtral_sn=row["mtral_sn"],
          defaults={
            "mtral_code": row.get("mtral_code"),
            "mtral_name": row["mtral_name"],
            "main_ingr_eng": row.get("main_ingr_eng"),
            "quantity": row.get("quantity"),
            "unit": row.get("unit"),
          },
        )
      except Exception:
        logger.exception(
          "Failed to upsert ingredient (medicine_info_id=%s, mtral_sn=%s)",
          row.get("medicine_info_id", "unknown"),
          row.get("mtral_sn", "unknown"),
        )
        continue
      if created:
        inserted += 1
      else:
        updated += 1
    return {"inserted": inserted, "updated": updated}

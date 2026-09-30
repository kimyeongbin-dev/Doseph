"""MedicineIngredient 모델 검증 테스트 (주성분 1:N 테이블).

검증 포인트:
- 필드 구성 (mtral_sn, mtral_code, mtral_name 등)
- FK 관계 (medicine_info_id → medicine_info.id)
- Unique 제약 (medicine_info_id, mtral_sn)
- 테이블명
"""

from tortoise import Tortoise

from app.db.databases import TORTOISE_APP_MODELS

Tortoise.init_models(TORTOISE_APP_MODELS, "models")


class TestMedicineIngredientSchema:
  """medicine_ingredient 모델 스키마 검증."""

  def test_module_importable(self) -> None:
    """medicine_ingredient 모듈이 import 가능해야 한다."""
    from app.models import medicine_ingredient  # noqa: F401

  def test_table_name(self) -> None:
    from app.models.medicine_ingredient import MedicineIngredient

    assert MedicineIngredient._meta.db_table == "medicine_ingredient"

  def test_required_fields_exist(self) -> None:
    """주성분 API 매핑 필드가 모두 정의되어야 한다."""
    from app.models.medicine_ingredient import MedicineIngredient

    fields_map = MedicineIngredient._meta.fields_map
    required = {
      "id",
      "medicine_info",
      "mtral_sn",
      "mtral_code",
      "mtral_name",
      "main_ingr_eng",
      "quantity",
      "unit",
      "created_at",
    }
    missing = required - set(fields_map.keys())
    assert not missing, f"누락 필드: {missing}"

  def test_mtral_name_not_null(self) -> None:
    """mtral_name(성분명)은 not null이어야 한다."""
    from app.models.medicine_ingredient import MedicineIngredient

    field = MedicineIngredient._meta.fields_map["mtral_name"]
    assert field.null is False
    assert field.max_length == 128

  def test_mtral_sn_not_null(self) -> None:
    """mtral_sn(성분 순번)은 not null이어야 한다 (UPSERT 키 구성요소)."""
    from app.models.medicine_ingredient import MedicineIngredient

    field = MedicineIngredient._meta.fields_map["mtral_sn"]
    assert field.null is False

  def test_fk_to_medicine_info(self) -> None:
    from app.models.medicine_ingredient import MedicineIngredient

    fields_map = MedicineIngredient._meta.fields_map
    assert "medicine_info" in fields_map
    fk_field = fields_map["medicine_info"]
    assert fk_field.model_name == "models.MedicineInfo"

  def test_unique_constraint_on_medicine_and_sn(self) -> None:
    """(medicine_info_id, mtral_sn) 유니크 제약이 있어야 한다."""
    from app.models.medicine_ingredient import MedicineIngredient

    unique_together = getattr(MedicineIngredient._meta, "unique_together", ())
    expected = ("medicine_info", "mtral_sn")
    found = any(tuple(group) == expected or set(group) == set(expected) for group in unique_together)
    assert found, f"unique_together에 {expected} 누락. 현재값: {unique_together}"

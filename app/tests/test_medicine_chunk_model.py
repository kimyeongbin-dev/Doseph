"""MedicineChunk 모델 검증 테스트 (RAG 벡터 검색 청크 테이블, v2 재설계).

검증 포인트 (v2 수요자 중심):
- 필드 구성 (section, chunk_index, content, embedding, model_version,
  interaction_tags 등)
- section enum **6종 고정** (스키마 락 ②, v2)
- interaction_tags JSONB 컬럼 존재 (스키마 락 ④, 신규)
- FK 관계 (medicine_info_id → medicine_info.id)
- Unique 제약 (medicine_info_id, section, chunk_index)
- 테이블명과 인덱스 구성
"""

from tortoise import Tortoise

from app.db.databases import TORTOISE_APP_MODELS

Tortoise.init_models(TORTOISE_APP_MODELS, "models")


class TestMedicineChunkSchema:
  """medicine_chunk 모델 스키마 검증 (v2)."""

  def test_module_importable(self) -> None:
    """medicine_chunk 모듈이 import 가능해야 한다."""
    from app.models import medicine_chunk  # noqa: F401

  def test_table_name(self) -> None:
    """테이블명은 medicine_chunk로 지정되어야 한다."""
    from app.models.medicine_chunk import MedicineChunk

    assert MedicineChunk._meta.db_table == "medicine_chunk"

  def test_required_fields_exist(self) -> None:
    """필수 필드가 모두 정의되어야 한다 (v2: interaction_tags 포함)."""
    from app.models.medicine_chunk import MedicineChunk

    fields_map = MedicineChunk._meta.fields_map
    required = {
      "id",
      "medicine_info",
      "section",
      "chunk_index",
      "content",
      "token_count",
      "embedding",
      "model_version",
      "interaction_tags",
      "created_at",
      "updated_at",
    }
    missing = required - set(fields_map.keys())
    assert not missing, f"누락 필드: {missing}"

  def test_section_field_type(self) -> None:
    """section 컬럼은 VARCHAR(48), not null이어야 한다."""
    from app.models.medicine_chunk import MedicineChunk

    section_field = MedicineChunk._meta.fields_map["section"]
    assert section_field.max_length == 48
    assert section_field.null is False

  def test_model_version_not_null(self) -> None:
    """model_version은 not null이어야 한다 (재임베딩 추적 필수)."""
    from app.models.medicine_chunk import MedicineChunk

    field = MedicineChunk._meta.fields_map["model_version"]
    assert field.null is False
    assert field.max_length == 64

  def test_chunk_index_has_default_zero(self) -> None:
    """chunk_index 기본값은 0이어야 한다 (단일 청크 기본)."""
    from app.models.medicine_chunk import MedicineChunk

    field = MedicineChunk._meta.fields_map["chunk_index"]
    assert field.default == 0

  def test_interaction_tags_is_json_field(self) -> None:
    """interaction_tags 필드가 JSON 타입이고 기본값이 빈 리스트여야 한다 (스키마 락 ④)."""
    from tortoise import fields

    from app.models.medicine_chunk import MedicineChunk

    field = MedicineChunk._meta.fields_map["interaction_tags"]
    assert isinstance(field, fields.JSONField)
    assert field.default is list

  def test_fk_to_medicine_info(self) -> None:
    """medicine_info FK 관계가 정의되어야 한다."""
    from app.models.medicine_chunk import MedicineChunk

    fields_map = MedicineChunk._meta.fields_map
    assert "medicine_info" in fields_map
    fk_field = fields_map["medicine_info"]
    assert fk_field.model_name == "models.MedicineInfo"

  def test_unique_constraint_on_section_index(self) -> None:
    """(medicine_info_id, section, chunk_index) 유니크 제약이 있어야 한다."""
    from app.models.medicine_chunk import MedicineChunk

    unique_together = getattr(MedicineChunk._meta, "unique_together", ())
    expected = ("medicine_info", "section", "chunk_index")
    found = any(tuple(group) == expected or set(group) == set(expected) for group in unique_together)
    assert found, f"unique_together에 {expected} 누락. 현재값: {unique_together}"

  def test_section_enum_has_6_values(self) -> None:
    """section enum 은 v2 6종 으로 고정 (스키마 락 ②, 사용자 질문 패턴 기반)."""
    from app.models.medicine_chunk import MedicineChunkSection

    expected_values = {
      "overview",
      "intake_guide",
      "drug_interaction",
      "lifestyle_interaction",
      "adverse_reaction",
      "special_event",
    }
    actual_values = {member.value for member in MedicineChunkSection}
    assert actual_values == expected_values, (
      f"section enum 불일치. 누락={expected_values - actual_values}, 불필요={actual_values - expected_values}"
    )

  def test_section_enum_v1_values_removed(self) -> None:
    """v1 섹션 값들은 반드시 제거되어야 한다 (재설계 회귀 방지)."""
    from app.models.medicine_chunk import MedicineChunkSection

    actual = {m.value for m in MedicineChunkSection}
    v1_only = {
      "efficacy",
      "usage",
      "storage",
      "ingredient",
      "precaution_warning",
      "precaution_contraindication",
      "precaution_caution",
      "precaution_general",
      "precaution_pregnancy",
      "precaution_pediatric",
      "precaution_elderly",
      "precaution_overdose",
    }
    leaked = actual & v1_only
    assert not leaked, f"v1 enum 값이 남아있음: {leaked}"

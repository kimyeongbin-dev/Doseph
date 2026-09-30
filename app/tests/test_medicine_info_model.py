"""MedicineInfo 모델 스키마 변경 검증 테스트 (RAG 임베딩 구조 전환).

변경 사항 검증:
- `embedding` 컬럼 제거 (청크 테이블로 분리)
- 8개 컬럼 신규 추가 (chart, material_name, valid_term, pack_unit,
  atc_code, ee_doc_url, ud_doc_url, nb_doc_url)
"""

from tortoise import Tortoise

from app.db.databases import TORTOISE_APP_MODELS
from app.models.medicine_info import MedicineInfo

# ── Tortoise 모델 메타데이터 로딩 (DB 연결 없이 필드 검사 가능) ──────
Tortoise.init_models(TORTOISE_APP_MODELS, "models")


class TestMedicineInfoSchemaChange:
  """medicine_info 테이블의 RAG 구조 전환 검증."""

  def test_embedding_column_removed(self) -> None:
    """embedding 컬럼이 medicine_info에서 완전히 제거되어야 한다."""
    fields_map = MedicineInfo._meta.fields_map
    assert "embedding" not in fields_map, (
      "embedding 컬럼은 medicine_chunk 테이블로 분리되었으므로 medicine_info에서 제거되어야 함"
    )

  def test_chart_column_added(self) -> None:
    """성상 정보(CHART) 컬럼이 TEXT 타입으로 추가되어야 한다."""
    fields_map = MedicineInfo._meta.fields_map
    assert "chart" in fields_map
    assert fields_map["chart"].null is True

  def test_material_name_column_added(self) -> None:
    """총량/분량(MATERIAL_NAME) 컬럼이 TEXT 타입으로 추가되어야 한다."""
    fields_map = MedicineInfo._meta.fields_map
    assert "material_name" in fields_map
    assert fields_map["material_name"].null is True

  def test_valid_term_column_added(self) -> None:
    """유효기간(VALID_TERM) 컬럼이 VARCHAR(64)로 추가되어야 한다."""
    fields_map = MedicineInfo._meta.fields_map
    assert "valid_term" in fields_map
    assert fields_map["valid_term"].max_length == 64
    assert fields_map["valid_term"].null is True

  def test_pack_unit_column_added(self) -> None:
    """포장단위(PACK_UNIT) 컬럼이 VARCHAR(2048)로 추가되어야 한다."""
    fields_map = MedicineInfo._meta.fields_map
    assert "pack_unit" in fields_map
    assert fields_map["pack_unit"].max_length == 2048
    assert fields_map["pack_unit"].null is True

  def test_atc_code_column_added(self) -> None:
    """WHO ATC 분류코드 컬럼이 VARCHAR(32)로 추가되어야 한다."""
    fields_map = MedicineInfo._meta.fields_map
    assert "atc_code" in fields_map
    assert fields_map["atc_code"].max_length == 32

  def test_doc_url_columns_added(self) -> None:
    """효능/용법/주의사항 원본 PDF URL 컬럼 3종이 모두 추가되어야 한다."""
    fields_map = MedicineInfo._meta.fields_map
    for col in ("ee_doc_url", "ud_doc_url", "nb_doc_url"):
      assert col in fields_map, f"{col} 컬럼 누락"
      assert fields_map[col].max_length == 256
      assert fields_map[col].null is True

  def test_item_seq_remains_unique_upsert_key(self) -> None:
    """기존 UPSERT 키(item_seq)는 유지되어야 한다 (회귀 방지)."""
    fields_map = MedicineInfo._meta.fields_map
    assert "item_seq" in fields_map
    assert fields_map["item_seq"].unique is True

  def test_table_name_unchanged(self) -> None:
    """테이블명은 medicine_info로 유지되어야 한다."""
    assert MedicineInfo._meta.db_table == "medicine_info"

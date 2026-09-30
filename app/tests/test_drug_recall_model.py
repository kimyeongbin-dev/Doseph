"""DrugRecall 모델 검증 테스트 (식약처 회수·판매중지 데이터, Phase 7).

검증 포인트 (인계 §14.5 핵심 발견 #1 반영):
- 필드 구성 (item_seq, product_name, entrps_name, entrps_name_normalized,
  recall_reason, recall_command_date, sale_stop_yn, is_hospital_only,
  is_non_drug 등)
- 🔴 복합 UNIQUE `(item_seq, recall_command_date, recall_reason)` —
  단순 item_seq UNIQUE 면 동일 품목의 다중 회수 사유 적재 시 충돌
  (시드 §14.5.1: `202007244` 3건, `201904809` 2건)
- 🔴 entrps_name_normalized 컬럼 존재 (§14.5 발견 #2 — 제조사명 정규화 매칭 키)
- FK 미사용 (loose join — `medicine_info.item_seq` 와 별도 테이블 분리, §14.5.2 검증)
- 인덱스 (entrps_name_normalized, recall_command_date, product_name, item_seq)
- 테이블명, aware datetime 타임스탬프
"""

from tortoise import Tortoise, fields

from app.db.databases import TORTOISE_APP_MODELS

Tortoise.init_models(TORTOISE_APP_MODELS, "models")


class TestDrugRecallSchema:
  """drug_recalls 모델 스키마 검증."""

  def test_module_importable(self) -> None:
    """drug_recall 모듈이 import 가능해야 한다."""
    from app.models import drug_recall  # noqa: F401

  def test_table_name(self) -> None:
    """테이블명은 drug_recalls 로 지정되어야 한다."""
    from app.models.drug_recall import DrugRecall

    assert DrugRecall._meta.db_table == "drug_recalls"

  def test_required_fields_exist(self) -> None:
    """필수 필드가 모두 정의되어야 한다 (§14.5 발견 #1, #2 반영)."""
    from app.models.drug_recall import DrugRecall

    fields_map = DrugRecall._meta.fields_map
    required = {
      "id",
      "item_seq",
      "std_code",
      "product_name",
      "entrps_name",
      "entrps_name_normalized",
      "recall_reason",
      "recall_command_date",
      "sale_stop_yn",
      "is_hospital_only",
      "is_non_drug",
      "created_at",
      "updated_at",
    }
    missing = required - set(fields_map.keys())
    assert not missing, f"누락 필드: {missing}"


class TestDrugRecallFieldTypes:
  """drug_recalls 필드 타입·길이·null 제약."""

  def test_item_seq_varchar20_not_null(self) -> None:
    """item_seq 은 VARCHAR(20) NOT NULL (단독 UNIQUE 아님 — 복합 UNIQUE 키 일부)."""
    from app.models.drug_recall import DrugRecall

    field = DrugRecall._meta.fields_map["item_seq"]
    assert field.max_length == 20
    assert field.null is False

  def test_item_seq_not_unique_alone(self) -> None:
    """🔴 item_seq 단독 UNIQUE 가 아니어야 한다 (§14.5 발견 #1).

    동일 item_seq 가 회수 사유·일자별로 다중 row 존재해야 하므로
    단독 UNIQUE 제약은 금지. 복합 UNIQUE 는 별도 테스트에서 검증.
    """
    from app.models.drug_recall import DrugRecall

    field = DrugRecall._meta.fields_map["item_seq"]
    assert field.unique is False, "item_seq 단독 UNIQUE 면 다중 회수 사유 적재 불가"

  def test_product_name_varchar200_not_null(self) -> None:
    """product_name 은 VARCHAR(200) NOT NULL (S7 fallback ILIKE 대상)."""
    from app.models.drug_recall import DrugRecall

    field = DrugRecall._meta.fields_map["product_name"]
    assert field.max_length == 200
    assert field.null is False

  def test_entrps_name_varchar128_not_null(self) -> None:
    """entrps_name 원문은 VARCHAR(128) NOT NULL (감사·표시용)."""
    from app.models.drug_recall import DrugRecall

    field = DrugRecall._meta.fields_map["entrps_name"]
    assert field.max_length == 128
    assert field.null is False

  def test_entrps_name_normalized_varchar128_not_null(self) -> None:
    """🔴 entrps_name_normalized 는 VARCHAR(128) NOT NULL (§14.5 발견 #2 — Q2 매칭 키)."""
    from app.models.drug_recall import DrugRecall

    field = DrugRecall._meta.fields_map["entrps_name_normalized"]
    assert field.max_length == 128
    assert field.null is False

  def test_recall_command_date_varchar8_not_null(self) -> None:
    """recall_command_date 는 VARCHAR(8) NOT NULL (YYYYMMDD)."""
    from app.models.drug_recall import DrugRecall

    field = DrugRecall._meta.fields_map["recall_command_date"]
    assert field.max_length == 8
    assert field.null is False

  def test_recall_reason_text_not_null(self) -> None:
    """recall_reason 은 TextField NOT NULL (복합 UNIQUE 키 일부이므로 NULL 불가)."""
    from app.models.drug_recall import DrugRecall

    field = DrugRecall._meta.fields_map["recall_reason"]
    assert isinstance(field, fields.TextField)
    assert field.null is False

  def test_std_code_nullable(self) -> None:
    """std_code 는 nullable (식약처 응답에 누락 가능)."""
    from app.models.drug_recall import DrugRecall

    field = DrugRecall._meta.fields_map["std_code"]
    assert field.max_length == 32
    assert field.null is True

  def test_sale_stop_yn_varchar1(self) -> None:
    """sale_stop_yn 은 VARCHAR(1) (Y/N)."""
    from app.models.drug_recall import DrugRecall

    field = DrugRecall._meta.fields_map["sale_stop_yn"]
    assert field.max_length == 1

  def test_is_hospital_only_boolean_default_false(self) -> None:
    """is_hospital_only 는 BOOLEAN, default False."""
    from app.models.drug_recall import DrugRecall

    field = DrugRecall._meta.fields_map["is_hospital_only"]
    assert isinstance(field, fields.BooleanField)
    assert field.default is False

  def test_is_non_drug_boolean_default_false(self) -> None:
    """is_non_drug 는 BOOLEAN, default False (의약외품 분류 표시)."""
    from app.models.drug_recall import DrugRecall

    field = DrugRecall._meta.fields_map["is_non_drug"]
    assert isinstance(field, fields.BooleanField)
    assert field.default is False

  def test_timestamps_aware(self) -> None:
    """created_at / updated_at 은 DatetimeField (CLAUDE.md §4.2 aware datetime)."""
    from app.models.drug_recall import DrugRecall

    for name in ("created_at", "updated_at"):
      field = DrugRecall._meta.fields_map[name]
      assert isinstance(field, fields.DatetimeField), name


class TestDrugRecallCompositeUnique:
  """🔴 복합 UNIQUE 검증 (§14.5 발견 #1 — 동일 item_seq 다중 row 필수)."""

  def test_composite_unique_on_item_seq_command_date_reason(self) -> None:
    """unique_together 에 (item_seq, recall_command_date, recall_reason) 가 등록되어 있어야 한다.

    시드 §14.5.1 의 `202007244` 3건 / `201904809` 2건 적재가 이 제약 하에서 가능해야 함.
    """
    from app.models.drug_recall import DrugRecall

    unique_together = getattr(DrugRecall._meta, "unique_together", ())
    expected = {"item_seq", "recall_command_date", "recall_reason"}
    found = any(set(group) == expected for group in unique_together)
    msg = (
      f"unique_together 에 (item_seq, recall_command_date, recall_reason) 복합 UNIQUE 누락. 현재값: {unique_together}"
    )
    assert found, msg


class TestDrugRecallIndexes:
  """인덱스 정책 검증."""

  def test_indexes_present(self) -> None:
    """필수 인덱스: entrps_name_normalized, recall_command_date, product_name, item_seq."""
    from app.models.drug_recall import DrugRecall

    indexes = getattr(DrugRecall._meta, "indexes", ())
    flat = {next(iter(group)) if len(tuple(group)) == 1 else tuple(group) for group in indexes}
    required_single = {
      "entrps_name_normalized",
      "recall_command_date",
      "product_name",
      "item_seq",
    }
    missing = required_single - {x for x in flat if isinstance(x, str)}
    assert not missing, f"누락 인덱스: {missing}. 현재 indexes={indexes}"


class TestDrugRecallNoFK:
  """FK 미사용 검증 (loose join 정책, §14.5.2 별도 테이블 분리 결정)."""

  def test_no_fk_to_medicine_info(self) -> None:
    """drug_recalls 는 medicine_info 로의 ForeignKey 관계를 두지 않는다."""
    from app.models.drug_recall import DrugRecall

    fields_map = DrugRecall._meta.fields_map
    fk_columns = [
      name for name, field in fields_map.items() if isinstance(field, fields.relational.ForeignKeyFieldInstance)
    ]
    assert not fk_columns, f"drug_recalls 에 FK 가 정의됨: {fk_columns} → loose join 정책 위반"

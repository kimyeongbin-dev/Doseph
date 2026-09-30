"""MedicineDataService._transform_item Dtl06 full-field mapping tests.

These tests lock the contract that the transform function maps every
Dtl06 response field that has a corresponding MedicineInfo column,
not just the initial 12 basic fields.

Scope:
- Basic identification fields (already mapped, regression guard)
- Newly mapped metadata fields (CHART, MATERIAL_NAME, VALID_TERM,
  PACK_UNIT, ATC_CODE, CHANGE_DATE)
- Newly mapped PDF document URLs (EE_DOC_ID, UD_DOC_ID, NB_DOC_ID)
- Newly added sync timestamp (last_synced_at, tz-aware UTC)
- Missing field fallback to None
- XML-derived fields (efficacy/side_effects/precautions) are NOT
  transformed here; they are produced by a later chunking step.
"""

from datetime import UTC, datetime

from app.services.medicine_data_service import MedicineDataService


class TestTransformItemBasicFields:
  """기본 식별 필드 매핑 유지 (회귀 가드)."""

  def test_maps_item_seq(self) -> None:
    item = {"ITEM_SEQ": "195700004"}
    result = MedicineDataService._transform_item(item)
    assert result["item_seq"] == "195700004"

  def test_maps_medicine_name(self) -> None:
    item = {"ITEM_NAME": "활명수"}
    result = MedicineDataService._transform_item(item)
    assert result["medicine_name"] == "활명수"

  def test_maps_main_item_ingr(self) -> None:
    item = {"MAIN_ITEM_INGR": "포도당"}
    result = MedicineDataService._transform_item(item)
    assert result["main_item_ingr"] == "포도당"


class TestTransformItemMetadataFields:
  """Dtl06 응답의 메타 필드 확장 매핑."""

  def test_maps_chart(self) -> None:
    item = {"CHART": "단맛이 있는 무색투명한 액"}
    result = MedicineDataService._transform_item(item)
    assert result["chart"] == "단맛이 있는 무색투명한 액"

  def test_maps_material_name(self) -> None:
    item = {"MATERIAL_NAME": "총량 : 100밀리리터 중|성분명 : 포도당"}
    result = MedicineDataService._transform_item(item)
    assert result["material_name"] == "총량 : 100밀리리터 중|성분명 : 포도당"

  def test_maps_valid_term(self) -> None:
    item = {"VALID_TERM": "제조일로부터 36 개월"}
    result = MedicineDataService._transform_item(item)
    assert result["valid_term"] == "제조일로부터 36 개월"

  def test_maps_pack_unit(self) -> None:
    item = {"PACK_UNIT": "500mL/병, 1000mL/병"}
    result = MedicineDataService._transform_item(item)
    assert result["pack_unit"] == "500mL/병, 1000mL/병"

  def test_maps_atc_code(self) -> None:
    item = {"ATC_CODE": "B05BA03"}
    result = MedicineDataService._transform_item(item)
    assert result["atc_code"] == "B05BA03"

  def test_maps_change_date(self) -> None:
    item = {"CHANGE_DATE": "20260323"}
    result = MedicineDataService._transform_item(item)
    assert result["change_date"] == "20260323"


class TestTransformItemDocumentUrls:
  """PDF 문서 URL 매핑 (EE/UD/NB_DOC_ID -> *_doc_url)."""

  def test_maps_ee_doc_url(self) -> None:
    item = {"EE_DOC_ID": "https://nedrug.mfds.go.kr/pbp/cmn/pdfdownload/195700004/EE"}
    result = MedicineDataService._transform_item(item)
    assert result["ee_doc_url"] == "https://nedrug.mfds.go.kr/pbp/cmn/pdfdownload/195700004/EE"

  def test_maps_ud_doc_url(self) -> None:
    item = {"UD_DOC_ID": "https://nedrug.mfds.go.kr/pbp/cmn/pdfdownload/195700004/UD"}
    result = MedicineDataService._transform_item(item)
    assert result["ud_doc_url"] == "https://nedrug.mfds.go.kr/pbp/cmn/pdfdownload/195700004/UD"

  def test_maps_nb_doc_url(self) -> None:
    item = {"NB_DOC_ID": "https://nedrug.mfds.go.kr/pbp/cmn/pdfdownload/195700004/NB"}
    result = MedicineDataService._transform_item(item)
    assert result["nb_doc_url"] == "https://nedrug.mfds.go.kr/pbp/cmn/pdfdownload/195700004/NB"


class TestTransformItemSyncTimestamp:
  """last_synced_at 타임스탬프 생성 (tz-aware UTC)."""

  def test_sets_last_synced_at_as_aware_utc_datetime(self) -> None:
    before = datetime.now(tz=UTC)
    result = MedicineDataService._transform_item({"ITEM_SEQ": "X"})
    after = datetime.now(tz=UTC)

    assert isinstance(result["last_synced_at"], datetime)
    assert result["last_synced_at"].tzinfo is not None, "last_synced_at은 timezone-aware이어야 함 (CLAUDE.md 4.2)"
    assert before <= result["last_synced_at"] <= after


class TestTransformItemMissingFields:
  """응답에서 필드가 빠졌을 때 None 폴백."""

  def test_missing_metadata_fields_become_none(self) -> None:
    item = {"ITEM_SEQ": "X", "ITEM_NAME": "Y"}
    result = MedicineDataService._transform_item(item)

    for column in (
      "chart",
      "material_name",
      "valid_term",
      "pack_unit",
      "atc_code",
      "change_date",
      "ee_doc_url",
      "ud_doc_url",
      "nb_doc_url",
    ):
      assert result[column] is None, f"{column}은 누락 시 None이어야 함"

  def test_empty_string_becomes_none(self) -> None:
    """API가 빈 문자열을 주면 None으로 정규화 (기존 정책 유지)."""
    item = {"CHART": "", "MATERIAL_NAME": "", "ATC_CODE": ""}
    result = MedicineDataService._transform_item(item)

    assert result["chart"] is None
    assert result["material_name"] is None
    assert result["atc_code"] is None


class TestTransformItemDocumentData:
  """Dtl06 DOC XML 본문을 원본 그대로 저장."""

  def test_maps_ee_doc_data(self) -> None:
    xml = '<DOC title="효능효과" type="EE"><SECTION title=""><ARTICLE title="1. 해열"/></SECTION></DOC>'
    result = MedicineDataService._transform_item({"EE_DOC_DATA": xml})
    assert result["ee_doc_data"] == xml

  def test_maps_ud_doc_data(self) -> None:
    xml = (
      '<DOC title="용법용량" type="UD"><SECTION title="">'
      '<ARTICLE title=""><PARAGRAPH tagName="p">'
      "<![CDATA[복용]]></PARAGRAPH></ARTICLE></SECTION></DOC>"
    )
    result = MedicineDataService._transform_item({"UD_DOC_DATA": xml})
    assert result["ud_doc_data"] == xml

  def test_maps_nb_doc_data(self) -> None:
    xml = '<DOC title="사용상의주의사항" type="NB"><SECTION title=""><ARTICLE title="1. 경고"/></SECTION></DOC>'
    result = MedicineDataService._transform_item({"NB_DOC_DATA": xml})
    assert result["nb_doc_data"] == xml


class TestTransformItemEfficacyPlaintext:
  """EE_DOC_DATA는 파싱돼서 평문 efficacy 컬럼도 함께 채움."""

  def test_efficacy_flattened_from_ee_doc_data(self) -> None:
    xml = (
      '<DOC title="효능효과" type="EE"><SECTION title="">'
      '<ARTICLE title="1. 해열 진통"/>'
      '<ARTICLE title="2. 감기 증상 완화"/>'
      "</SECTION></DOC>"
    )
    result = MedicineDataService._transform_item({"EE_DOC_DATA": xml})
    assert "1. 해열 진통" in result["efficacy"]
    assert "2. 감기 증상 완화" in result["efficacy"]

  def test_efficacy_none_when_no_ee_doc_data(self) -> None:
    result = MedicineDataService._transform_item({"ITEM_SEQ": "X"})
    assert result["efficacy"] is None


class TestTransformItemSideEffectsAndPrecautionsOutOfScope:
  """side_effects / precautions는 NB_DOC_DATA ARTICLE 단위 청크로만 생성.

  transform이 직접 해당 컬럼에 평문을 넣지 않는다 (청크 테이블이 책임).
  """

  def test_transform_does_not_populate_side_effects(self) -> None:
    item = {"NB_DOC_DATA": "<DOC>...</DOC>"}
    result = MedicineDataService._transform_item(item)
    assert "side_effects" not in result or result.get("side_effects") is None

  def test_transform_does_not_populate_precautions(self) -> None:
    item = {"NB_DOC_DATA": "<DOC>...</DOC>"}
    result = MedicineDataService._transform_item(item)
    assert "precautions" not in result or result.get("precautions") is None

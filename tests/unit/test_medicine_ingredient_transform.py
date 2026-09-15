"""Unit tests for MedicineDataService._transform_ingredient_item (Mcpn07).

docs-private/PLAN_DRUG_DB_INGEST.md §3.2 — Mcpn07 응답을 medicine_ingredient UPSERT
입력 dict 로 변환. medicine_info FK 미해석 / 필수 필드 누락 시 None 반환.
"""

from app.services.medicine_data_service import MedicineDataService

_ID_MAP = {"195500005": 42, "195700004": 99}


def test_transform_resolves_medicine_info_id() -> None:
    item = {
        "ITEM_SEQ": "195500005",
        "MTRAL_SN": "1",
        "MTRAL_CODE": "M040702",
        "MTRAL_NM": "포도당",
        "MAIN_INGR_ENG": "Glucose",
        "QNT": "50",
        "INGD_UNIT_CD": "그램",
    }
    result = MedicineDataService._transform_ingredient_item(item, _ID_MAP)
    assert result is not None
    assert result["medicine_info_id"] == 42
    assert result["mtral_sn"] == 1
    assert result["mtral_code"] == "M040702"
    assert result["mtral_name"] == "포도당"
    assert result["main_ingr_eng"] == "Glucose"
    assert result["quantity"] == "50"
    assert result["unit"] == "그램"


def test_transform_skips_unknown_item_seq() -> None:
    """medicine_info 에 등록 안 된 약품은 None — sync 흐름에서 skip 처리."""
    item = {
        "ITEM_SEQ": "999999999",
        "MTRAL_SN": "1",
        "MTRAL_NM": "포도당",
    }
    assert MedicineDataService._transform_ingredient_item(item, _ID_MAP) is None


def test_transform_skips_invalid_mtral_sn() -> None:
    item = {
        "ITEM_SEQ": "195500005",
        "MTRAL_SN": "abc",
        "MTRAL_NM": "포도당",
    }
    assert MedicineDataService._transform_ingredient_item(item, _ID_MAP) is None


def test_transform_skips_zero_or_missing_mtral_sn() -> None:
    """MTRAL_SN 0/빈값은 skip — unique key (medicine_info_id, mtral_sn) 정합성."""
    item = {
        "ITEM_SEQ": "195500005",
        "MTRAL_SN": "0",
        "MTRAL_NM": "포도당",
    }
    assert MedicineDataService._transform_ingredient_item(item, _ID_MAP) is None


def test_transform_skips_empty_mtral_name() -> None:
    item = {
        "ITEM_SEQ": "195500005",
        "MTRAL_SN": "1",
        "MTRAL_NM": "",
    }
    assert MedicineDataService._transform_ingredient_item(item, _ID_MAP) is None


def test_transform_handles_optional_fields_none() -> None:
    """MAIN_INGR_ENG / QNT / INGD_UNIT_CD 누락은 허용 (None 채움)."""
    item = {
        "ITEM_SEQ": "195700004",
        "MTRAL_SN": "1",
        "MTRAL_NM": "포도당",
    }
    result = MedicineDataService._transform_ingredient_item(item, _ID_MAP)
    assert result is not None
    assert result["main_ingr_eng"] is None
    assert result["quantity"] is None
    assert result["unit"] is None
    assert result["mtral_code"] is None


def test_transform_quantity_coerces_numeric_to_string() -> None:
    """API 가 QNT 를 숫자로 줄 수도 있음 — string 으로 통일."""
    item = {
        "ITEM_SEQ": "195500005",
        "MTRAL_SN": "1",
        "MTRAL_NM": "포도당",
        "QNT": 0.2,
    }
    result = MedicineDataService._transform_ingredient_item(item, _ID_MAP)
    assert result is not None
    assert result["quantity"] == "0.2"

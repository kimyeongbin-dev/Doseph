"""Unit tests for MedicationService._get_drug_info — DB 검색 기반 (LLM 호출 없음).

docs-private/PLAN_DRUG_DB_INGEST.md — drug-info 응답이 MedicineInfo 의 JSONB precautions /
list side_effects / TEXT dosage 컬럼을 그대로 매핑한다. NULL/miss 시 빈 응답,
interactions 항상 빈 배열 (DB 컬럼 없음).
"""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.services.medication_service import MedicationService


@pytest.fixture
def service() -> MedicationService:
    return MedicationService()


def _mock_medicine_info(
    *,
    medicine_name: str = "타이레놀정500mg",
    precautions: dict | None = None,
    side_effects: list[str] | None = None,
    dosage: str | None = None,
) -> MagicMock:
    info = MagicMock()
    info.medicine_name = medicine_name
    info.precautions = precautions
    info.side_effects = side_effects
    info.dosage = dosage
    return info


# ── DB hit 케이스 ────────────────────────────────────────────────────────────


async def test_db_exact_match_returns_precaution_sections(
    service: MedicationService,
) -> None:
    """JSONB precautions dict → list[PrecautionSection] 변환, 카테고리 순서 보존."""
    info = _mock_medicine_info(
        precautions={
            "경고": ["임산부는 신중히 투여", "간 기능 저하 환자 주의"],
            "금기": ["저혈당 환자에게 투여 금지"],
        },
    )
    with patch(
        "app.services.medication_service.MedicineInfoRepository",
    ) as mock_repo_cls:
        mock_repo = mock_repo_cls.return_value
        mock_repo.get_by_name = AsyncMock(return_value=info)
        mock_repo.search_by_name = AsyncMock()

        result = await service._get_drug_info("타이레놀정500mg")

    assert len(result.warnings) == 2
    assert result.warnings[0].category == "경고"
    assert result.warnings[0].items == [
        "임산부는 신중히 투여",
        "간 기능 저하 환자 주의",
    ]
    assert result.warnings[1].category == "금기"
    mock_repo.search_by_name.assert_not_awaited()


async def test_db_exact_match_passes_through_side_effects_list(
    service: MedicationService,
) -> None:
    info = _mock_medicine_info(side_effects=["두통", "어지러움", "구역"])
    with patch(
        "app.services.medication_service.MedicineInfoRepository",
    ) as mock_repo_cls:
        mock_repo = mock_repo_cls.return_value
        mock_repo.get_by_name = AsyncMock(return_value=info)

        result = await service._get_drug_info("타이레놀정500mg")

    assert result.side_effects == ["두통", "어지러움", "구역"]


async def test_db_hit_passes_through_dosage(
    service: MedicationService,
) -> None:
    info = _mock_medicine_info(dosage="성인: 1회 500mg, 1일 3회 식후 30분")
    with patch(
        "app.services.medication_service.MedicineInfoRepository",
    ) as mock_repo_cls:
        mock_repo = mock_repo_cls.return_value
        mock_repo.get_by_name = AsyncMock(return_value=info)

        result = await service._get_drug_info("타이레놀정500mg")

    assert result.dosage == "성인: 1회 500mg, 1일 3회 식후 30분"


async def test_db_hit_with_null_columns_returns_empty(
    service: MedicationService,
) -> None:
    """precautions=None / side_effects=None / dosage=None 모두 빈 응답."""
    info = _mock_medicine_info(precautions=None, side_effects=None, dosage=None)
    with patch(
        "app.services.medication_service.MedicineInfoRepository",
    ) as mock_repo_cls:
        mock_repo = mock_repo_cls.return_value
        mock_repo.get_by_name = AsyncMock(return_value=info)

        result = await service._get_drug_info("타이레놀정500mg")

    assert result.warnings == []
    assert result.side_effects == []
    assert result.dosage == ""
    assert result.medicine_name == "타이레놀정500mg"


async def test_db_hit_with_empty_dict_returns_empty_warnings(
    service: MedicationService,
) -> None:
    """precautions={} → warnings=[]."""
    info = _mock_medicine_info(precautions={})
    with patch(
        "app.services.medication_service.MedicineInfoRepository",
    ) as mock_repo_cls:
        mock_repo = mock_repo_cls.return_value
        mock_repo.get_by_name = AsyncMock(return_value=info)

        result = await service._get_drug_info("타이레놀정500mg")

    assert result.warnings == []


async def test_categories_with_empty_items_are_filtered(
    service: MedicationService,
) -> None:
    """카테고리 값이 빈 list 면 PrecautionSection 으로 만들지 않음."""
    info = _mock_medicine_info(
        precautions={
            "경고": ["A"],
            "금기": [],  # 빈 list
        },
    )
    with patch(
        "app.services.medication_service.MedicineInfoRepository",
    ) as mock_repo_cls:
        mock_repo = mock_repo_cls.return_value
        mock_repo.get_by_name = AsyncMock(return_value=info)

        result = await service._get_drug_info("타이레놀정500mg")

    assert len(result.warnings) == 1
    assert result.warnings[0].category == "경고"


# ── ILIKE fallback ──────────────────────────────────────────────────────────


async def test_falls_back_to_search_by_name_when_exact_miss(
    service: MedicationService,
) -> None:
    fuzzy_hit = _mock_medicine_info(
        medicine_name="타이레놀정500밀리그람",
        precautions={"경고": ["공복 복용 금지"]},
    )
    with patch(
        "app.services.medication_service.MedicineInfoRepository",
    ) as mock_repo_cls:
        mock_repo = mock_repo_cls.return_value
        mock_repo.get_by_name = AsyncMock(return_value=None)
        mock_repo.search_by_name = AsyncMock(return_value=[fuzzy_hit])

        result = await service._get_drug_info("타이레놀")

    mock_repo.get_by_name.assert_awaited_once_with("타이레놀")
    mock_repo.search_by_name.assert_awaited_once()
    assert len(result.warnings) == 1
    assert result.warnings[0].items == ["공복 복용 금지"]


# ── 매칭 실패 케이스 ─────────────────────────────────────────────────────────


async def test_no_match_returns_empty_response(
    service: MedicationService,
) -> None:
    with patch(
        "app.services.medication_service.MedicineInfoRepository",
    ) as mock_repo_cls:
        mock_repo = mock_repo_cls.return_value
        mock_repo.get_by_name = AsyncMock(return_value=None)
        mock_repo.search_by_name = AsyncMock(return_value=[])

        result = await service._get_drug_info("존재하지않는약")

    assert result.medicine_name == "존재하지않는약"
    assert result.warnings == []
    assert result.side_effects == []
    assert result.dosage == ""
    assert result.interactions == []


# ── interactions 정책 ────────────────────────────────────────────────────────


async def test_interactions_always_empty(
    service: MedicationService,
) -> None:
    info = _mock_medicine_info(
        precautions={"경고": ["A"]},
        side_effects=["B"],
    )
    with patch(
        "app.services.medication_service.MedicineInfoRepository",
    ) as mock_repo_cls:
        mock_repo = mock_repo_cls.return_value
        mock_repo.get_by_name = AsyncMock(return_value=info)

        result = await service._get_drug_info("타이레놀정500mg")

    assert result.interactions == []


# ── LLM 코드 의존성 제거 검증 (P5-A 회귀) ────────────────────────────────────


def test_module_no_longer_imports_openai() -> None:
    import app.services.medication_service as svc_module

    assert not hasattr(svc_module, "AsyncOpenAI"), "AsyncOpenAI 가 여전히 import 됨 — LLM 호출 코드가 남아있을 가능성"


async def test_does_not_call_llm_even_when_db_miss(
    service: MedicationService,
) -> None:
    with patch("app.services.medication_service.MedicineInfoRepository") as mock_repo_cls:
        mock_repo = mock_repo_cls.return_value
        mock_repo.get_by_name = AsyncMock(return_value=None)
        mock_repo.search_by_name = AsyncMock(return_value=[])

        result = await service._get_drug_info(f"randomdrug-{uuid4()}")

    assert result.warnings == []

"""Unit tests for MedicationService._get_drug_info — DB 검색 기반 (LLM 호출 없음).

docs-private/PLAN_DRUG_DB_INGEST.md — drug-info 응답이 MedicineInfo 의 JSONB precautions /
list side_effects / TEXT dosage 컬럼을 그대로 매핑한다. NULL/miss 시 빈 응답.

⚠️ 2026-09-15 현행화(QA-27): 작성 당시엔 *"interactions 는 항상 빈 배열(DB 컬럼 없음)"* 이었으나,
   이후 `_load_drug_interactions` 가 신설돼 **medicine_chunk 의 DRUG_INTERACTION 섹션을 실제로
   조회**한다. 옛 전제를 단언하던 테스트는 실제 동작을 단언하도록 다시 썼다.
   이 파일이 CI 에서 한 번도 돌지 않아 4개월 반 동안 아무도 몰랐다.

매핑 로직(`_get_drug_info`)만 보는 유닛이므로, 협력자인 `_load_drug_interactions` 는
기본적으로 대역으로 세운다(`stub_interactions`). 그 함수 자체의 동작은 전용 테스트에서 본다.
"""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.dtos.drug_info import DrugInteraction
from app.services.medication_service import MedicationService


@pytest.fixture
def service() -> MedicationService:
    return MedicationService()


@pytest.fixture(autouse=True)
def stub_interactions():
    """`_load_drug_interactions` 를 기본 대역으로 세운다(빈 목록).

    이 함수는 medicine_chunk 를 **직접 조회**하므로 대역 없이는 Tortoise 커넥션이
    필요하다(ConfigurationError). 매핑 로직 테스트의 관심사가 아니므로 기본은 빈 목록,
    상호작용 자체를 보는 테스트만 개별적으로 반환값을 덮어쓴다.
    """
    with patch(
        "app.services.medication_service._load_drug_interactions",
        new=AsyncMock(return_value=[]),
    ) as stub:
        yield stub


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


# ── interactions — 로더 결과를 그대로 전달하는가 ──────────────────────────────
# ⚠️ 이 절은 2026-09-15 에 다시 썼다(QA-27). 옛 테스트는 `interactions 는 항상 빈 배열`
#    이라는 **지금은 거짓인 전제**를 단언하고 있었다. `_load_drug_interactions` 신설로
#    실제로는 medicine_chunk 에서 조회된다.
#    대역이 빈 목록을 돌려주니 옛 단언도 "통과"하는데, 그건 동작이 맞아서가 아니라
#    대역을 그렇게 세웠기 때문이다 — 전형적인 헛된 초록이라 계약을 바꿔 잠갔다.


async def test_interactions_are_passed_through_from_loader(
    service: MedicationService,
    stub_interactions: AsyncMock,
) -> None:
    """로더가 찾은 상호작용이 응답에 그대로 실려야 한다."""
    loaded = [
        DrugInteraction(drug="와파린", description="출혈 위험 증가"),
        DrugInteraction(drug="알코올", description="간독성 증가"),
    ]
    stub_interactions.return_value = loaded
    info = _mock_medicine_info(precautions={"경고": ["A"]}, side_effects=["B"])

    with patch(
        "app.services.medication_service.MedicineInfoRepository",
    ) as mock_repo_cls:
        mock_repo = mock_repo_cls.return_value
        mock_repo.get_by_name = AsyncMock(return_value=info)

        result = await service._get_drug_info("타이레놀정500mg")

    assert [i.drug for i in result.interactions] == ["와파린", "알코올"], (
        "로더가 돌려준 상호작용이 응답에 실리지 않았다"
    )
    assert result.interactions[0].description == "출혈 위험 증가"
    stub_interactions.assert_awaited_once_with(info.id)


async def test_interactions_empty_when_loader_finds_none(
    service: MedicationService,
    stub_interactions: AsyncMock,
) -> None:
    """상호작용 chunk 가 없으면 빈 배열이다(옛 '항상 빈 배열' 전제의 잔존 케이스)."""
    stub_interactions.return_value = []
    info = _mock_medicine_info(precautions={"경고": ["A"]})

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

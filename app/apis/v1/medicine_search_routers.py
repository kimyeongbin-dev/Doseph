"""Medicine search API routers (autocomplete).

OCR 결과 인라인 편집 / "+ 약 추가" 모달의 실시간 약품명 자동완성용 endpoint.
``GET /api/v1/medicines/suggest?q=…`` — pg_trgm 기반 fuzzy 매칭, prefix 우선.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.dependencies.security import get_current_account
from app.dtos.medicine_search import MedicineSuggestion
from app.models.accounts import Account
from app.services.medicine_search_service import MedicineSearchService

router = APIRouter(prefix="/medicines", tags=["Medicines"])


def get_medicine_search_service() -> MedicineSearchService:
    """Provide a MedicineSearchService instance for DI."""
    return MedicineSearchService()


MedicineSearchServiceDep = Annotated[MedicineSearchService, Depends(get_medicine_search_service)]
CurrentAccount = Annotated[Account, Depends(get_current_account)]


# ── GET /medicines/suggest ─────────────────────────────────────────
# 흐름: query 정규화 (service) -> repository pg_trgm 검색
#       -> prefix 일치 우선 + similarity desc 정렬된 list 반환
@router.get(
    "/suggest",
    response_model=list[MedicineSuggestion],
    summary="약품명 실시간 자동완성",
)
async def suggest_medicines(
    service: MedicineSearchServiceDep,
    _current_account: CurrentAccount,
    q: Annotated[str, Query(min_length=1, max_length=64, description="사용자 입력 (2자 이상부터 매칭)")],
    limit: Annotated[int, Query(ge=1, le=20, description="최대 결과 수 (default 8)")] = 8,
) -> list[MedicineSuggestion]:
    """OCR 결과 / 약 추가 폼의 약품명 인라인 자동완성.

    Args:
        service: 의존성 주입된 ``MedicineSearchService``.
        _current_account: 인증된 계정 (자동완성도 인증 필요).
        q: 사용자 입력 문자열. 2자 미만일 땐 빈 list 가 반환 (service 단 normalize).
        limit: 1 ~ 20.

    Returns:
        list[MedicineSuggestion]: prefix 일치 우선, 그 다음 trigram similarity 내림차순.
    """
    rows = await service.suggest_by_name(query=q, limit=limit)
    return [MedicineSuggestion(**row) for row in rows]

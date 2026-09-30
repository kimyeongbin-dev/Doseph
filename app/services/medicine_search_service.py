"""Medicine search service (autocomplete).

OCR 결과 인라인 편집 / "+ 약 추가" 모달의 약품명 실시간 자동완성용 서비스.
얇은 layer — repository 의 ``autocomplete_by_name`` 결과를 그대로 DTO 로 변환.
business rule 은 query 정규화 (trim + 최소 길이 차단) 만 둔다.
"""

import logging

from app.repositories.medicine_info_repository import MedicineInfoRepository

logger = logging.getLogger(__name__)

# 최소 입력 길이 — 1자 입력 시 결과가 너무 광범위하고 인덱스 효율도 떨어진다.
# 한글 1글자 = 자모 3개 trigram 단위라 2자부터 의미있는 매칭이 시작.
_MIN_QUERY_LENGTH = 2


class MedicineSearchService:
  """약품명 자동완성 (read-only) 서비스."""

  def __init__(self) -> None:
    self.repository = MedicineInfoRepository()

  # ── 자동완성 검색 ────────────────────────────────────────────────
  # 흐름: query trim -> 최소 길이 검증 -> repository fuzzy 검색 -> dict 반환
  async def suggest_by_name(self, query: str, limit: int = 8) -> list[dict]:
    """약품명 자동완성 결과 반환.

    Args:
        query: 사용자 입력. 공백 양쪽 trim 한 뒤 ``_MIN_QUERY_LENGTH`` 미만이면
            빈 list 반환 (불필요한 DB hit + 노이즈 차단).
        limit: 결과 개수 상한. router 단에서 1~20 사이로 강제.

    Returns:
        list[dict]: ``[{id, medicine_name, score}, ...]`` — prefix 일치 우선,
            trigram score desc, 동점 시 name asc.
    """
    normalized = (query or "").strip()
    if len(normalized) < _MIN_QUERY_LENGTH:
      return []
    rows = await self.repository.autocomplete_by_name(query=normalized, limit=limit)
    logger.debug("medicine autocomplete: q=%r -> %d hit", normalized, len(rows))
    return rows

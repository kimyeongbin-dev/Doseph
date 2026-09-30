"""Medicine search DTOs (autocomplete suggestions).

OCR 결과 인라인 편집 / "+ 약 추가" 모달의 약품명 자동완성 응답 schema.
medicine_info 테이블의 pg_trgm 기반 fuzzy 매칭 결과를 prefix 우선 정렬하여
반환하는 ``GET /api/v1/medicines/suggest`` endpoint 의 출력 모델.
"""

from pydantic import BaseModel, ConfigDict, Field


class MedicineSuggestion(BaseModel):
  """약품명 자동완성 항목 한 건."""

  model_config = ConfigDict(from_attributes=True)

  id: int = Field(..., description="medicine_info.id")
  medicine_name: str = Field(..., description="등록된 한국어 약품명 (DB 정규형)")
  score: float = Field(..., ge=0.0, le=1.0, description="trigram similarity (0.0 ~ 1.0). prefix 일치는 보통 1.0 근접.")

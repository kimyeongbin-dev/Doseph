"""Hybrid Metadata Retriever — JSONB ?| 메타 필터 + halfvec cosine top-K.

`plan/2026-08-11_rag-query-rewriter-plan.md` (PR-C). Query Rewriter (PR-B) 의 QueryMetadata 와 임베딩
1회로 통합 검색.

이전 흐름 (HybridRetriever fan-out + RRF intra-query) 폐기:
- fan-out 분산 → 단일 query (Query Rewriter 의 rewritten_query)
- RRF intra-query → 메타필터 + cosine 단일 ranking (메타로 좁혀진 후보 안에서)
- BM25 → 본 PR 보류 (한국어 mecab 부재 + 메타필터로 충분)

흐름:
  rewritten_query (1개)
    -> encode_query (OpenAI 1회)
    -> hybrid SQL: ingredients ?| ARRAY[ingredients]
                   AND section = ANY(sections)
                   AND (target_conditions = '[]' OR target_conditions ?| ARRAY[conditions])
                   AND distance < threshold
                   ORDER BY distance ASC LIMIT N
    -> RetrievedChunk list
"""

from dataclasses import dataclass
from typing import Any

from tortoise import connections


@dataclass(frozen=True)
class RetrievedChunk:
    """Hybrid retrieval 결과 1건 - 2nd LLM context assembler 친화 dict 변환 가능."""

    medicine_info_id: int
    medicine_name: str
    section: str
    content: str
    ingredients: list[str]
    target_conditions: list[str]
    distance: float

    @property
    def similarity(self) -> float:
        """Cosine distance -> similarity (1 - distance, 0~1 범위)."""
        return 1.0 - self.distance

    def to_dict(self) -> dict[str, Any]:
        """rag_context_assembler 호환 dict (medicine_name/section/content/score)."""
        return {
            "medicine_name": self.medicine_name,
            "section": self.section,
            "content": self.content,
            "ingredients": self.ingredients,
            "score": round(self.similarity, 3),
        }


def _vector_literal(embedding: list[float]) -> str:
    """Pgvector 입력 형식 - '[v1,v2,...]'. embed scripts 와 동일 패턴."""
    return "[" + ",".join(f"{v:.6f}" for v in embedding) + "]"


def _build_hybrid_sql(
    *,
    has_section_filter: bool,
    has_condition_filter: bool,
) -> str:
    """SQL 빌더 - 동적 WHERE 절은 사전 컴파일된 옵션 분기로 처리.

    ingredient 필터는 항상 적용 (필수). section / condition 은 list 가
    비어있으면 SQL 절 자체를 생략 (planner 가 추가 비용 0).
    """
    conditions: list[str] = ["mc.ingredients ?| $2::text[]"]
    if has_section_filter:
        conditions.append("mc.section = ANY($3::text[])")
    if has_condition_filter:
        # chunk 의 target_conditions 가 비어있거나 (일반 chunk) 또는
        # 사용자 condition 과 교집합 있으면 통과.
        idx = "$4" if has_section_filter else "$3"
        conditions.append(f"(mc.target_conditions = '[]'::jsonb OR mc.target_conditions ?| {idx}::text[])")
    where_clause = " AND ".join(conditions)
    return f"""
        SELECT mc.id AS chunk_id,
               mc.medicine_info_id,
               mi.medicine_name,
               mc.section,
               mc.content,
               mc.ingredients,
               mc.target_conditions,
               (mc.embedding <=> $1::halfvec(3072)) AS distance
        FROM medicine_chunk mc
        JOIN medicine_info mi ON mi.id = mc.medicine_info_id
        WHERE {where_clause}
        ORDER BY distance ASC
        LIMIT ${3 + int(has_section_filter) + int(has_condition_filter)}
    """  # noqa: S608  # nosec B608 — where_clause 는 코드 내부 상수 + 값은 $N 바인딩 → SQL injection 안전


async def retrieve_with_metadata(
    *,
    query_embedding: list[float],
    target_ingredients: list[str],
    target_sections: list[str] | None = None,
    target_conditions: list[str] | None = None,
    limit: int = 15,
) -> list[RetrievedChunk]:
    """Hybrid retrieval - 메타 필터 + halfvec cosine top-K.

    Args:
        query_embedding: rewritten_query 의 사전계산 3072d 벡터.
        target_ingredients: ingredient 필터 (target_ingredients +
            interaction_concerns). 빈 list 면 빈 결과 반환 (필수 필터).
        target_sections: chunk section 필터. None/빈 list 면 모든 섹션.
        target_conditions: 환자상태 필터. None/빈 list 면 condition 필터 생략.
            전달 시 chunk 의 target_conditions 가 비어있거나 사용자
            condition 과 교집합 있는 chunk 만 통과.
        limit: top-K cap.

    Returns:
        RetrievedChunk list - distance ASC 순서. ingredients 빈 list 면
        빈 list 반환 (메타필터 source 부재).
    """
    if not target_ingredients:
        return []

    has_section_filter = bool(target_sections)
    has_condition_filter = bool(target_conditions)
    sql = _build_hybrid_sql(
        has_section_filter=has_section_filter,
        has_condition_filter=has_condition_filter,
    )

    params: list[Any] = [_vector_literal(query_embedding), target_ingredients]
    if has_section_filter:
        params.append(target_sections)
    if has_condition_filter:
        params.append(target_conditions)
    params.append(limit)

    rows = await connections.get("default").execute_query_dict(sql, params)
    return [
        RetrievedChunk(
            medicine_info_id=row["medicine_info_id"],
            medicine_name=row["medicine_name"],
            section=row["section"],
            content=row["content"],
            ingredients=list(row["ingredients"] or []),
            target_conditions=list(row["target_conditions"] or []),
            distance=float(row["distance"]),
        )
        for row in rows
    ]

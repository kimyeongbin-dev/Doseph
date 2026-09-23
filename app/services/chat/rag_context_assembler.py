"""RAG tool_results → 2nd LLM system prompt 의 [검색된 약품 정보] 섹션 조립.

사라진 계획 «feature/RAG» §3 Step 4 + F1 결정.
🔑 포맷의 정본 = `app/services/tools/context_format.py`.

흐름:
  fanout 으로 search_medicine_knowledge_base x N 호출
    → tool_results: {tool_call_id_1: {"chunks": [...]}, tool_call_id_2: ...}
    → 모든 chunks 평탄화 + (medicine_name, section, chunk_index) 기준 dedup
    → format_rag_context 로 markdown 섹션 작성
"""

from typing import Any

from app.services.tools.context_format import format_rag_context

_RAG_SECTION_HEADER = "[검색된 약품 정보]"


def assemble_rag_section(tool_results: dict[str, Any], cap: int = 15) -> str:
    """tool_results dict → RAG context markdown 섹션.

    Args:
        tool_results: {tool_call_id: {"chunks": [...]}} 또는
            {tool_call_id: {"error": "..."}} 형식. ai_worker.run_tool_calls_job
            의 반환값 직접 입력 가능.
        cap: 최종 chunk 수 상한 (RRF 적용 후). 기본 15 (lost-in-middle 회피).

    Returns:
        '[검색된 약품 정보]' 헤더 + chunks N줄 markdown. 빈 chunks 면 빈 문자열.
    """
    flattened = _flatten_chunks(tool_results)
    if not flattened:
        return ""

    deduped = _dedup_chunks(flattened)
    body = format_rag_context(deduped, cap=cap)
    if not body:
        return ""
    return _RAG_SECTION_HEADER + "\n" + body


def _flatten_chunks(tool_results: dict[str, Any]) -> list[dict[str, Any]]:
    """tool_results 의 모든 'chunks' 키를 단일 list 로 평탄화.

    'error' 인 result 는 skip. 'chunks' 가 없는 result 도 skip.
    """
    out: list[dict[str, Any]] = []
    for result in tool_results.values():
        if not isinstance(result, dict):
            continue
        if "error" in result:
            continue
        chunks = result.get("chunks")
        if not chunks:
            continue
        out.extend(chunks)
    return out


def _dedup_chunks(chunks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """(medicine_name, section, content) 3-tuple 기준 중복 제거.

    동일 chunk 가 여러 fan-out query 에서 회수돼도 한 번만 inject.
    score 가 더 높은 hit 우선 (먼저 나온 게 보통 score 더 높음 — Tortoise
    의 retrieval 결과 ORDER BY score DESC).
    """
    seen: set[tuple[str, str, str]] = set()
    out: list[dict[str, Any]] = []
    for chunk in chunks:
        key = (
            chunk.get("medicine_name", ""),
            chunk.get("section", ""),
            chunk.get("content", ""),
        )
        if key in seen:
            continue
        seen.add(key)
        out.append(chunk)
    return out

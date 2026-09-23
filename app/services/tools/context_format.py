"""RAG context formatter — chunks list → 2nd LLM system prompt 의 검색 결과 섹션.

사라진 계획 «feature/RAG» §3 F1 — `[약: name][section]: content` 포맷 명시.
🔑 **정본은 이 파일이다** — chunk 헤더 포맷을 여기서 만든다.

정책:
- top-N cap (기본 15) 으로 token 폭발 차단
- 각 chunk content 1500 자 truncate (안전 마진)
- 섹션 한국어 표시 (DRUG_INTERACTION → '약물 상호작용' 등)
- 빈 chunks 면 빈 문자열 반환 (섹션 자체 생략 가능)
"""

from typing import Any


def format_rag_context(chunks: list[dict[str, Any]], cap: int = 15, max_content_chars: int = 1500) -> str:
    """RAG retrieval 결과 chunks 를 2nd LLM 친화 markdown 섹션으로 조립.

    Args:
        chunks: ai_worker.rag.retrieval._serialize_chunks 의 결과. 각 dict 는
            {medicine_name, section, content, score} 키 보유.
        cap: 최종 포함할 chunk 수 상한. 기본 15 (lost-in-middle 회피).
        max_content_chars: 각 chunk content 의 최대 char 수. 기본 1500.

    Returns:
        markdown 섹션. 빈 chunks 면 빈 문자열.
    """
    if not chunks:
        return ""

    lines: list[str] = []
    for chunk in chunks[:cap]:
        name = chunk.get("medicine_name", "")
        section = chunk.get("section", "")
        content = chunk.get("content", "")
        if len(content) > max_content_chars:
            content = content[:max_content_chars] + "..."
        # 줄바꿈을 단일 공백으로 collapse — 한 chunk = 한 줄 가독성
        content_one_line = " ".join(content.split())
        lines.append(f"[약: {name}] [{section}]: {content_one_line}")

    return "\n".join(lines)

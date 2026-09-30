"""Unit tests for app.services.tools.context_format — RAG chunks → markdown 섹션.

PLAN.md §4.1 — F1 결정의 4가지 검증. Phase 3 [Implement] Green.
"""

from __future__ import annotations

from app.services.tools.context_format import format_rag_context

SAMPLE_CHUNKS = [
  {
    "medicine_name": "타이레놀",
    "section": "drug_interaction",
    "content": "와파린과 병용 시 INR 상승으로 출혈 위험 증가.",
    "score": 0.95,
  },
  {
    "medicine_name": "와파린",
    "section": "drug_interaction",
    "content": "아세트아미노펜 병용 시 출혈 위험.",
    "score": 0.92,
  },
]


class TestFormatRagContext:
  """format_rag_context 단위 테스트."""

  def test_basic_format(self) -> None:
    """기본 케이스 — 2 chunks → 2줄 markdown."""
    result = format_rag_context(SAMPLE_CHUNKS)
    lines = result.split("\n")
    assert len(lines) == 2
    assert lines[0].startswith("[약: 타이레놀] [drug_interaction]:")
    assert "와파린과 병용" in lines[0]
    assert lines[1].startswith("[약: 와파린] [drug_interaction]:")

  def test_empty_chunks(self) -> None:
    """빈 chunks → 빈 문자열."""
    assert format_rag_context([]) == ""

  def test_cap_applied(self) -> None:
    """20 chunks 입력 + cap=15 → 15 줄로 잘림."""
    chunks = [{"medicine_name": f"약{i}", "section": "overview", "content": "내용", "score": 0.5} for i in range(20)]
    result = format_rag_context(chunks, cap=15)
    assert len(result.split("\n")) == 15

  def test_long_content_truncated(self) -> None:
    """content 가 1500 자 초과 → truncate + '...' suffix."""
    long = "가" * 5000
    chunks = [{"medicine_name": "약", "section": "overview", "content": long, "score": 0.9}]
    result = format_rag_context(chunks, max_content_chars=1500)
    # prefix '[약: 약] [overview]: ' + 1500 char + '...' suffix 정도
    assert "..." in result
    # 본문 길이가 5000 보다 훨씬 짧아져야 함
    assert len(result) < 2500

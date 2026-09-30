"""Unit tests for app.services.chat.rag_context_assembler."""

from __future__ import annotations

from app.services.chat.rag_context_assembler import assemble_rag_section


def _result(chunks: list[dict]) -> dict:
  return {"chunks": chunks}


class TestAssembleRagSection:
  """assemble_rag_section 단위 테스트."""

  def test_basic(self) -> None:
    tool_results = {
      "call_1": _result([
        {
          "medicine_name": "타이레놀",
          "section": "drug_interaction",
          "content": "와파린과 병용 시 INR 상승.",
          "score": 0.95,
        },
      ]),
      "call_2": _result([
        {
          "medicine_name": "와파린",
          "section": "drug_interaction",
          "content": "아세트아미노펜 병용 시 출혈 위험.",
          "score": 0.92,
        },
      ]),
    }
    result = assemble_rag_section(tool_results)
    assert result.startswith("[검색된 약품 정보]")
    assert "타이레놀" in result
    assert "와파린" in result

  def test_empty_tool_results(self) -> None:
    assert assemble_rag_section({}) == ""

  def test_all_errors(self) -> None:
    """모든 tool_result 가 error 면 빈 문자열."""
    tool_results = {
      "call_1": {"error": "ConnectionError"},
      "call_2": {"error": "Timeout"},
    }
    assert assemble_rag_section(tool_results) == ""

  def test_dedup_across_calls(self) -> None:
    """같은 chunk 가 여러 fan-out 에서 회수돼도 1번만 출력."""
    same_chunk = {
      "medicine_name": "타이레놀",
      "section": "adverse_reaction",
      "content": "흔한 부작용은 오심.",
      "score": 0.9,
    }
    tool_results = {
      "call_1": _result([same_chunk]),
      "call_2": _result([same_chunk]),
      "call_3": _result([same_chunk]),
    }
    result = assemble_rag_section(tool_results)
    # body 의 줄 수 (헤더 제외)
    body_lines = result.split("\n")[1:]
    assert len(body_lines) == 1

  def test_cap_applied(self) -> None:
    """50 chunks → cap=15."""
    chunks = [
      {"medicine_name": f"약{i}", "section": "overview", "content": f"내용{i}", "score": 0.5} for i in range(50)
    ]
    result = assemble_rag_section({"call_1": _result(chunks)}, cap=15)
    body_lines = result.split("\n")[1:]
    assert len(body_lines) == 15

  def test_mixed_error_and_chunks(self) -> None:
    """error 와 정상 chunks 혼재 — 정상만 inject."""
    tool_results = {
      "call_1": _result([{"medicine_name": "약A", "section": "overview", "content": "내용A"}]),
      "call_2": {"error": "permanent"},
      "call_3": _result([{"medicine_name": "약B", "section": "overview", "content": "내용B"}]),
    }
    result = assemble_rag_section(tool_results)
    assert "약A" in result
    assert "약B" in result

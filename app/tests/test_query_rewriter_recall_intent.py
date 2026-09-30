"""Query Rewriter 의 recall_check 의도 분류 테스트 (Step 2 Red).

drug_recall 회귀 핫픽스 — IntentType.RECALL_CHECK + RecallQuery DTO 가
1st LLM Structured Output 으로 정상 round-trip 되는지 검증.
"""

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.dtos.query_rewriter import (
  IntentType,
  QueryRewriterOutput,
  RecallMode,
  RecallQuery,
)
from app.services.intent import query_rewriter


def _fake_client_returning(parsed: QueryRewriterOutput) -> MagicMock:
  completion = MagicMock()
  completion.choices = [MagicMock(message=MagicMock(parsed=parsed))]

  client = MagicMock()
  client.beta.chat.completions.parse = AsyncMock(return_value=completion)
  return client


@pytest.fixture(autouse=True)
def _reset_client_singleton(monkeypatch: pytest.MonkeyPatch) -> None:
  monkeypatch.setattr(query_rewriter, "_client", None)
  monkeypatch.setattr(query_rewriter, "_initialised", False)


# ── DTO ─────────────────────────────────────────────────────────


class TestRecallQueryDto:
  def test_user_mode_no_manufacturer(self) -> None:
    q = RecallQuery(mode=RecallMode.USER)
    assert q.mode == RecallMode.USER
    assert q.manufacturer is None

  def test_manufacturer_mode_with_name(self) -> None:
    q = RecallQuery(mode=RecallMode.MANUFACTURER, manufacturer="동국제약")
    assert q.mode == RecallMode.MANUFACTURER
    assert q.manufacturer == "동국제약"


# ── IntentType.RECALL_CHECK 가 enum 에 추가되었는지 ─────────────


class TestIntentEnum:
  def test_recall_check_member_exists(self) -> None:
    assert IntentType.RECALL_CHECK.value == "recall_check"

  def test_intent_count_is_six(self) -> None:
    assert len(list(IntentType)) == 6


# ── 1st LLM 분류 결과 round-trip ────────────────────────────────


class TestRewriteQueryRecallIntent:
  @pytest.mark.asyncio
  async def test_user_mode_intent(self, monkeypatch: pytest.MonkeyPatch) -> None:
    parsed = QueryRewriterOutput(
      intent=IntentType.RECALL_CHECK,
      recall_query=RecallQuery(mode=RecallMode.USER),
    )
    monkeypatch.setattr(query_rewriter, "_get_client", lambda: _fake_client_returning(parsed))

    out = await query_rewriter.rewrite_query(
      messages=[{"role": "user", "content": "내 약 회수된 거 있어?"}],
    )
    assert out.intent == IntentType.RECALL_CHECK
    assert out.recall_query is not None
    assert out.recall_query.mode == RecallMode.USER
    assert out.recall_query.manufacturer is None

  @pytest.mark.asyncio
  async def test_manufacturer_mode_intent(self, monkeypatch: pytest.MonkeyPatch) -> None:
    parsed = QueryRewriterOutput(
      intent=IntentType.RECALL_CHECK,
      recall_query=RecallQuery(mode=RecallMode.MANUFACTURER, manufacturer="동국제약"),
    )
    monkeypatch.setattr(query_rewriter, "_get_client", lambda: _fake_client_returning(parsed))

    out = await query_rewriter.rewrite_query(
      messages=[{"role": "user", "content": "동국제약 회수 이력 알려줘"}],
    )
    assert out.intent == IntentType.RECALL_CHECK
    assert out.recall_query is not None
    assert out.recall_query.mode == RecallMode.MANUFACTURER
    assert out.recall_query.manufacturer == "동국제약"

  @pytest.mark.asyncio
  async def test_domain_question_unaffected(self, monkeypatch: pytest.MonkeyPatch) -> None:
    """회귀 보호 — recall 무관한 의학 질문은 domain_question 으로 분류."""
    from app.dtos.query_rewriter import QueryMetadata

    parsed = QueryRewriterOutput(
      intent=IntentType.DOMAIN_QUESTION,
      rewritten_query="타이레놀(아세트아미노펜) 부작용",
      metadata=QueryMetadata(target_ingredients=["아세트아미노펜"]),
    )
    monkeypatch.setattr(query_rewriter, "_get_client", lambda: _fake_client_returning(parsed))

    out = await query_rewriter.rewrite_query(
      messages=[{"role": "user", "content": "타이레놀 부작용"}],
    )
    assert out.intent == IntentType.DOMAIN_QUESTION
    assert out.recall_query is None


# ── system_prompt 에 recall_check 분류 규칙 포함 검증 ─────────


class TestSystemPromptHasRecallRule:
  def test_prompt_mentions_recall_check(self) -> None:
    prompt: Any = query_rewriter.SYSTEM_PROMPT
    assert "recall_check" in prompt
    # 회수 도메인 핵심 동의어
    assert "회수" in prompt
    assert "판매중지" in prompt or "리콜" in prompt

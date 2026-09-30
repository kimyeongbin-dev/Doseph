"""Unit tests for app.services.intent.query_rewriter — 1st LLM Structured Output.

PLAN.md (RAG 재설계 PR-B). gpt-4o-mini 호출은 mock — 실제 OpenAI API 호출 X.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.dtos.query_rewriter import (
  IntentType,
  QueryMetadata,
  QueryRewriterOutput,
)
from app.services.intent import query_rewriter as rewriter_module
from app.services.intent.query_rewriter import rewrite_query


@pytest.fixture
def stub_openai_client(monkeypatch: pytest.MonkeyPatch):
  """OpenAI client 의 beta.chat.completions.parse 를 stub. 반환값을 set 가능."""
  parsed_holder: dict[str, QueryRewriterOutput | None] = {"value": None}
  captured: dict[str, object] = {"messages": None}

  async def _fake_parse(**kwargs):
    captured["messages"] = kwargs.get("messages")
    captured["response_format"] = kwargs.get("response_format")
    completion = MagicMock()
    completion.choices = [MagicMock()]
    completion.choices[0].message.parsed = parsed_holder["value"]
    return completion

  fake_client = MagicMock()
  fake_client.beta.chat.completions.parse = AsyncMock(side_effect=_fake_parse)

  # _get_client / _initialised 캐시 강제 리셋
  monkeypatch.setattr(rewriter_module, "_client", fake_client)
  monkeypatch.setattr(rewriter_module, "_initialised", True)

  def _set_parsed(value: QueryRewriterOutput | None) -> None:
    parsed_holder["value"] = value

  return captured, _set_parsed


class TestRewriteQueryMessageAssembly:
  """system_prompt + medical_context 합성."""

  @pytest.mark.asyncio
  async def test_medical_context_appended_to_system_prompt(
    self,
    stub_openai_client: tuple[dict[str, object], object],
  ) -> None:
    captured, set_parsed = stub_openai_client
    set_parsed(
      QueryRewriterOutput(
        intent=IntentType.DOMAIN_QUESTION,
        rewritten_query="간 질환 환자 타이레놀 복용",
        metadata=QueryMetadata(
          target_drugs=["타이레놀"],
          target_ingredients=["아세트아미노펜"],
        ),
      )
    )

    await rewrite_query(
      messages=[{"role": "user", "content": "타이레놀 먹어도 돼?"}],
      medical_context="[사용자 의학 컨텍스트]\n- 기저질환: 간질환",
    )

    msgs = captured["messages"]
    assert msgs[0]["role"] == "system"
    # system_prompt 의 설정 + medical_context 모두 합쳐 system 에 들어감
    assert "Query Rewriter" in msgs[0]["content"]
    assert "[사용자 의학 컨텍스트]" in msgs[0]["content"]
    assert "간질환" in msgs[0]["content"]
    # user 메시지 그대로 propagate
    assert msgs[1] == {"role": "user", "content": "타이레놀 먹어도 돼?"}

  @pytest.mark.asyncio
  async def test_no_medical_context_only_system_prompt(
    self,
    stub_openai_client: tuple[dict[str, object], object],
  ) -> None:
    captured, set_parsed = stub_openai_client
    set_parsed(QueryRewriterOutput(intent=IntentType.GREETING, direct_answer="안녕"))

    await rewrite_query(
      messages=[{"role": "user", "content": "안녕"}],
      medical_context=None,
    )

    msgs = captured["messages"]
    # medical_context 없으면 system 에 헤더 없음
    assert "[사용자 의학 컨텍스트]" not in msgs[0]["content"]


class TestRewriteQueryParsedFallback:
  """Structured Output 가 None 또는 client 부재 시 fallback."""

  @pytest.mark.asyncio
  async def test_parsed_none_returns_ambiguous_fallback(
    self,
    stub_openai_client: tuple[dict[str, object], object],
  ) -> None:
    _captured, set_parsed = stub_openai_client
    set_parsed(None)  # OpenAI 가 schema 못 맞춘 극단 케이스

    result = await rewrite_query(
      messages=[{"role": "user", "content": "..."}],
    )
    assert result.intent == IntentType.AMBIGUOUS
    assert result.direct_answer is not None
    assert "질문을 정확히 이해하지 못했어요" in result.direct_answer

  @pytest.mark.asyncio
  async def test_no_api_key_returns_ambiguous_fallback(
    self,
    monkeypatch: pytest.MonkeyPatch,
  ) -> None:
    # _get_client 가 None 반환 (api_key 없음) 시 fallback 직접
    monkeypatch.setattr(rewriter_module, "_client", None)
    monkeypatch.setattr(rewriter_module, "_initialised", True)

    result = await rewrite_query(messages=[{"role": "user", "content": "안녕"}])
    assert result.intent == IntentType.AMBIGUOUS
    assert "AI 응답 설정" in (result.direct_answer or "")


class TestRewriteQueryIntentBranches:
  """4가지 intent 분기 — Structured Output 결과 그대로 propagate."""

  @pytest.mark.asyncio
  async def test_greeting_branch(
    self,
    stub_openai_client: tuple[dict[str, object], object],
  ) -> None:
    _, set_parsed = stub_openai_client
    set_parsed(QueryRewriterOutput(intent=IntentType.GREETING, direct_answer="안녕하세요"))
    result = await rewrite_query(messages=[{"role": "user", "content": "안녕"}])
    assert result.intent == IntentType.GREETING
    assert result.direct_answer == "안녕하세요"
    assert result.rewritten_query is None
    assert result.metadata is None

  @pytest.mark.asyncio
  async def test_out_of_scope_branch(
    self,
    stub_openai_client: tuple[dict[str, object], object],
  ) -> None:
    _, set_parsed = stub_openai_client
    set_parsed(QueryRewriterOutput(intent=IntentType.OUT_OF_SCOPE, direct_answer="저는 약 챗봇이에요"))
    result = await rewrite_query(messages=[{"role": "user", "content": "오늘 날씨"}])
    assert result.intent == IntentType.OUT_OF_SCOPE
    assert result.rewritten_query is None

  @pytest.mark.asyncio
  async def test_domain_question_with_metadata(
    self,
    stub_openai_client: tuple[dict[str, object], object],
  ) -> None:
    _, set_parsed = stub_openai_client
    meta = QueryMetadata(
      target_drugs=["타이레놀"],
      target_ingredients=["아세트아미노펜"],
      target_conditions=["liver_disease"],
      target_sections=["drug_interaction", "adverse_reaction"],
      interaction_concerns=["와파린나트륨"],
    )
    set_parsed(
      QueryRewriterOutput(
        intent=IntentType.DOMAIN_QUESTION,
        rewritten_query="간 질환 환자가 와파린 복용 중 아세트아미노펜 병용 시 출혈 위험",
        metadata=meta,
      )
    )

    result = await rewrite_query(
      messages=[{"role": "user", "content": "타이레놀 먹어도 돼?"}],
      medical_context="[사용자 의학 컨텍스트]\n- 기저질환: 간질환\n- 복용 중인 약: 쿠파린정",
    )
    assert result.intent == IntentType.DOMAIN_QUESTION
    assert result.direct_answer is None
    assert result.rewritten_query is not None
    assert "간 질환" in result.rewritten_query
    assert result.metadata is not None
    assert result.metadata.target_ingredients == ["아세트아미노펜"]
    assert result.metadata.target_conditions == ["liver_disease"]
    assert result.metadata.interaction_concerns == ["와파린나트륨"]
    assert result.metadata.target_sections == ["drug_interaction", "adverse_reaction"]

  @pytest.mark.asyncio
  async def test_ambiguous_branch(
    self,
    stub_openai_client: tuple[dict[str, object], object],
  ) -> None:
    _, set_parsed = stub_openai_client
    set_parsed(QueryRewriterOutput(intent=IntentType.AMBIGUOUS, direct_answer="어느 약?"))
    result = await rewrite_query(messages=[{"role": "user", "content": "그거 먹어도 돼?"}])
    assert result.intent == IntentType.AMBIGUOUS
    assert result.direct_answer == "어느 약?"

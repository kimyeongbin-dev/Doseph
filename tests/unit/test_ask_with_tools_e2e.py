"""e2e mock 통합 테스트 - MessageService.ask_with_tools (PR-D 재설계 후).

PLAN.md (RAG 재설계 PR-D) - 단순 3단계 직선 흐름:
  1. classify_user_turn (medical_context + ingredient_mapping + Query Rewriter)
  2. (domain_question) encode_query + retrieve_with_metadata
  3. _compose_system_prompt + generate_chat_response_via_rq (2nd LLM)

실 OpenAI / DB 호출은 모두 mock. 흐름 자체의 정합성만 검증.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

import pytest

from app.dtos.query_rewriter import IntentType, QueryMetadata, QueryRewriterOutput
from app.services import message_service as ms_module
from app.services.rag.retrievers.hybrid_metadata import RetrievedChunk

SESSION_ID = uuid4()
ACCOUNT_ID = uuid4()
PROFILE_ID = uuid4()


def _stub_chat_session(profile_id: UUID, account_id: UUID) -> MagicMock:
  session = MagicMock()
  session.id = SESSION_ID
  session.profile_id = profile_id
  session.account_id = account_id
  session.summary = None
  return session


def _stub_msg(content: str) -> MagicMock:
  m = MagicMock()
  m.content = content
  m.id = uuid4()
  return m


@pytest.fixture
def service() -> ms_module.MessageService:
  svc = ms_module.MessageService(queue=MagicMock())
  svc.session_repository = MagicMock()
  svc.session_repository.get_by_id = AsyncMock(return_value=_stub_chat_session(PROFILE_ID, ACCOUNT_ID))
  svc.repository = MagicMock()
  svc.repository.get_recent_by_session = AsyncMock(return_value=[])
  svc.repository.create_user_message = AsyncMock(side_effect=lambda _sid, content: _stub_msg(content))
  svc.repository.create_assistant_message = AsyncMock(side_effect=lambda _sid, content: _stub_msg(content))
  svc.repository.count_by_session = AsyncMock(return_value=2)
  svc.repository.soft_delete = AsyncMock()
  return svc


class TestAskWithToolsDirectAnswer:
  """direct_answer 분기 - greeting/out_of_scope/ambiguous 즉시 응답."""

  @pytest.mark.asyncio
  async def test_greeting_no_retrieval(
    self,
    service: ms_module.MessageService,
    monkeypatch: pytest.MonkeyPatch,
  ) -> None:
    async def _fake_classify(_pid, _msgs):
      return (
        "",
        "",
        QueryRewriterOutput(intent=IntentType.GREETING, direct_answer="안녕하세요"),
      )

    retrieve_mock = AsyncMock()
    generate_mock = AsyncMock()
    encode_mock = AsyncMock(return_value=[0.0] * 3072)
    monkeypatch.setattr(ms_module, "classify_user_turn", _fake_classify)
    monkeypatch.setattr(ms_module, "retrieve_with_metadata", retrieve_mock)
    monkeypatch.setattr(ms_module, "generate_chat_response_via_rq", generate_mock)
    monkeypatch.setattr(ms_module, "encode_query", encode_mock)

    result = await service.ask_with_tools(session_id=SESSION_ID, account_id=ACCOUNT_ID, content="안녕")
    assert result.assistant_message.content == "안녕하세요"
    retrieve_mock.assert_not_called()
    generate_mock.assert_not_called()
    encode_mock.assert_not_called()


class TestAskWithToolsDomainQuestion:
  """5-1 시나리오 - domain_question 분기 (rewritten_query + metadata → retrieval → 2nd LLM)."""

  @pytest.mark.asyncio
  async def test_full_pipeline_with_metadata(
    self,
    service: ms_module.MessageService,
    monkeypatch: pytest.MonkeyPatch,
  ) -> None:
    meta = QueryMetadata(
      target_drugs=["타이레놀"],
      target_ingredients=["아세트아미노펜"],
      target_conditions=["liver_disease"],
      target_sections=["drug_interaction", "adverse_reaction"],
      interaction_concerns=["와파린나트륨"],
    )

    async def _fake_classify(_pid, _msgs):
      return (
        "[사용자 의학 컨텍스트]\n- 복용 중인 약: 쿠파린정\n- 기저질환: 간질환",
        "[용어 매핑]\n- 쿠파린정 → 성분: 와파린나트륨",
        QueryRewriterOutput(
          intent=IntentType.DOMAIN_QUESTION,
          rewritten_query=("간 질환 환자가 와파린(쿠파린정) 복용 중 아세트아미노펜(타이레놀) 병용 시 출혈/간 손상"),
          metadata=meta,
        ),
      )

    captured: dict[str, Any] = {}

    async def _fake_encode(query: str) -> list[float]:
      captured["embedded"] = query
      return [0.5] * 3072

    async def _fake_retrieve(**kwargs):
      captured["retrieve_kwargs"] = kwargs
      return [
        RetrievedChunk(
          medicine_info_id=1,
          medicine_name="타이레놀이알서방정",
          section="drug_interaction",
          content="와파린 병용 시 INR 상승, 출혈 위험",
          ingredients=["아세트아미노펜"],
          target_conditions=[],
          distance=0.18,
        ),
      ]

    async def _fake_generate(*, messages, system_prompt, queue):
      del queue
      captured["messages"] = messages
      captured["system_prompt"] = system_prompt
      return {"answer": "타이레놀(아세트아미노펜) 와파린 병용 시 INR ...", "token_usage": None}

    monkeypatch.setattr(ms_module, "classify_user_turn", _fake_classify)
    monkeypatch.setattr(ms_module, "encode_query", _fake_encode)
    monkeypatch.setattr(ms_module, "retrieve_with_metadata", _fake_retrieve)
    monkeypatch.setattr(ms_module, "generate_chat_response_via_rq", _fake_generate)

    result = await service.ask_with_tools(session_id=SESSION_ID, account_id=ACCOUNT_ID, content="타이레놀 먹어도 돼?")

    # 1. encode_query 가 rewritten_query 를 임베딩
    assert "간 질환 환자" in captured["embedded"]

    # 2. retrieve_with_metadata 의 ingredient 필터 = target + interaction union
    kwargs = captured["retrieve_kwargs"]
    assert set(kwargs["target_ingredients"]) == {"아세트아미노펜", "와파린나트륨"}
    assert kwargs["target_sections"] == ["drug_interaction", "adverse_reaction"]
    assert kwargs["target_conditions"] == ["liver_disease"]

    # 3. 2nd LLM system_prompt 에 medical_context + 용어 매핑 + RAG 모두 prepend
    sp = captured["system_prompt"]
    assert "[사용자 의학 컨텍스트]" in sp
    assert "[용어 매핑]" in sp
    assert "[검색된 약품 정보]" in sp
    assert "타이레놀이알서방정" in sp

    # 4. user 메시지 raw 그대로 propagate
    assert any(m["role"] == "user" and m["content"] == "타이레놀 먹어도 돼?" for m in captured["messages"])

    # 5. assistant persist
    assert "타이레놀" in result.assistant_message.content

  @pytest.mark.asyncio
  async def test_domain_without_metadata_fallback(
    self,
    service: ms_module.MessageService,
    monkeypatch: pytest.MonkeyPatch,
  ) -> None:
    """domain_question 인데 rewritten_query / metadata 누락 → fallback."""

    async def _fake_classify(_pid, _msgs):
      return (
        "",
        "",
        QueryRewriterOutput(intent=IntentType.DOMAIN_QUESTION, rewritten_query=None),
      )

    retrieve_mock = AsyncMock()
    generate_mock = AsyncMock()
    encode_mock = AsyncMock()
    monkeypatch.setattr(ms_module, "classify_user_turn", _fake_classify)
    monkeypatch.setattr(ms_module, "retrieve_with_metadata", retrieve_mock)
    monkeypatch.setattr(ms_module, "generate_chat_response_via_rq", generate_mock)
    monkeypatch.setattr(ms_module, "encode_query", encode_mock)

    result = await service.ask_with_tools(session_id=SESSION_ID, account_id=ACCOUNT_ID, content="약?")
    assert "구체적" in result.assistant_message.content
    retrieve_mock.assert_not_called()


class TestAskWithToolsRollback:
  """예외 발생 시 user 메시지 soft_delete 검증."""

  @pytest.mark.asyncio
  async def test_classify_failure_rolls_back(
    self,
    service: ms_module.MessageService,
    monkeypatch: pytest.MonkeyPatch,
  ) -> None:
    async def _fake_classify(_pid, _msgs):
      raise RuntimeError("4o-mini API down")

    monkeypatch.setattr(ms_module, "classify_user_turn", _fake_classify)

    with pytest.raises(RuntimeError, match="4o-mini API down"):
      await service.ask_with_tools(session_id=SESSION_ID, account_id=ACCOUNT_ID, content="타이레놀")
    service.repository.soft_delete.assert_awaited_once()

"""MessageService.ask_with_tools 의 recall_check 분기 테스트.

drug_recall 회귀 핫픽스 — Query Rewriter 가 ``intent=RECALL_CHECK`` 를
반환했을 때 다음 분기가 정상 동작하는지 검증.

- ``mode=user``         : check_user_medications_recall 호출
- ``mode=manufacturer`` : check_manufacturer_recalls 호출 (manufacturer 선택)

🔑 가짜 도구 실행기 안의 단언은 **그 가짜가 불려야만** 돈다. 그래서 테스트마다
호출 횟수와 최종 답변(가짜 2nd LLM 이 낸 문장)을 바깥에서 다시 단언한다 —
그게 없던 «제조사 이름 없음» 테스트는 분기를 망가뜨려도 초록이었다(B-18 배치 1).
"""

from typing import Any
from unittest.mock import AsyncMock

import pytest

from app.dtos.query_rewriter import IntentType, RecallMode, RecallQuery
from app.services.message_service import MessageService
from app.services.tools.pending import InMemoryPendingTurnStore
from app.tests.chat_service_stubs import ChatStubs, make_classify


def _service() -> MessageService:
  return MessageService(pending_store=InMemoryPendingTurnStore(), queue=object())


# ── A. mode=user (사용자 복용약 전체 회수 매칭) ─────────────────


class TestRecallCheckUserMode:
  @pytest.mark.asyncio
  async def test_user_mode_runs_recall_then_generates_answer(
    self,
    monkeypatch: pytest.MonkeyPatch,
    chat_stubs: ChatStubs,
  ) -> None:
    monkeypatch.setattr(
      "app.services.message_service.classify_user_turn",
      make_classify(IntentType.RECALL_CHECK, recall_query=RecallQuery(mode=RecallMode.USER)),
    )

    captured_calls: list[dict[str, Any]] = []

    async def fake_run(*, calls: list[dict[str, Any]], queue: object, **_: object) -> dict[str, Any]:
      captured_calls.extend(calls)
      assert len(calls) == 1
      assert calls[0]["name"] == "check_user_medications_recall"
      # profile_id top-level 주입 검증 (worker dispatch 가 require)
      assert calls[0]["profile_id"] == str(chat_stubs.profile_id)
      return {calls[0]["tool_call_id"]: {"matched": True, "recalls": [{"item_seq": "X1"}]}}

    async def fake_generate(
      *, messages: list[dict[str, Any]], queue: object, system_prompt: str | None = None
    ) -> dict[str, Any]:
      tool_msgs = [m for m in messages if m.get("role") == "tool"]
      assert len(tool_msgs) == 1
      assert "X1" in tool_msgs[0]["content"]
      return {"answer": "회수된 약 1건이 있습니다.", "token_usage": None}

    monkeypatch.setattr("app.services.message_service.run_tool_calls_via_rq", fake_run)
    monkeypatch.setattr("app.services.message_service.generate_chat_response_via_rq", fake_generate)

    result = await _service().ask_with_tools(
      session_id=chat_stubs.session_id,
      account_id=chat_stubs.account_id,
      content="내 약 회수된 거 있어?",
    )

    assert result.pending is None
    assert result.assistant_message is not None
    assert result.assistant_message.content == "회수된 약 1건이 있습니다."
    assert len(captured_calls) == 1


# ── B. mode=manufacturer (특정 제조사) ───────────────────────────


class TestRecallCheckManufacturerMode:
  @pytest.mark.asyncio
  async def test_manufacturer_mode_with_explicit_name(
    self,
    monkeypatch: pytest.MonkeyPatch,
    chat_stubs: ChatStubs,
  ) -> None:
    monkeypatch.setattr(
      "app.services.message_service.classify_user_turn",
      make_classify(
        IntentType.RECALL_CHECK,
        recall_query=RecallQuery(mode=RecallMode.MANUFACTURER, manufacturer="동국제약"),
      ),
    )

    captured_calls: list[dict[str, Any]] = []

    async def fake_run(*, calls: list[dict[str, Any]], queue: object, **_: object) -> dict[str, Any]:
      captured_calls.extend(calls)
      assert calls[0]["name"] == "check_manufacturer_recalls"
      assert calls[0]["arguments"]["manufacturer"] == "동국제약"
      assert calls[0]["profile_id"] == str(chat_stubs.profile_id)
      return {calls[0]["tool_call_id"]: {"matched": False, "recalls": []}}

    async def fake_generate(
      *, messages: list[dict[str, Any]], queue: object, system_prompt: str | None = None
    ) -> dict[str, Any]:
      return {"answer": "동국제약 회수 이력 없습니다.", "token_usage": None}

    monkeypatch.setattr("app.services.message_service.run_tool_calls_via_rq", fake_run)
    monkeypatch.setattr("app.services.message_service.generate_chat_response_via_rq", fake_generate)

    result = await _service().ask_with_tools(
      session_id=chat_stubs.session_id,
      account_id=chat_stubs.account_id,
      content="동국제약 회수 이력 알려줘",
    )

    assert result.pending is None
    assert result.assistant_message is not None
    assert result.assistant_message.content == "동국제약 회수 이력 없습니다."
    assert len(captured_calls) == 1

  @pytest.mark.asyncio
  async def test_manufacturer_mode_without_name(
    self,
    monkeypatch: pytest.MonkeyPatch,
    chat_stubs: ChatStubs,
  ) -> None:
    """제조사 명시 없으면 worker 가 사용자 복용약 제조사 셋 자동 추출 — manufacturer 키 미포함."""
    monkeypatch.setattr(
      "app.services.message_service.classify_user_turn",
      make_classify(
        IntentType.RECALL_CHECK,
        recall_query=RecallQuery(mode=RecallMode.MANUFACTURER, manufacturer=None),
      ),
    )

    captured_calls: list[dict[str, Any]] = []

    async def fake_run(*, calls: list[dict[str, Any]], queue: object, **_: object) -> dict[str, Any]:
      captured_calls.extend(calls)
      assert calls[0]["name"] == "check_manufacturer_recalls"
      # manufacturer 키가 아예 없거나 None
      assert calls[0]["arguments"].get("manufacturer") in (None, "")
      return {calls[0]["tool_call_id"]: {"matched": False, "recalls": []}}

    async def fake_generate(
      *, messages: list[dict[str, Any]], queue: object, system_prompt: str | None = None
    ) -> dict[str, Any]:
      return {"answer": "복용약 제조사 회수 이력 없음.", "token_usage": None}

    monkeypatch.setattr("app.services.message_service.run_tool_calls_via_rq", fake_run)
    monkeypatch.setattr("app.services.message_service.generate_chat_response_via_rq", fake_generate)

    result = await _service().ask_with_tools(
      session_id=chat_stubs.session_id,
      account_id=chat_stubs.account_id,
      content="제약회사 회수당한 거 있어?",
    )

    assert result.pending is None
    assert result.assistant_message is not None
    # 이 두 단언이 없으면 분기가 되묻기(fallback)로 빠져도 통과한다
    assert len(captured_calls) == 1
    assert result.assistant_message.content == "복용약 제조사 회수 이력 없음."


# ── C. recall_check 인데 recall_query=None (LLM 위반) → fallback ──


class TestRecallCheckMissingQuery:
  @pytest.mark.asyncio
  async def test_missing_recall_query_falls_back_to_direct_answer(
    self,
    monkeypatch: pytest.MonkeyPatch,
    chat_stubs: ChatStubs,
  ) -> None:
    monkeypatch.setattr(
      "app.services.message_service.classify_user_turn",
      make_classify(IntentType.RECALL_CHECK, recall_query=None),
    )
    monkeypatch.setattr(
      "app.services.message_service.run_tool_calls_via_rq",
      AsyncMock(side_effect=AssertionError("호출 금지")),
    )
    monkeypatch.setattr(
      "app.services.message_service.generate_chat_response_via_rq",
      AsyncMock(side_effect=AssertionError("호출 금지")),
    )

    result = await _service().ask_with_tools(
      session_id=chat_stubs.session_id,
      account_id=chat_stubs.account_id,
      content="회수된 거",
    )

    assert result.pending is None
    assert result.assistant_message is not None
    # 되묻기 문구 — 정확한 문장 대신 주제어만 본다(문구는 바뀔 수 있다)
    assert "회수" in result.assistant_message.content

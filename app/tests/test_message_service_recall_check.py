"""MessageService.ask_with_tools 의 recall_check 분기 테스트 (Step 2 Red).

drug_recall 회귀 핫픽스 — Query Rewriter 가 ``intent=RECALL_CHECK`` 를
반환했을 때 다음 분기가 정상 동작하는지 검증.

- ``mode=user``         : check_user_medications_recall 호출
- ``mode=manufacturer`` : check_manufacturer_recalls 호출 (manufacturer 선택)
"""

from typing import Any
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.dtos.query_rewriter import (
    IntentType,
    QueryRewriterOutput,
    RecallMode,
    RecallQuery,
)
from app.services.message_service import MessageService
from app.services.tools.pending import InMemoryPendingTurnStore


class _StubChatMessage:
    def __init__(self, *, message_id: str, content: str, sender_type: str) -> None:
        self.id = message_id
        self.content = content
        self.sender_type = sender_type
        self.metadata: dict[str, Any] = {}


class _StubSession:
    def __init__(self, *, session_id: Any, account_id: Any, profile_id: Any) -> None:
        self.id = session_id
        self.account_id = account_id
        self.profile_id = profile_id
        self.summary = None


@pytest.fixture
def stub_repos(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    captured: dict[str, Any] = {"assistant": [], "user": []}
    session_account = uuid4()
    session_profile = uuid4()
    session_id = uuid4()
    captured["session_id"] = session_id
    captured["account_id"] = session_account
    captured["profile_id"] = session_profile

    async def fake_get_session(_self, sid):
        return _StubSession(session_id=session_id, account_id=session_account, profile_id=session_profile)

    async def fake_recent(_self, _sid, limit):
        return []

    async def fake_user_msg(_self, sid, content):
        msg = _StubChatMessage(message_id=str(uuid4()), content=content, sender_type="USER")
        captured["user"].append(content)
        return msg

    async def fake_assistant_msg(_self, sid, content, metadata=None):
        msg = _StubChatMessage(message_id=str(uuid4()), content=content, sender_type="ASSISTANT")
        msg.metadata = metadata or {}
        captured["assistant"].append(content)
        return msg

    async def fake_count(_self, _sid):
        return 0

    async def fake_soft_delete(_self, _msg):
        return None

    from app.repositories.chat_session_repository import ChatSessionRepository
    from app.repositories.message_repository import MessageRepository

    monkeypatch.setattr(ChatSessionRepository, "get_by_id", fake_get_session)
    monkeypatch.setattr(MessageRepository, "get_recent_by_session", fake_recent)
    monkeypatch.setattr(MessageRepository, "create_user_message", fake_user_msg)
    monkeypatch.setattr(MessageRepository, "create_assistant_message", fake_assistant_msg)
    monkeypatch.setattr(MessageRepository, "count_by_session", fake_count)
    monkeypatch.setattr(MessageRepository, "soft_delete", fake_soft_delete)
    return captured


def _make_classify(intent: IntentType, **kwargs: Any):
    output = QueryRewriterOutput(intent=intent, **kwargs)

    async def _fake(_profile_id, _messages):
        return ("", "", output)

    return _fake


# ── A. mode=user (사용자 복용약 전체 회수 매칭) ─────────────────


class TestRecallCheckUserMode:
    @pytest.mark.asyncio
    async def test_user_mode_runs_recall_then_generates_answer(
        self,
        monkeypatch: pytest.MonkeyPatch,
        stub_repos: dict,
    ) -> None:
        recall_query = RecallQuery(mode=RecallMode.USER)
        monkeypatch.setattr(
            "app.services.message_service.classify_user_turn",
            _make_classify(IntentType.RECALL_CHECK, recall_query=recall_query),
        )

        captured_calls: list[Any] = []

        async def fake_run(*, calls, queue, **_):
            captured_calls.extend(calls)
            assert len(calls) == 1
            assert calls[0]["name"] == "check_user_medications_recall"
            # profile_id top-level 주입 검증 (worker dispatch 가 require)
            assert calls[0]["profile_id"] == str(stub_repos["profile_id"])
            tool_id = calls[0]["tool_call_id"]
            return {tool_id: {"matched": True, "recalls": [{"item_seq": "X1"}]}}

        async def fake_generate(*, messages, queue, system_prompt=None):
            tool_msgs = [m for m in messages if m.get("role") == "tool"]
            assert len(tool_msgs) == 1
            assert "X1" in tool_msgs[0]["content"]
            return {"answer": "회수된 약 1건이 있습니다.", "token_usage": None}

        monkeypatch.setattr("app.services.message_service.run_tool_calls_via_rq", fake_run)
        monkeypatch.setattr("app.services.message_service.generate_chat_response_via_rq", fake_generate)

        store = InMemoryPendingTurnStore()
        service = MessageService(pending_store=store, queue=object())
        result = await service.ask_with_tools(
            session_id=stub_repos["session_id"],
            account_id=stub_repos["account_id"],
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
        stub_repos: dict,
    ) -> None:
        recall_query = RecallQuery(mode=RecallMode.MANUFACTURER, manufacturer="동국제약")
        monkeypatch.setattr(
            "app.services.message_service.classify_user_turn",
            _make_classify(IntentType.RECALL_CHECK, recall_query=recall_query),
        )

        captured_calls: list[Any] = []

        async def fake_run(*, calls, queue, **_):
            captured_calls.extend(calls)
            assert calls[0]["name"] == "check_manufacturer_recalls"
            assert calls[0]["arguments"]["manufacturer"] == "동국제약"
            assert calls[0]["profile_id"] == str(stub_repos["profile_id"])
            tool_id = calls[0]["tool_call_id"]
            return {tool_id: {"matched": False, "recalls": []}}

        async def fake_generate(*, messages, queue, system_prompt=None):
            return {"answer": "동국제약 회수 이력 없습니다.", "token_usage": None}

        monkeypatch.setattr("app.services.message_service.run_tool_calls_via_rq", fake_run)
        monkeypatch.setattr("app.services.message_service.generate_chat_response_via_rq", fake_generate)

        store = InMemoryPendingTurnStore()
        service = MessageService(pending_store=store, queue=object())
        result = await service.ask_with_tools(
            session_id=stub_repos["session_id"],
            account_id=stub_repos["account_id"],
            content="동국제약 회수 이력 알려줘",
        )

        assert result.pending is None
        assert result.assistant_message is not None
        assert "동국제약" in result.assistant_message.content
        assert len(captured_calls) == 1

    @pytest.mark.asyncio
    async def test_manufacturer_mode_without_name(
        self,
        monkeypatch: pytest.MonkeyPatch,
        stub_repos: dict,
    ) -> None:
        """제조사 명시 없으면 worker 가 사용자 복용약 제조사 셋 자동 추출 — manufacturer 키 미포함."""
        recall_query = RecallQuery(mode=RecallMode.MANUFACTURER, manufacturer=None)
        monkeypatch.setattr(
            "app.services.message_service.classify_user_turn",
            _make_classify(IntentType.RECALL_CHECK, recall_query=recall_query),
        )

        async def fake_run(*, calls, queue, **_):
            assert calls[0]["name"] == "check_manufacturer_recalls"
            # manufacturer 키가 아예 없거나 None
            assert calls[0]["arguments"].get("manufacturer") in (None, "")
            tool_id = calls[0]["tool_call_id"]
            return {tool_id: {"matched": False, "recalls": []}}

        async def fake_generate(*, messages, queue, system_prompt=None):
            return {"answer": "복용약 제조사 회수 이력 없음.", "token_usage": None}

        monkeypatch.setattr("app.services.message_service.run_tool_calls_via_rq", fake_run)
        monkeypatch.setattr("app.services.message_service.generate_chat_response_via_rq", fake_generate)

        store = InMemoryPendingTurnStore()
        service = MessageService(pending_store=store, queue=object())
        result = await service.ask_with_tools(
            session_id=stub_repos["session_id"],
            account_id=stub_repos["account_id"],
            content="제약회사 회수당한 거 있어?",
        )

        assert result.pending is None
        assert result.assistant_message is not None


# ── C. recall_check 인데 recall_query=None (LLM 위반) → fallback ──


class TestRecallCheckMissingQuery:
    @pytest.mark.asyncio
    async def test_missing_recall_query_falls_back_to_direct_answer(
        self,
        monkeypatch: pytest.MonkeyPatch,
        stub_repos: dict,
    ) -> None:
        monkeypatch.setattr(
            "app.services.message_service.classify_user_turn",
            _make_classify(IntentType.RECALL_CHECK, recall_query=None),
        )
        monkeypatch.setattr(
            "app.services.message_service.run_tool_calls_via_rq",
            AsyncMock(side_effect=AssertionError("호출 금지")),
        )
        monkeypatch.setattr(
            "app.services.message_service.generate_chat_response_via_rq",
            AsyncMock(side_effect=AssertionError("호출 금지")),
        )

        store = InMemoryPendingTurnStore()
        service = MessageService(pending_store=store, queue=object())
        result = await service.ask_with_tools(
            session_id=stub_repos["session_id"],
            account_id=stub_repos["account_id"],
            content="회수된 거",
        )

        assert result.pending is None
        assert result.assistant_message is not None
        assert "회수" in result.assistant_message.content or "회수" in result.assistant_message.content

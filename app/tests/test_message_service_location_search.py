"""MessageService.ask_with_tools 의 location_search 분기 테스트 (Step 2 Red).

위치 검색 회귀 핫픽스 — Query Rewriter 가 ``intent=LOCATION_SEARCH`` 를
반환했을 때 다음 두 분기가 정상 동작하는지 검증.

- ``mode=keyword``  : ``run_tool_calls_via_rq`` 즉시 호출 + 2nd LLM 응답.
- ``mode=gps``      : ``PendingTurnStore.create`` 로 좌표 콜백 대기.
"""

from typing import Any
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.dtos.query_rewriter import (
    IntentType,
    LocationCategory,
    LocationMode,
    LocationQuery,
    QueryRewriterOutput,
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
    """Repository / classify_user_turn / RQ adapter 전부 stub."""
    captured: dict[str, Any] = {"assistant": [], "user": [], "tool_calls": [], "generate_calls": []}
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


# ── A. mode=keyword (즉시 카카오 호출) ──────────────────────────


class TestLocationSearchKeyword:
    @pytest.mark.asyncio
    async def test_keyword_runs_tool_then_generates_answer(
        self,
        monkeypatch: pytest.MonkeyPatch,
        stub_repos: dict,
    ) -> None:
        location_query = LocationQuery(mode=LocationMode.KEYWORD, query="강남역 약국")
        monkeypatch.setattr(
            "app.services.message_service.classify_user_turn",
            _make_classify(IntentType.LOCATION_SEARCH, location_query=location_query),
        )

        captured_calls: list[Any] = []

        async def fake_run(*, calls, queue, **_):
            captured_calls.extend(calls)
            assert len(calls) == 1
            assert calls[0]["name"] == "search_hospitals_by_keyword"
            assert calls[0]["arguments"] == {"query": "강남역 약국"}
            assert "geolocation" not in calls[0]
            tool_id = calls[0]["tool_call_id"]
            return {tool_id: {"places": [{"place_name": "강남스퀘어약국"}]}}

        async def fake_generate(*, messages, queue, system_prompt=None):
            tool_msgs = [m for m in messages if m.get("role") == "tool"]
            assert len(tool_msgs) == 1
            assert "강남스퀘어약국" in tool_msgs[0]["content"]
            return {"answer": "강남역 근처 약국입니다.", "token_usage": None}

        monkeypatch.setattr("app.services.message_service.run_tool_calls_via_rq", fake_run)
        monkeypatch.setattr("app.services.message_service.generate_chat_response_via_rq", fake_generate)

        store = InMemoryPendingTurnStore()
        service = MessageService(pending_store=store, queue=object())
        result = await service.ask_with_tools(
            session_id=stub_repos["session_id"],
            account_id=stub_repos["account_id"],
            content="강남역 약국 찾아줘",
        )

        assert result.pending is None
        assert result.assistant_message is not None
        assert result.assistant_message.content == "강남역 근처 약국입니다."
        assert len(captured_calls) == 1


# ── B. mode=gps (PendingTurn 으로 좌표 콜백 대기) ───────────────


class TestLocationSearchGps:
    @pytest.mark.asyncio
    async def test_gps_creates_pending_turn_and_returns_handoff(
        self,
        monkeypatch: pytest.MonkeyPatch,
        stub_repos: dict,
    ) -> None:
        location_query = LocationQuery(
            mode=LocationMode.GPS,
            category=LocationCategory.PHARMACY,
            radius_m=1000,
        )
        monkeypatch.setattr(
            "app.services.message_service.classify_user_turn",
            _make_classify(IntentType.LOCATION_SEARCH, location_query=location_query),
        )

        # 즉시 실행/2nd LLM 절대 호출 안 됨
        monkeypatch.setattr(
            "app.services.message_service.run_tool_calls_via_rq",
            AsyncMock(side_effect=AssertionError("gps 분기에서 즉시 실행 금지")),
        )
        monkeypatch.setattr(
            "app.services.message_service.generate_chat_response_via_rq",
            AsyncMock(side_effect=AssertionError("gps 분기에서 2nd LLM 즉시 호출 금지")),
        )

        store = InMemoryPendingTurnStore()
        service = MessageService(pending_store=store, queue=object())
        result = await service.ask_with_tools(
            session_id=stub_repos["session_id"],
            account_id=stub_repos["account_id"],
            content="내 주변 약국 찾아줘",
        )

        assert result.pending is not None
        assert result.assistant_message is None
        assert result.user_message is not None

        pending = await store.claim(result.pending.turn_id)
        assert pending is not None
        assert pending.account_id == str(stub_repos["account_id"])
        assert len(pending.tool_calls) == 1
        tc = pending.tool_calls[0]
        assert tc.name == "search_hospitals_by_location"
        assert tc.needs_geolocation is True
        assert tc.arguments == {"category": "약국", "radius_m": 1000}


# ── C. location_search 인데 location_query=None (LLM 위반) → fallback ──


class TestLocationSearchMissingQuery:
    @pytest.mark.asyncio
    async def test_missing_location_query_falls_back_to_direct_answer(
        self,
        monkeypatch: pytest.MonkeyPatch,
        stub_repos: dict,
    ) -> None:
        monkeypatch.setattr(
            "app.services.message_service.classify_user_turn",
            _make_classify(IntentType.LOCATION_SEARCH, location_query=None),
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
            content="약국 찾아줘",
        )

        assert result.pending is None
        assert result.assistant_message is not None
        # fallback 메시지 — 정확한 문구 매칭은 피하고 키워드만 검증
        assert "약국" in result.assistant_message.content or "병원" in result.assistant_message.content

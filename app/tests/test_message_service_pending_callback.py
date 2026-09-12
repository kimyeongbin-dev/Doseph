"""MessageService.resolve_pending_turn 콜백 경로 테스트 (Y-6 Red).

시나리오 A (allow), B (denied), 만료(410), account 불일치(403).
"""

from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock
from uuid import uuid4

from fastapi import HTTPException
import pytest

from app.dtos.tools import PendingTurn, ToolCall
from app.services.message_service import MessageService
from app.services.tools.pending import InMemoryPendingTurnStore


class _StubChatMessage:
    def __init__(self, *, message_id: str, content: str, sender_type: str) -> None:
        self.id = message_id
        self.content = content
        self.sender_type = sender_type
        self.metadata: dict[str, Any] = {}


@pytest.fixture
def stub_repo(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    captured: dict[str, Any] = {"assistant": []}

    async def fake_assistant(_self, sid, content, metadata=None) -> _StubChatMessage:
        msg = _StubChatMessage(message_id=str(uuid4()), content=content, sender_type="ASSISTANT")
        msg.metadata = metadata or {}
        captured["assistant"].append((sid, content, metadata))
        return msg

    # 옵션 D — resolve_pending_turn 의 count_by_session 호출 stub
    async def fake_count(_self, _sid) -> int:
        return 0

    from app.repositories.message_repository import MessageRepository

    monkeypatch.setattr(MessageRepository, "create_assistant_message", fake_assistant)
    monkeypatch.setattr(MessageRepository, "count_by_session", fake_count)
    return captured


def _make_pending(account_id: str, *, session_id: str | None = None) -> PendingTurn:
    return PendingTurn(
        turn_id="",
        session_id=session_id or str(uuid4()),
        account_id=account_id,
        messages_snapshot=[
            {"role": "user", "content": "내 주변 약국이랑 강남역 약국"},
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": "c1",
                        "type": "function",
                        "function": {"name": "search_hospitals_by_keyword", "arguments": '{"query": "강남역 약국"}'},
                    },
                    {
                        "id": "c2",
                        "type": "function",
                        "function": {"name": "search_hospitals_by_location", "arguments": '{"category": "약국"}'},
                    },
                ],
            },
        ],
        tool_calls=[
            ToolCall(
                tool_call_id="c1",
                name="search_hospitals_by_keyword",
                arguments={"query": "강남역 약국"},
                needs_geolocation=False,
            ),
            ToolCall(
                tool_call_id="c2",
                name="search_hospitals_by_location",
                arguments={"category": "약국"},
                needs_geolocation=True,
            ),
        ],
        eager_results={"c1": {"places": [{"place_name": "강남스퀘어약국"}]}},
        created_at=datetime(2026, 4, 24, 12, 0, 0, tzinfo=UTC),
    )


# ── A. allow (status=ok) ───────────────────────────────────────


class TestCallbackOk:
    @pytest.mark.asyncio
    async def test_allow_runs_location_then_calls_llm(
        self,
        monkeypatch: pytest.MonkeyPatch,
        stub_repo: dict,
    ) -> None:
        account_id = str(uuid4())
        store = InMemoryPendingTurnStore()
        turn_id = await store.create(_make_pending(account_id))

        location_calls: list = []

        async def fake_run_tool_calls(*, calls, queue, **_) -> dict:
            # location 만 남아야 함 (keyword 는 eager_results 에서 재활용)
            location_calls.extend(calls)
            assert len(calls) == 1
            assert calls[0]["name"] == "search_hospitals_by_location"
            assert calls[0]["geolocation"] == {"lat": 37.5, "lng": 127.0}
            return {"c2": {"places": [{"place_name": "미진약국"}]}}

        async def fake_generate(*, messages, system_prompt=None, queue) -> dict:
            # messages 에 두 tool role 결과(c1, c2) 가 모두 포함되어 있어야 함
            tool_ids = [m.get("tool_call_id") for m in messages if m.get("role") == "tool"]
            assert set(tool_ids) == {"c1", "c2"}
            return {"answer": "강남스퀘어약국과 미진약국", "token_usage": None}

        monkeypatch.setattr("app.services.message_service.run_tool_calls_via_rq", fake_run_tool_calls)
        monkeypatch.setattr("app.services.message_service.generate_chat_response_via_rq", fake_generate)

        service = MessageService(pending_store=store)
        result = await service.resolve_pending_turn(
            turn_id=turn_id,
            account_id=account_id,
            status="ok",
            lat=37.5,
            lng=127.0,
        )

        assert result.pending is None
        assert result.assistant_message is not None
        assert result.assistant_message.content == "강남스퀘어약국과 미진약국"


# ── B. denied ──────────────────────────────────────────────────


class TestCallbackDenied:
    @pytest.mark.asyncio
    async def test_denied_skips_location_and_goes_straight_to_llm(
        self,
        monkeypatch: pytest.MonkeyPatch,
        stub_repo: dict,
    ) -> None:
        account_id = str(uuid4())
        store = InMemoryPendingTurnStore()
        turn_id = await store.create(_make_pending(account_id))

        async def should_not_run_tool(**_: Any) -> dict:
            raise AssertionError("denied 시 location 호출이 일어나면 안 됨")

        async def fake_generate(*, messages, system_prompt=None, queue) -> dict:
            # location tool 결과가 error payload 로 전달되어야 함
            c2_msg = next((m for m in messages if m.get("tool_call_id") == "c2"), None)
            assert c2_msg is not None
            assert "denied" in c2_msg["content"].lower() or "permission" in c2_msg["content"].lower()
            return {"answer": "위치 없이도 가능한 옵션 안내드릴게요.", "token_usage": None}

        monkeypatch.setattr("app.services.message_service.run_tool_calls_via_rq", should_not_run_tool)
        monkeypatch.setattr("app.services.message_service.generate_chat_response_via_rq", fake_generate)

        service = MessageService(pending_store=store)
        result = await service.resolve_pending_turn(
            turn_id=turn_id,
            account_id=account_id,
            status="denied",
            lat=None,
            lng=None,
        )

        assert result.assistant_message is not None
        assert result.pending is None


# ── 만료 / 권한 ─────────────────────────────────────────────────


class TestCallbackErrors:
    @pytest.mark.asyncio
    async def test_unknown_turn_id_raises_410(self, monkeypatch: pytest.MonkeyPatch) -> None:
        store = InMemoryPendingTurnStore()
        service = MessageService(pending_store=store)
        monkeypatch.setattr(
            "app.services.message_service.generate_chat_response_via_rq",
            AsyncMock(side_effect=AssertionError("호출되면 안 됨")),
        )

        with pytest.raises(HTTPException) as exc:
            await service.resolve_pending_turn(
                turn_id="00000000-dead-beef-0000-000000000000",
                account_id=str(uuid4()),
                status="ok",
                lat=37.5,
                lng=127.0,
            )
        assert exc.value.status_code == 410

    @pytest.mark.asyncio
    async def test_account_mismatch_raises_403(self, monkeypatch: pytest.MonkeyPatch) -> None:
        other = str(uuid4())
        real = str(uuid4())
        store = InMemoryPendingTurnStore()
        turn_id = await store.create(_make_pending(real))

        service = MessageService(pending_store=store)
        monkeypatch.setattr(
            "app.services.message_service.generate_chat_response_via_rq",
            AsyncMock(side_effect=AssertionError("호출되면 안 됨")),
        )

        with pytest.raises(HTTPException) as exc:
            await service.resolve_pending_turn(
                turn_id=turn_id,
                account_id=other,
                status="ok",
                lat=37.5,
                lng=127.0,
            )
        assert exc.value.status_code == 403

    @pytest.mark.asyncio
    async def test_ok_without_coords_raises_400(self, monkeypatch: pytest.MonkeyPatch) -> None:
        account_id = str(uuid4())
        store = InMemoryPendingTurnStore()
        turn_id = await store.create(_make_pending(account_id))

        service = MessageService(pending_store=store)
        monkeypatch.setattr(
            "app.services.message_service.generate_chat_response_via_rq",
            AsyncMock(side_effect=AssertionError("호출되면 안 됨")),
        )

        with pytest.raises(HTTPException) as exc:
            await service.resolve_pending_turn(
                turn_id=turn_id,
                account_id=account_id,
                status="ok",
                lat=None,
                lng=None,
            )
        assert exc.value.status_code == 400

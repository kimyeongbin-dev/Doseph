"""MessageService.ask_with_tools 의 location_search 분기 테스트.

위치 검색 회귀 핫픽스 — Query Rewriter 가 ``intent=LOCATION_SEARCH`` 를
반환했을 때 다음 두 분기가 정상 동작하는지 검증.

- ``mode=keyword``  : ``run_tool_calls_via_rq`` 즉시 호출 + 2nd LLM 응답.
- ``mode=gps``      : ``PendingTurnStore.create`` 로 좌표 콜백 대기.
"""

from typing import Any
from unittest.mock import AsyncMock

import pytest

from app.dtos.query_rewriter import IntentType, LocationCategory, LocationMode, LocationQuery
from app.services.message_service import MessageService
from app.services.tools.pending import InMemoryPendingTurnStore
from app.tests.chat_service_stubs import ChatStubs, make_classify

# ── A. mode=keyword (즉시 카카오 호출) ──────────────────────────


class TestLocationSearchKeyword:
  @pytest.mark.asyncio
  async def test_keyword_runs_tool_then_generates_answer(
    self,
    monkeypatch: pytest.MonkeyPatch,
    chat_stubs: ChatStubs,
  ) -> None:
    monkeypatch.setattr(
      "app.services.message_service.classify_user_turn",
      make_classify(
        IntentType.LOCATION_SEARCH,
        location_query=LocationQuery(mode=LocationMode.KEYWORD, query="강남역 약국"),
      ),
    )

    captured_calls: list[dict[str, Any]] = []

    async def fake_run(*, calls: list[dict[str, Any]], queue: object, **_: object) -> dict[str, Any]:
      captured_calls.extend(calls)
      assert len(calls) == 1
      assert calls[0]["name"] == "search_hospitals_by_keyword"
      assert calls[0]["arguments"] == {"query": "강남역 약국"}
      assert "geolocation" not in calls[0]
      return {calls[0]["tool_call_id"]: {"places": [{"place_name": "강남스퀘어약국"}]}}

    async def fake_generate(
      *, messages: list[dict[str, Any]], queue: object, system_prompt: str | None = None
    ) -> dict[str, Any]:
      tool_msgs = [m for m in messages if m.get("role") == "tool"]
      assert len(tool_msgs) == 1
      assert "강남스퀘어약국" in tool_msgs[0]["content"]
      return {"answer": "강남역 근처 약국입니다.", "token_usage": None}

    monkeypatch.setattr("app.services.message_service.run_tool_calls_via_rq", fake_run)
    monkeypatch.setattr("app.services.message_service.generate_chat_response_via_rq", fake_generate)

    service = MessageService(pending_store=InMemoryPendingTurnStore(), queue=object())
    result = await service.ask_with_tools(
      session_id=chat_stubs.session_id,
      account_id=chat_stubs.account_id,
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
    chat_stubs: ChatStubs,
  ) -> None:
    monkeypatch.setattr(
      "app.services.message_service.classify_user_turn",
      make_classify(
        IntentType.LOCATION_SEARCH,
        location_query=LocationQuery(mode=LocationMode.GPS, category=LocationCategory.PHARMACY, radius_m=1000),
      ),
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
      session_id=chat_stubs.session_id,
      account_id=chat_stubs.account_id,
      content="내 주변 약국 찾아줘",
    )

    assert result.pending is not None
    assert result.assistant_message is None
    assert result.user_message is not None

    pending = await store.claim(result.pending.turn_id)
    assert pending is not None
    assert pending.account_id == str(chat_stubs.account_id)
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
    chat_stubs: ChatStubs,
  ) -> None:
    monkeypatch.setattr(
      "app.services.message_service.classify_user_turn",
      make_classify(IntentType.LOCATION_SEARCH, location_query=None),
    )
    monkeypatch.setattr(
      "app.services.message_service.run_tool_calls_via_rq",
      AsyncMock(side_effect=AssertionError("호출 금지")),
    )
    monkeypatch.setattr(
      "app.services.message_service.generate_chat_response_via_rq",
      AsyncMock(side_effect=AssertionError("호출 금지")),
    )

    service = MessageService(pending_store=InMemoryPendingTurnStore(), queue=object())
    result = await service.ask_with_tools(
      session_id=chat_stubs.session_id,
      account_id=chat_stubs.account_id,
      content="약국 찾아줘",
    )

    assert result.pending is None
    assert result.assistant_message is not None
    # fallback 메시지 — 정확한 문구 매칭은 피하고 키워드만 검증
    assert "약국" in result.assistant_message.content or "병원" in result.assistant_message.content

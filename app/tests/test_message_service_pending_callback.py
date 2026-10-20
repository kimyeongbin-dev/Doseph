"""위치 권한 콜백 — 대기 턴을 마무리하는 경로.

- 서비스 ``MessageService.resolve_pending_turn``: 허용(ok) · 거부(denied) · 만료(410) · 남의 턴(403)
- 요청 경계 ``ToolResultRequest`` / ``POST /messages/tool-result``:
  ``status="ok"`` 인데 좌표가 없거나 유한한 숫자가 아니면 **422** — 값의 조합이 규칙을 어긴 요청이다.
  검증은 경계(Pydantic)가 하고, 서비스는 HTTP 를 모른다(저장소 규칙 §5-2).
"""

from collections.abc import AsyncGenerator
from datetime import UTC, datetime
import math
from typing import Any
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

from fastapi import HTTPException
from httpx import ASGITransport, AsyncClient
from pydantic import ValidationError
import pytest
import pytest_asyncio

from app.apis.v1.message_routers import get_message_service
from app.dependencies.security import get_current_account
from app.dtos.message import ToolResultRequest
from app.dtos.tools import PendingTurn, ToolCall
from app.main import app
from app.repositories.message_repository import MessageRepository
from app.services.message_service import MessageService
from app.services.tools.pending import InMemoryPendingTurnStore
from app.tests.chat_service_stubs import StubChatMessage


@pytest.fixture
def stub_repo(monkeypatch: pytest.MonkeyPatch) -> list[str]:
  """어시스턴트 메시지 저장·메시지 수만 가짜로 — 저장된 답변 문장을 돌려준다."""
  saved: list[str] = []

  async def fake_assistant(
    _self: MessageRepository, _sid: UUID, content: str, metadata: dict[str, Any] | None = None
  ) -> StubChatMessage:
    saved.append(content)
    return StubChatMessage(content=content, sender_type="ASSISTANT", metadata=metadata)

  # resolve_pending_turn 이 요약 판단에 메시지 수를 읽는다
  async def fake_count(_self: MessageRepository, _sid: UUID) -> int:
    return 0

  monkeypatch.setattr(MessageRepository, "create_assistant_message", fake_assistant)
  monkeypatch.setattr(MessageRepository, "count_by_session", fake_count)
  return saved


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
    stub_repo: list[str],
  ) -> None:
    account_id = str(uuid4())
    store = InMemoryPendingTurnStore()
    turn_id = await store.create(_make_pending(account_id))

    async def fake_run_tool_calls(*, calls: list[dict[str, Any]], queue: object, **_: object) -> dict[str, Any]:
      # location 만 남아야 함 (keyword 는 eager_results 에서 재활용)
      assert len(calls) == 1
      assert calls[0]["name"] == "search_hospitals_by_location"
      assert calls[0]["geolocation"] == {"lat": 37.5, "lng": 127.0}
      return {"c2": {"places": [{"place_name": "미진약국"}]}}

    async def fake_generate(
      *, messages: list[dict[str, Any]], queue: object, system_prompt: str | None = None
    ) -> dict[str, Any]:
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
    assert stub_repo == ["강남스퀘어약국과 미진약국"]


# ── B. denied ──────────────────────────────────────────────────


class TestCallbackDenied:
  @pytest.mark.asyncio
  async def test_denied_skips_location_and_goes_straight_to_llm(
    self,
    monkeypatch: pytest.MonkeyPatch,
    stub_repo: list[str],
  ) -> None:
    account_id = str(uuid4())
    store = InMemoryPendingTurnStore()
    turn_id = await store.create(_make_pending(account_id))

    async def should_not_run_tool(**_: object) -> dict[str, Any]:
      raise AssertionError("denied 시 location 호출이 일어나면 안 됨")

    async def fake_generate(
      *, messages: list[dict[str, Any]], queue: object, system_prompt: str | None = None
    ) -> dict[str, Any]:
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

    assert result.pending is None
    assert result.assistant_message is not None
    # 이 단언이 없으면 2nd LLM 이 안 불려도(위 단언이 안 돌아도) 통과한다
    assert result.assistant_message.content == "위치 없이도 가능한 옵션 안내드릴게요."


# ── 만료 / 권한 / 잘못된 좌표 ────────────────────────────────────


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
  async def test_ok_without_coords_is_rejected_before_claim(self, monkeypatch: pytest.MonkeyPatch) -> None:
    """경계를 건너뛴 호출 방어선 — HTTP 가 아니라 ValueError 이고, 대기 턴을 소비하지 않는다."""
    account_id = str(uuid4())
    store = InMemoryPendingTurnStore()
    turn_id = await store.create(_make_pending(account_id))

    service = MessageService(pending_store=store)
    monkeypatch.setattr(
      "app.services.message_service.generate_chat_response_via_rq",
      AsyncMock(side_effect=AssertionError("호출되면 안 됨")),
    )

    with pytest.raises(ValueError, match="lat and lng"):
      await service.resolve_pending_turn(
        turn_id=turn_id,
        account_id=account_id,
        status="ok",
        lat=None,
        lng=None,
      )
    assert await store.claim(turn_id) is not None, "거절된 요청이 대기 턴을 소비했다"


# ── 요청 경계 — 좌표 규칙은 DTO 가 잡는다 ────────────────────────


class TestToolResultRequest:
  @pytest.mark.parametrize(
    ("lat", "lng"),
    [(None, None), (37.5, None), (None, 127.0), (math.nan, 127.0), (37.5, math.inf)],
  )
  def test_ok_requires_finite_coords(self, lat: float | None, lng: float | None) -> None:
    with pytest.raises(ValidationError):
      ToolResultRequest(turn_id="t", status="ok", lat=lat, lng=lng)

  def test_ok_with_coords_is_accepted(self) -> None:
    request = ToolResultRequest(turn_id="t", status="ok", lat=37.5, lng=127.0)
    assert (request.lat, request.lng) == (37.5, 127.0)

  def test_denied_without_coords_is_accepted(self) -> None:
    assert ToolResultRequest(turn_id="t", status="denied").lat is None


@pytest_asyncio.fixture
async def tool_result_client() -> AsyncGenerator[tuple[AsyncClient, MagicMock]]:
  """인증과 서비스를 가짜로 바꾼 클라이언트 — 경계 검증만 본다."""
  fake_service = MagicMock()
  fake_service.resolve_pending_turn = AsyncMock()
  app.dependency_overrides[get_current_account] = lambda: MagicMock(id=uuid4())
  app.dependency_overrides[get_message_service] = lambda: fake_service
  try:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
      yield ac, fake_service
  finally:
    for dep in (get_current_account, get_message_service):
      app.dependency_overrides.pop(dep, None)


class TestToolResultRoute:
  @pytest.mark.asyncio
  async def test_ok_without_coords_is_unprocessable(self, tool_result_client: tuple[AsyncClient, MagicMock]) -> None:
    client, fake_service = tool_result_client

    response = await client.post("/api/v1/messages/tool-result", json={"turn_id": "t", "status": "ok"})

    assert response.status_code == 422
    fake_service.resolve_pending_turn.assert_not_awaited()

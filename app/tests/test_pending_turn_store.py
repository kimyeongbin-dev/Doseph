"""PendingTurn 저장소 계약 테스트 (Y-3 Red).

병렬 tool_calls 를 한 턴 단위로 묶어 Redis 에 임시 보관하고, 사용자
콜백(POST /messages/tool-result) 도착 시 1회성으로 GETDEL 회수한다.

본 테스트는 Protocol 과 두 구현 (Redis 실제, In-Memory 테스트용) 양쪽이
동일한 동작 계약을 따르는지를 검증한다. Redis 컨테이너 의존성을 피하기
위해 실제 동작은 In-Memory 구현으로 검증하고, Redis 구현은 ``redis.asyncio``
호출 인자만 mock 으로 락한다.

Red 전제:
- ``PendingTurn`` Pydantic 모델이 ``app.dtos.tools`` 에 있다.
- ``PendingTurnStore`` Protocol 이 ``create``/``claim``/``exists`` 를 정의.
- ``InMemoryPendingTurnStore`` 가 시간 주입(monkeypatchable now) 가능.
- ``RedisPendingTurnStore`` 가 ``redis.asyncio.Redis`` 를 받아 SETEX/GETDEL 호출.
"""

from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock

import pytest

from app.dtos.tools import PendingTurn, ToolCall
from app.services.tools.pending import (
  DEFAULT_TTL_SEC,
  InMemoryPendingTurnStore,
  PendingTurnStore,
  RedisPendingTurnStore,
)

# ── 헬퍼 ───────────────────────────────────────────────────────


def _make_turn(
  *,
  session_id: str = "11111111-1111-1111-1111-111111111111",
  account_id: str = "22222222-2222-2222-2222-222222222222",
) -> PendingTurn:
  """단일 location 툴 + keyword 툴 1개 mix 시나리오의 표본."""
  return PendingTurn(
    turn_id="",  # store 가 채움
    session_id=session_id,
    account_id=account_id,
    messages_snapshot=[
      {"role": "user", "content": "내 주변 약국이랑 강남역 약국 알려줘"},
      {
        "role": "assistant",
        "content": None,
        "tool_calls": [
          {"id": "call_1", "function": {"name": "search_hospitals_by_location"}},
          {"id": "call_2", "function": {"name": "search_hospitals_by_keyword"}},
        ],
      },
    ],
    tool_calls=[
      ToolCall(
        tool_call_id="call_1",
        name="search_hospitals_by_location",
        arguments={"category": "약국", "radius_m": 1000},
        needs_geolocation=True,
      ),
      ToolCall(
        tool_call_id="call_2",
        name="search_hospitals_by_keyword",
        arguments={"query": "강남역 약국"},
        needs_geolocation=False,
      ),
    ],
    eager_results={"call_2": [{"id": "1", "place_name": "강남스퀘어약국"}]},
    created_at=datetime(2026, 4, 24, 12, 0, 0, tzinfo=UTC),
  )


# ── Protocol 준수 ──────────────────────────────────────────────


class TestProtocolCompliance:
  def test_in_memory_is_pending_turn_store(self) -> None:
    store = InMemoryPendingTurnStore()
    assert isinstance(store, PendingTurnStore)

  def test_redis_is_pending_turn_store(self) -> None:
    fake_redis = AsyncMock()
    store = RedisPendingTurnStore(redis=fake_redis)
    assert isinstance(store, PendingTurnStore)

  def test_default_ttl_is_60(self) -> None:
    assert DEFAULT_TTL_SEC == 60


# ── In-Memory 동작 계약 ─────────────────────────────────────────


class TestInMemoryStoreLifecycle:
  @pytest.mark.asyncio
  async def test_create_returns_turn_id_and_persists(self) -> None:
    store = InMemoryPendingTurnStore()
    turn = _make_turn()

    turn_id = await store.create(turn)

    assert turn_id
    assert isinstance(turn_id, str)
    assert await store.exists(turn_id)

  @pytest.mark.asyncio
  async def test_create_assigns_unique_turn_id_per_call(self) -> None:
    store = InMemoryPendingTurnStore()

    id1 = await store.create(_make_turn())
    id2 = await store.create(_make_turn())

    assert id1 != id2

  @pytest.mark.asyncio
  async def test_claim_returns_stored_turn_with_id_filled(self) -> None:
    store = InMemoryPendingTurnStore()
    original = _make_turn()

    turn_id = await store.create(original)
    claimed = await store.claim(turn_id)

    assert claimed is not None
    assert claimed.turn_id == turn_id
    assert claimed.session_id == original.session_id
    assert claimed.account_id == original.account_id
    assert len(claimed.tool_calls) == 2
    assert claimed.tool_calls[0].needs_geolocation is True
    assert claimed.eager_results == original.eager_results

  @pytest.mark.asyncio
  async def test_claim_is_one_shot(self) -> None:
    store = InMemoryPendingTurnStore()
    turn_id = await store.create(_make_turn())

    first = await store.claim(turn_id)
    second = await store.claim(turn_id)

    assert first is not None
    assert second is None

  @pytest.mark.asyncio
  async def test_claim_unknown_turn_id_returns_none(self) -> None:
    store = InMemoryPendingTurnStore()
    assert await store.claim("00000000-0000-0000-0000-000000000000") is None

  @pytest.mark.asyncio
  async def test_exists_after_claim_is_false(self) -> None:
    store = InMemoryPendingTurnStore()
    turn_id = await store.create(_make_turn())

    await store.claim(turn_id)

    assert not await store.exists(turn_id)


class TestInMemoryStoreTTL:
  @pytest.mark.asyncio
  async def test_expired_turn_returns_none_on_claim(self) -> None:
    """Frozen-time 흐름으로 TTL 만료 시뮬레이션."""
    current = {"now": 0.0}

    def fake_clock() -> float:
      return current["now"]

    store = InMemoryPendingTurnStore(clock=fake_clock, ttl_sec=10)
    turn_id = await store.create(_make_turn())

    current["now"] = 11.0  # TTL 10s 초과
    assert not await store.exists(turn_id)
    assert await store.claim(turn_id) is None

  @pytest.mark.asyncio
  async def test_within_ttl_still_alive(self) -> None:
    current = {"now": 0.0}

    store = InMemoryPendingTurnStore(clock=lambda: current["now"], ttl_sec=10)
    turn_id = await store.create(_make_turn())

    current["now"] = 9.0
    assert await store.exists(turn_id)


class TestInMemoryStoreIsolation:
  @pytest.mark.asyncio
  async def test_two_turns_independent(self) -> None:
    store = InMemoryPendingTurnStore()
    id_a = await store.create(_make_turn(session_id="aaaaaaaa-1111-1111-1111-111111111111"))
    id_b = await store.create(_make_turn(session_id="bbbbbbbb-2222-2222-2222-222222222222"))

    a = await store.claim(id_a)
    b = await store.claim(id_b)

    assert a is not None
    assert b is not None
    assert a.session_id != b.session_id


# ── PendingTurn DTO 직렬화 round-trip ──────────────────────────


class TestPendingTurnSerialization:
  def test_round_trip_preserves_all_fields(self) -> None:
    original = _make_turn()
    original_with_id = original.model_copy(update={"turn_id": "abcd-1234"})

    json_str = original_with_id.model_dump_json()
    restored = PendingTurn.model_validate_json(json_str)

    assert restored == original_with_id

  def test_tool_call_fields(self) -> None:
    call = ToolCall(
      tool_call_id="x",
      name="search_hospitals_by_keyword",
      arguments={"query": "강남역 약국"},
      needs_geolocation=False,
    )
    assert call.tool_call_id == "x"
    assert call.needs_geolocation is False


# ── Redis impl: 호출 인자만 락 ────────────────────────────────


class TestRedisStoreCallContract:
  @pytest.mark.asyncio
  async def test_create_uses_setex_with_pending_turn_prefix_and_ttl(self) -> None:
    fake_redis = AsyncMock()
    store = RedisPendingTurnStore(redis=fake_redis, ttl_sec=DEFAULT_TTL_SEC)

    turn_id = await store.create(_make_turn())

    fake_redis.setex.assert_awaited_once()
    call_args = fake_redis.setex.await_args
    key: str = call_args.args[0] if call_args.args else call_args.kwargs["name"]
    ttl: int = call_args.args[1] if len(call_args.args) > 1 else call_args.kwargs["time"]
    value: Any = call_args.args[2] if len(call_args.args) > 2 else call_args.kwargs["value"]

    assert key == f"pending:turn:{turn_id}"
    assert ttl == DEFAULT_TTL_SEC
    # JSON 인코딩으로 저장
    assert isinstance(value, (str, bytes))
    text = value.decode("utf-8") if isinstance(value, bytes) else value
    assert "session_id" in text

  @pytest.mark.asyncio
  async def test_claim_uses_getdel_atomic(self) -> None:
    original = _make_turn()
    # turn_id 가 채워진 상태로 직렬화된 값을 흉내
    turn_id = "fake-turn-1"
    with_id = original.model_copy(update={"turn_id": turn_id})
    stored_value = with_id.model_dump_json().encode("utf-8")

    fake_redis = AsyncMock()
    fake_redis.getdel = AsyncMock(return_value=stored_value)

    store = RedisPendingTurnStore(redis=fake_redis)
    claimed = await store.claim(turn_id)

    fake_redis.getdel.assert_awaited_once_with(f"pending:turn:{turn_id}")
    assert claimed is not None
    assert claimed.turn_id == turn_id
    assert claimed.session_id == original.session_id

  @pytest.mark.asyncio
  async def test_claim_returns_none_when_redis_returns_none(self) -> None:
    fake_redis = AsyncMock()
    fake_redis.getdel = AsyncMock(return_value=None)

    store = RedisPendingTurnStore(redis=fake_redis)
    result = await store.claim("missing-turn")

    assert result is None

  @pytest.mark.asyncio
  async def test_exists_uses_redis_exists(self) -> None:
    fake_redis = AsyncMock()
    fake_redis.exists = AsyncMock(return_value=1)

    store = RedisPendingTurnStore(redis=fake_redis)
    result = await store.exists("turn-x")

    fake_redis.exists.assert_awaited_once_with("pending:turn:turn-x")
    assert result is True

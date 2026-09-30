"""Pending-turn 저장소.

LLM 이 위치 기반 툴을 호출했을 때, 사용자 GPS 콜백을 기다리는 동안 한
턴 전체 (메시지 스냅샷 + 모든 tool_calls + 즉시 실행된 keyword 결과) 를
임시로 보관한다. 콜백이 도착하면 1회성 GETDEL 로 회수해 2nd LLM 호출에
이어 붙인다.

저장 형태:
- Redis 키:    ``pending:turn:{turn_id}``
- Redis 값:    ``PendingTurn`` 의 JSON 직렬화 (Hash 가 아님)
- TTL:         60s (기본)

Hash 대신 JSON string 을 쓰는 이유:
1. ``GETDEL`` 한 번에 atomic 회수 가능 (Hash 는 PIPELINE/Lua 필요)
2. Pydantic ``model_dump_json`` / ``model_validate_json`` 으로 round-trip
3. 필드 추가 시 마이그레이션 부담 없음
"""

import json
import logging
import time
from typing import Protocol, runtime_checkable
import uuid

from redis.asyncio import Redis

from app.dtos.tools import PendingTurn

logger = logging.getLogger(__name__)

DEFAULT_TTL_SEC = 60
_KEY_PREFIX = "pending:turn:"


def _key(turn_id: str) -> str:
  return f"{_KEY_PREFIX}{turn_id}"


@runtime_checkable
class PendingTurnStore(Protocol):
  """병렬 tool_calls 를 묶어 한 턴 단위로 보관하는 저장소 인터페이스."""

  async def create(self, turn: PendingTurn) -> str:
    """저장 후 부여된 ``turn_id`` 를 반환."""
    ...

  async def claim(self, turn_id: str) -> PendingTurn | None:
    """1회성 회수. 성공 시 저장본 삭제. 부재/만료 시 ``None``."""
    ...

  async def exists(self, turn_id: str) -> bool:
    """삭제·만료되지 않고 살아있는지 여부."""
    ...


class InMemoryPendingTurnStore:
  """테스트·로컬 전용 in-memory 구현.

  Redis 컨테이너 없이 단위 테스트에서 동작 계약을 검증하기 위해 둔다.
  ``clock`` 을 주입하면 frozen-time 으로 TTL 만료를 시뮬레이션할 수 있다.
  """

  def __init__(
    self,
    *,
    ttl_sec: int = DEFAULT_TTL_SEC,
    clock: "callable[[], float] | None" = None,
  ) -> None:
    self._ttl = ttl_sec
    self._clock = clock or time.monotonic
    self._store: dict[str, tuple[PendingTurn, float]] = {}

  async def create(self, turn: PendingTurn) -> str:
    """Persist a pending turn and return its newly assigned ``turn_id``."""
    turn_id = str(uuid.uuid4())
    stamped = turn.model_copy(update={"turn_id": turn_id})
    expires_at = self._clock() + self._ttl
    self._store[turn_id] = (stamped, expires_at)
    return turn_id

  async def claim(self, turn_id: str) -> PendingTurn | None:
    """Atomically pop a pending turn — returns ``None`` if missing/expired."""
    record = self._store.get(turn_id)
    if record is None:
      return None
    turn, expires_at = record
    if self._clock() >= expires_at:
      self._store.pop(turn_id, None)
      return None
    del self._store[turn_id]
    return turn

  async def exists(self, turn_id: str) -> bool:
    """Return whether a non-expired entry exists for ``turn_id``."""
    record = self._store.get(turn_id)
    if record is None:
      return False
    _, expires_at = record
    if self._clock() >= expires_at:
      self._store.pop(turn_id, None)
      return False
    return True


class RedisPendingTurnStore:
  """프로덕션용 Redis 구현 (``redis.asyncio`` 기반)."""

  def __init__(self, *, redis: Redis, ttl_sec: int = DEFAULT_TTL_SEC) -> None:
    self._redis = redis
    self._ttl = ttl_sec

  async def create(self, turn: PendingTurn) -> str:
    """Persist ``turn`` to Redis with TTL and return the newly assigned id."""
    turn_id = str(uuid.uuid4())
    stamped = turn.model_copy(update={"turn_id": turn_id})
    await self._redis.setex(_key(turn_id), self._ttl, stamped.model_dump_json())
    logger.info("[ToolCalling] pending store create turn=%s ttl=%ds", turn_id, self._ttl)
    return turn_id

  async def claim(self, turn_id: str) -> PendingTurn | None:
    """Atomic GETDEL — returns the stored turn or ``None`` if missing/stale."""
    raw = await self._redis.getdel(_key(turn_id))
    if raw is None:
      logger.warning("[ToolCalling] pending store claim miss turn=%s (expired or unknown)", turn_id)
      return None
    if isinstance(raw, bytes):
      raw = raw.decode("utf-8")
    try:
      pending = PendingTurn.model_validate_json(raw)
    except (json.JSONDecodeError, ValueError):
      # 이전 버전 스키마로 저장된 데이터 등 — 재진입 불가능, 무시.
      logger.warning("[ToolCalling] pending store claim parse fail turn=%s (stale schema?)", turn_id)
      return None
    logger.debug("[ToolCalling] pending store claim turn=%s", turn_id)
    return pending

  async def exists(self, turn_id: str) -> bool:
    """Cheap presence check (does NOT consume the key)."""
    return bool(await self._redis.exists(_key(turn_id)))

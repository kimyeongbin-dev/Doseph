"""FastAPI 측 Redis 클라이언트 — Producer 전용.

본 모듈은 ``app/`` (FastAPI) 마이크로서비스가 사용하는 Redis 클라이언트의
유일한 진입점이다. 책임 범위:

- HTTP 요청을 받아 RQ 큐(``ai``)에 Job 을 넣는다 (Producer)
- 짧은 lifecycle 의 상태값을 읽고 쓴다 (예: PendingTurn TTL=60s)

명시적 비-책임:
- LLM 호출, 임베딩, 모델 로드 등 **워커가 처리할 작업은 절대 import 하지 않음**
- ``ai_worker/`` 패키지는 본 모듈을 import 해서는 안 됨 (각자 자기 모듈 사용)

Idle drop / 좀비 커넥션 대비:
- ``socket_keepalive=True`` + ``health_check_interval=30`` + ``retry_on_timeout``
- producer 측은 HTTP 응답 latency 가 우선이라 **재시도 데코레이터를 적용하지
  않는다** — 실패 시 클라이언트(브라우저) 가 재시도하는 게 UX 일관성이 좋음.
  지속 재시도가 필요한 IO 는 ai-worker 가 담당.
"""

import redis
from redis.asyncio import Redis as AsyncRedis
from redis.asyncio import from_url as async_from_url
from redis.backoff import ExponentialBackoff
from redis.retry import Retry

# Producer 측 keepalive 옵션 — ai-worker 와 별도로 자체 정의(서비스 분리 원칙).
_KEEPALIVE_KWARGS = {
  "socket_keepalive": True,
  "health_check_interval": 30,
  "retry_on_timeout": True,
  "retry_on_error": [redis.ConnectionError, redis.TimeoutError],
  "retry": Retry(ExponentialBackoff(cap=10, base=1), retries=5),
}


def make_sync_redis(url: str, **overrides) -> redis.Redis:
  """Producer 용 sync Redis client.

  Args:
      url: redis://host:port/db 형태의 연결 URL.
      **overrides: ``decode_responses=True`` 등 호출자 명시 옵션.

  Returns:
      Hardened ``redis.Redis`` instance — RQ Queue 의 ``connection`` 인자로
      직접 주입 가능.
  """
  kwargs = {**_KEEPALIVE_KWARGS, **overrides}
  return redis.from_url(url, **kwargs)


def make_async_redis(url: str, **overrides) -> AsyncRedis:
  """Producer 용 async Redis client.

  Args:
      url: redis://host:port/db 형태의 연결 URL.
      **overrides: 호출자 명시 옵션.

  Returns:
      Hardened ``redis.asyncio.Redis`` instance — PendingTurnStore 등
      FastAPI 라우터 흐름 안에서 await 가능.
  """
  kwargs = {**_KEEPALIVE_KWARGS, **overrides}
  return async_from_url(url, **kwargs)

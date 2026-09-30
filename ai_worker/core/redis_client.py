"""ai-worker 측 Redis 클라이언트 — Consumer 전용.

본 모듈은 ``ai_worker/`` 마이크로서비스 내부에서만 사용된다. 책임 범위:

- RQ 큐(``ai``, ``default``)에서 Job 을 꺼내 LLM/임베딩 작업을 실행하는
  Consumer (``rq.SimpleWorker``) 에 Redis connection 을 제공한다
- Worker 내부의 보조 IO (예: OCR 결과 SETEX, status flag) 에도 동일 클라이언트
  사용

명시적 비-책임:
- FastAPI 라우터, HTTP 컨트롤러 등 producer 측 코드는 일절 포함하지 않음
- ``app/`` 패키지는 본 모듈을 import 해서는 안 됨 (각자 자기 모듈 사용)

Idle drop / 좀비 커넥션 대비:
- ``socket_keepalive=True`` + ``health_check_interval=30`` + ``retry_on_timeout``
- worker 는 long-living BLPOP loop 라 producer 보다 더 강한 보호가 필요하므로
  본 모듈의 keepalive 와 ``ai_worker.core.redis_retry.redis_retry`` 데코레이터
  를 **둘 다** 사용해야 한다.
"""

import redis
from redis.backoff import ExponentialBackoff
from redis.retry import Retry

# Consumer 측 keepalive — app 측과 동일 정책이지만 별도 정의(서비스 분리 원칙).
_KEEPALIVE_KWARGS = {
  "socket_keepalive": True,
  "health_check_interval": 30,
  "retry_on_timeout": True,
  "retry_on_error": [redis.ConnectionError, redis.TimeoutError],
  "retry": Retry(ExponentialBackoff(cap=10, base=1), retries=5),
}


def make_sync_redis(url: str, **overrides) -> redis.Redis:
  """Consumer 용 sync Redis client.

  Args:
      url: redis://host:port/db 형태의 연결 URL.
      **overrides: ``decode_responses=True``, ``socket_timeout=5`` (헬스체크용) 등.

  Returns:
      Hardened ``redis.Redis`` instance — ``rq.SimpleWorker`` 의 ``connection``
      인자에 직접 주입.
  """
  kwargs = {**_KEEPALIVE_KWARGS, **overrides}
  return redis.from_url(url, **kwargs)

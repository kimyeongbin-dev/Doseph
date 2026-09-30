# ruff: noqa: ANN002, ANN202
# 데코레이터 wrapper 의 *args/**kwargs 는 임의 함수 시그니처를 그대로 통과시키는
# 패턴이라 구체 타입을 줄 수 없다 (ParamSpec 사용은 가독성 손해 대비 가치 적음).
"""ai-worker 측 Redis IO 재시도 데코레이터 — Consumer 전용.

Keepalive (``ai_worker.core.redis_client``) 가 idle drop 의 1차 예방책이라면,
본 모듈은 좀비 커넥션·일시적 네트워크 hiccup 등으로 ``ConnectionError`` /
``TimeoutError`` 가 결국 raise 됐을 때의 2차 복구책이다.

본 데코레이터는 **ai-worker 가 처리하는 long-running 작업** (OCR 결과 저장,
임베딩 결과 publish 등) 에 한정해 적용한다. FastAPI producer 측은 HTTP 응답
latency 우선이라 재시도하지 않으며 (``app/core/redis_client.py`` 참조)
본 모듈을 import 해서는 안 된다.

특징:
- 외부 의존성 없이 ``functools.wraps`` 로 자체 구현 (tenacity 미사용)
- sync/async 함수 모두 같은 데코레이터로 처리 (런타임에 코루틴 여부 분기)
- 기본 정책: 최대 3회 재시도, 지수 백오프 (1s, 2s, 4s)
- Redis 모듈의 ``ConnectionError`` 와 ``TimeoutError`` 만 catch — 다른 예외는
  그대로 raise 해서 비즈니스 로직 버그를 숨기지 않음
"""

import asyncio
from collections.abc import Callable
import functools
import logging
import time

import redis

logger = logging.getLogger(__name__)

# 재시도 대상 예외 — sync 와 async 의 redis exception 클래스가 같음
# (redis.exceptions.ConnectionError, redis.exceptions.TimeoutError)
_RETRYABLE_EXCEPTIONS: tuple[type[BaseException], ...] = (
  redis.ConnectionError,
  redis.TimeoutError,
)


def redis_retry(
  max_attempts: int = 3,
  base_delay: float = 1.0,
) -> Callable:
  """Retry decorator for Redis IO (ai-worker 전용).

  Args:
      max_attempts: 최대 시도 횟수 (첫 호출 포함). 기본 3회.
      base_delay: 지수 백오프 기준 초 단위 (1, 2, 4, ...). 기본 1초.

  Returns:
      Decorator. sync/async 함수 모두 적용 가능.

  Examples:
      >>> @redis_retry()
      ... def store_value(key: str, value: str) -> None:
      ...   redis_conn.set(key, value)
  """

  def decorator(func: Callable) -> Callable:
    """Inner decorator — picks sync or async wrapper based on ``func``."""
    if asyncio.iscoroutinefunction(func):

      @functools.wraps(func)
      async def async_wrapper(*args, **kwargs):
        """Async retry wrapper — exponential backoff on Redis IO error."""
        last_exc: BaseException | None = None
        for attempt in range(1, max_attempts + 1):
          try:
            return await func(*args, **kwargs)
          except _RETRYABLE_EXCEPTIONS as exc:
            last_exc = exc
            if attempt == max_attempts:
              break
            delay = base_delay * (2 ** (attempt - 1))
            logger.warning(
              "Redis IO 실패 (attempt %d/%d): %s — %.1fs 후 재시도",
              attempt,
              max_attempts,
              exc,
              delay,
            )
            await asyncio.sleep(delay)
        logger.error("Redis IO 최종 실패 (%d회 시도 후): %s", max_attempts, last_exc)
        raise last_exc

      return async_wrapper

    @functools.wraps(func)
    def sync_wrapper(*args, **kwargs):
      """Sync retry wrapper — exponential backoff on Redis IO error."""
      last_exc: BaseException | None = None
      for attempt in range(1, max_attempts + 1):
        try:
          return func(*args, **kwargs)
        except _RETRYABLE_EXCEPTIONS as exc:
          last_exc = exc
          if attempt == max_attempts:
            break
          delay = base_delay * (2 ** (attempt - 1))
          logger.warning(
            "Redis IO 실패 (attempt %d/%d): %s — %.1fs 후 재시도",
            attempt,
            max_attempts,
            exc,
            delay,
          )
          time.sleep(delay)
      logger.error("Redis IO 최종 실패 (%d회 시도 후): %s", max_attempts, last_exc)
      raise last_exc

    return sync_wrapper

  return decorator

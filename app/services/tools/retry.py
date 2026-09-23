"""자체 retry decorator — tenacity 외부 의존 없이 ~50 라인.

사라진 계획 «feature/RAG» §4 D1 결정 — tenacity 가 아닌 자체 구현 채택.
🔑 **정본은 이 파일이다** — 재시도 정책을 여기서 정한다.

정책:
- max_attempts=2 (기본). 즉 첫 호출 + 1회 재시도 = 총 2회.
- exponential backoff: 0.5s → 1.0s (max 1초). 누적 max wait < 1.5s.
- retryable: ConnectionError, TimeoutError, OpenAI/Kakao 의 일시적 5xx.
- non-retryable: ValueError, TypeError, OpenAI BadRequestError (4xx) 즉시 raise.
- async/sync 자동 분기.

본 PR 의 적용 대상: ai_worker.tool_calling.jobs._dispatch 내부 외부 호출
(Kakao API, OpenAI Embedding API). RAG retrieval 자체는 DB 라 retry 불필요.
"""

import asyncio
from collections.abc import Awaitable, Callable
import functools
import logging
from typing import TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")


def retry_async(
    *,
    max_attempts: int = 2,
    initial_backoff: float = 0.5,
    max_backoff: float = 1.0,
    retryable: tuple[type[BaseException], ...] = (ConnectionError, TimeoutError),
) -> Callable[[Callable[..., Awaitable[T]]], Callable[..., Awaitable[T]]]:
    """비동기 함수를 retry 로 감싸는 decorator factory.

    Args:
        max_attempts: 최대 호출 횟수 (재시도 + 첫 호출). 기본 2.
        initial_backoff: 첫 재시도 전 대기 (초). 기본 0.5.
        max_backoff: 누적 backoff 상한 (초). 기본 1.0.
        retryable: 재시도 대상 예외 클래스 tuple. 다른 예외는 즉시 raise.

    Returns:
        decorated async function. 모든 시도 실패 시 마지막 예외 propagate.
    """

    def decorator(func: Callable[..., Awaitable[T]]) -> Callable[..., Awaitable[T]]:
        @functools.wraps(func)
        async def wrapper(*args: object, **kwargs: object) -> T:
            backoff = initial_backoff
            last_exc: BaseException | None = None
            for attempt in range(1, max_attempts + 1):
                try:
                    return await func(*args, **kwargs)
                except retryable as exc:
                    last_exc = exc
                    if attempt >= max_attempts:
                        logger.warning(
                            "[retry] %s exhausted %d/%d attempts: %s",
                            func.__name__,
                            attempt,
                            max_attempts,
                            type(exc).__name__,
                        )
                        raise
                    logger.info(
                        "[retry] %s attempt %d/%d failed (%s) — sleep %.2fs",
                        func.__name__,
                        attempt,
                        max_attempts,
                        type(exc).__name__,
                        backoff,
                    )
                    await asyncio.sleep(backoff)
                    backoff = min(backoff * 2, max_backoff)
            # unreachable — loop returns or raises
            raise last_exc if last_exc is not None else RuntimeError("retry_async unreachable")

        return wrapper

    return decorator

"""Unit tests for app.services.tools.retry — 자체 구현 retry decorator (D1).

PLAN.md (feature/RAG) §4.1 Step 2 — retry helper 의 4가지 의도된 동작.
Phase 3 [Implement] 통과 검증 (Green).
"""

from __future__ import annotations

import pytest

from app.services.tools.retry import retry_async


class TestRetryAsync:
  """retry_async decorator factory 단위 테스트."""

  @pytest.mark.asyncio
  async def test_retry_once_then_success(self) -> None:
    """일시적 ConnectionError 1회 후 성공 → 호출 2번 (재시도 1회)."""
    call_count = 0

    @retry_async(max_attempts=2, initial_backoff=0.01, max_backoff=0.01)
    async def _flaky() -> str:
      nonlocal call_count
      call_count += 1
      if call_count == 1:
        raise ConnectionError("transient")
      return "ok"

    result = await _flaky()
    assert result == "ok"
    assert call_count == 2

  @pytest.mark.asyncio
  async def test_all_attempts_fail_propagate(self) -> None:
    """max_attempts 모두 ConnectionError → 마지막 예외 propagate."""
    call_count = 0

    @retry_async(max_attempts=2, initial_backoff=0.01, max_backoff=0.01)
    async def _always_fail() -> None:
      nonlocal call_count
      call_count += 1
      raise ConnectionError("permanent")

    with pytest.raises(ConnectionError, match="permanent"):
      await _always_fail()
    assert call_count == 2

  @pytest.mark.asyncio
  async def test_non_retryable_immediate_raise(self) -> None:
    """ValueError 는 retryable 에 없음 → retry 안함, 즉시 raise."""
    call_count = 0

    @retry_async(max_attempts=3, initial_backoff=0.01)
    async def _bad_input() -> None:
      nonlocal call_count
      call_count += 1
      raise ValueError("invalid")

    with pytest.raises(ValueError, match="invalid"):
      await _bad_input()
    assert call_count == 1  # retry 안함

  @pytest.mark.asyncio
  async def test_decorator_factory_returns_callable(self) -> None:
    """decorator factory 는 사용 가능한 callable 반환."""

    @retry_async()
    async def _noop() -> int:
      return 42

    assert await _noop() == 42

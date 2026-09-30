"""Rate limiting service module.

This module provides rate limiting functionality to prevent abuse.
Currently uses in-memory storage for single worker environments.
For production with multiple workers, Redis-based implementation is recommended.
"""

from abc import ABC, abstractmethod
import time

from fastapi import HTTPException, status


class RateLimiter(ABC):
  """Abstract base class for rate limiters."""

  @abstractmethod
  def check(self, key: str) -> None:
    """Check rate limit for given key.

    Args:
        key: Identifier for rate limiting (e.g., IP address).

    Raises:
        HTTPException: If rate limit is exceeded.
    """


class InMemoryRateLimiter(RateLimiter):
  """In-memory based rate limiter.

  Warning: In multi-worker environments, each worker maintains separate state.
  For production environments, RedisRateLimiter is recommended.

  Attributes:
      max_requests: Maximum number of requests allowed in the time window.
      window_seconds: Time window duration in seconds.
  """

  def __init__(self, max_requests: int = 10, window_seconds: int = 60) -> None:
    """Initialize in-memory rate limiter.

    Args:
        max_requests: Maximum requests allowed per window.
        window_seconds: Time window duration in seconds.
    """
    self.max_requests = max_requests
    self.window_seconds = window_seconds
    self._tracker: dict[str, tuple[int, float]] = {}

  def check(self, key: str) -> None:
    """Check rate limit for given key.

    Args:
        key: Identifier for rate limiting.

    Raises:
        HTTPException: If rate limit is exceeded.
    """
    current_time = time.time()

    if key in self._tracker:
      count, timestamp = self._tracker[key]

      # Reset if window exceeded
      if current_time - timestamp > self.window_seconds:
        self._tracker[key] = (1, current_time)
        return

      # Check if request count exceeded
      if count >= self.max_requests:
        raise HTTPException(
          status_code=status.HTTP_429_TOO_MANY_REQUESTS,
          detail={
            "error": "rate_limit_exceeded",
            "error_description": (f"Request limit exceeded. Please try again after {self.window_seconds} seconds."),
          },
        )

      self._tracker[key] = (count + 1, timestamp)
    else:
      self._tracker[key] = (1, current_time)


# Default instance for dependency injection
default_rate_limiter = InMemoryRateLimiter(max_requests=10, window_seconds=60)


def get_rate_limiter() -> RateLimiter:
  """Get rate limiter dependency.

  Returns:
      RateLimiter: Rate limiter instance.
  """
  return default_rate_limiter

"""Rate limiting middleware module.

This module provides IP-based rate limiting middleware with different limits
for various request types:
- GET requests: Lenient limits
- Mutation requests (POST/PATCH/DELETE): Strict limits
- Authentication endpoints: Strictest limits

Note: Redis-based storage is recommended for production environments.
"""

from collections.abc import Awaitable, Callable
import logging
import time

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from app.core.config import config

logger = logging.getLogger(__name__)


class RateLimitConfig:
    """Rate limiting window settings.

    Request thresholds live in `Config` (RATE_LIMIT_*_MAX_REQUESTS) so a single
    high-volume client (e.g. an E2E suite) can be accommodated by environment
    rather than by editing code. Only the observation windows stay constant.
    """

    # 관측 구간은 환경과 무관하게 고정 — 한도만 env 로 조정한다.
    GET_WINDOW_SECONDS = 60
    MUTATION_WINDOW_SECONDS = 60
    AUTH_WINDOW_SECONDS = 60

    # Excluded paths (health checks, documentation, etc.)
    EXCLUDED_PATHS = {
        "/health",
        "/api/docs",
        "/api/redoc",
        "/api/openapi.json",
    }

    # Authentication-related path patterns
    AUTH_PATH_PREFIXES = {
        "/api/v1/auth/",
        "/api/v1/oauth/",
    }


class InMemoryRateLimitStore:
    """In-memory rate limit storage.

    Warning: In multi-worker environments, each worker maintains separate state.
    Redis-based storage is recommended for production environments.
    """

    def __init__(self) -> None:
        # key: (count, window_start_time)
        self._store: dict[str, tuple[int, float]] = {}
        self._last_cleanup = time.time()
        self._cleanup_interval = 300  # Cleanup every 5 minutes

    def check_and_increment(self, key: str, max_requests: int, window_seconds: int) -> bool:
        """Check rate limit and increment counter.

        Args:
            key: Rate limit key.
            max_requests: Maximum allowed requests.
            window_seconds: Time window in seconds.

        Returns:
            bool: True if allowed, False if rate limit exceeded.
        """
        current_time = time.time()

        # Periodic cleanup
        if current_time - self._last_cleanup > self._cleanup_interval:
            self._cleanup_expired(current_time)

        if key in self._store:
            count, window_start = self._store[key]

            # Reset if window exceeded
            if current_time - window_start > window_seconds:
                self._store[key] = (1, current_time)
                return True

            # Request count exceeded
            if count >= max_requests:
                return False

            self._store[key] = (count + 1, window_start)
        else:
            self._store[key] = (1, current_time)

        return True

    def _cleanup_expired(self, current_time: float) -> None:
        """Clean up expired entries.

        Args:
            current_time: Current timestamp.
        """
        max_window = max(
            RateLimitConfig.GET_WINDOW_SECONDS,
            RateLimitConfig.MUTATION_WINDOW_SECONDS,
            RateLimitConfig.AUTH_WINDOW_SECONDS,
        )
        expired_keys = [key for key, (_, ts) in self._store.items() if current_time - ts > max_window * 2]
        for key in expired_keys:
            del self._store[key]
        self._last_cleanup = current_time


# Global storage instance
_rate_limit_store = InMemoryRateLimitStore()


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Rate limiting middleware for request throttling."""

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        """Apply per-IP rate limit then forward to the next ASGI handler.

        Limits depend on path/method (auth strictest, mutations medium, GET lenient).
        Excluded paths (health/docs) bypass entirely.

        Args:
            request: Incoming HTTP request.
            call_next: Next ASGI middleware/handler.

        Returns:
            Response from the downstream handler, or 429 JSON when limit exceeded.
        """
        path = request.url.path
        method = request.method

        # Check excluded paths
        if path in RateLimitConfig.EXCLUDED_PATHS:
            return await call_next(request)

        # Extract client IP
        client_ip = self._get_client_ip(request)

        # Determine rate limit settings
        max_requests, window_seconds = self._get_rate_limit(path, method)

        # Check rate limit
        rate_key = f"{client_ip}:{method}:{self._get_path_category(path)}"
        if not _rate_limit_store.check_and_increment(rate_key, max_requests, window_seconds):
            logger.warning(
                "Rate limit exceeded: ip=%s, method=%s, path=%s",
                client_ip,
                method,
                path,
            )
            return Response(
                content=(
                    '{"error":"rate_limit_exceeded",'
                    '"error_description":"Request limit exceeded. Please try again later."}'
                ),
                status_code=429,
                media_type="application/json",
                headers={"Retry-After": str(window_seconds)},
            )

        return await call_next(request)

    def _get_client_ip(self, request: Request) -> str:
        """Extract client IP address considering proxies.

        Args:
            request: FastAPI request object.

        Returns:
            str: Client IP address.
        """
        # Check X-Forwarded-For header (behind proxy/load balancer)
        forwarded_for = request.headers.get("X-Forwarded-For")
        if forwarded_for:
            # First IP is the actual client
            return forwarded_for.split(",")[0].strip()

        # Check X-Real-IP header (Nginx)
        real_ip = request.headers.get("X-Real-IP")
        if real_ip:
            return real_ip

        # Direct connection
        if request.client:
            return request.client.host

        return "unknown"

    def _get_rate_limit(self, path: str, method: str) -> tuple[int, int]:
        """Get rate limit based on path and method.

        Args:
            path: Request path.
            method: HTTP method.

        Returns:
            tuple[int, int]: (max_requests, window_seconds)
        """
        # Authentication-related paths
        for prefix in RateLimitConfig.AUTH_PATH_PREFIXES:
            if path.startswith(prefix):
                return config.RATE_LIMIT_AUTH_MAX_REQUESTS, RateLimitConfig.AUTH_WINDOW_SECONDS

        # Mutation requests
        if method in ("POST", "PATCH", "PUT", "DELETE"):
            return (
                config.RATE_LIMIT_MUTATION_MAX_REQUESTS,
                RateLimitConfig.MUTATION_WINDOW_SECONDS,
            )

        # Regular GET requests
        return config.RATE_LIMIT_GET_MAX_REQUESTS, RateLimitConfig.GET_WINDOW_SECONDS

    def _get_path_category(self, path: str) -> str:
        """Get path category for rate limit key generation.

        Args:
            path: Request path.

        Returns:
            str: Path category.
        """
        for prefix in RateLimitConfig.AUTH_PATH_PREFIXES:
            if path.startswith(prefix):
                return "auth"
        return "api"

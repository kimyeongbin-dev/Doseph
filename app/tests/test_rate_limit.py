"""Tests for configurable per-IP rate limit thresholds.

The limits used to be hardcoded class constants, which made high-volume
environments (E2E suites hitting the API from a single IP) trip the production
thresholds with no way to adjust. 12-factor Factor III: same code, limits from
the environment.
"""

import pytest

from app.core.config import Config, config
from app.middlewares.rate_limit import RateLimitConfig, RateLimitMiddleware


@pytest.fixture
def middleware() -> RateLimitMiddleware:
    """Middleware instance for pure limit-selection tests (no ASGI app needed)."""
    return RateLimitMiddleware(app=None)  # type: ignore[arg-type]


# ── 한도 선택이 config 를 따르는지 ───────────────────────────────────
# 흐름: config 값 교체 -> _get_rate_limit 이 그 값을 반환 -> 하드코딩 회귀 차단
def test_get_limit_follows_config(
    middleware: RateLimitMiddleware,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(config, "RATE_LIMIT_GET_MAX_REQUESTS", 1234)
    monkeypatch.setattr(config, "RATE_LIMIT_MUTATION_MAX_REQUESTS", 56)
    monkeypatch.setattr(config, "RATE_LIMIT_AUTH_MAX_REQUESTS", 7)

    assert middleware._get_rate_limit("/api/v1/medications", "GET")[0] == 1234
    assert middleware._get_rate_limit("/api/v1/medications", "POST")[0] == 56
    assert middleware._get_rate_limit("/api/v1/auth/me", "GET")[0] == 7


# ── 경로/메서드별 분기 ───────────────────────────────────────────────
# 흐름: auth 접두사 우선 -> 변경 메서드 -> 나머지 GET
def test_auth_prefix_wins_over_method(
    middleware: RateLimitMiddleware,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(config, "RATE_LIMIT_MUTATION_MAX_REQUESTS", 56)
    monkeypatch.setattr(config, "RATE_LIMIT_AUTH_MAX_REQUESTS", 7)

    # POST 이지만 /api/v1/auth/ 접두사라 인증 한도(가장 엄격)가 적용돼야 한다
    assert middleware._get_rate_limit("/api/v1/auth/refresh", "POST")[0] == 7


# ── 윈도우 길이는 코드 상수로 유지 ───────────────────────────────────
# 한도만 환경별로 조정하고 관측 구간(60초)은 고정해 비교 가능성을 지킨다.
def test_windows_stay_constant(middleware: RateLimitMiddleware) -> None:
    assert middleware._get_rate_limit("/api/v1/medications", "GET")[1] == (RateLimitConfig.GET_WINDOW_SECONDS)
    assert middleware._get_rate_limit("/api/v1/auth/me", "GET")[1] == (RateLimitConfig.AUTH_WINDOW_SECONDS)


# ── 기본값은 운영 기준 ───────────────────────────────────────────────
# env 를 주지 않으면 기존 하드코딩 값과 같아야 한다(운영 동작 불변).
def test_defaults_match_previous_hardcoded_values() -> None:
    fields = Config.model_fields
    assert fields["RATE_LIMIT_GET_MAX_REQUESTS"].default == 200
    assert fields["RATE_LIMIT_MUTATION_MAX_REQUESTS"].default == 30
    assert fields["RATE_LIMIT_AUTH_MAX_REQUESTS"].default == 10

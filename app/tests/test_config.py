"""Tests for environment-driven URL configuration in production.

Enforces 12-factor portability: production must inject public URLs via env
(no hardcoded platform URLs baked into the code). Missing URLs in production
must fail fast at startup rather than silently falling back to a stale default.
"""

from pydantic import ValidationError
import pytest

from app.core.config import _ENV_URLS, Config, Env, docs_urls

# PROD 검증 통과에 필요한 최소 시크릿(기본값이면 별도 검증에 걸리므로 실제값 형태로 주입)
_PROD_SECRETS = {
    "SECRET_KEY": "A" * 64,
    "DB_PASSWORD": "real-db-password",
    "KAKAO_CLIENT_ID": "real-kakao-id",
    "KAKAO_CLIENT_SECRET": "real-kakao-secret",
}
_PROD_URLS = {
    "API_BASE_URL": "https://api.doseph.com",
    "FRONTEND_URL": "https://doseph.com",
    "KAKAO_REDIRECT_URI": "https://doseph.com/auth/kakao/callback",
}


def _prod_config(**overrides: str) -> Config:
    """Build a PROD Config isolated from any local .env file."""
    # 동적 **kwargs 언패킹은 Pydantic 모델의 필드별 타입과 정적으로 대응시킬 수 없다
    # (파라미터 후보마다 arg-type 오류가 하나씩 발생). 테스트 전용 헬퍼이고 값은
    # 전부 str 이므로 이 한 줄만 명시적으로 무시한다.
    return Config(
        _env_file=None,
        ENV=Env.PROD,
        **{**_PROD_SECRETS, **overrides},  # type: ignore[arg-type]
    )


def test_prod_with_all_urls_ok() -> None:
    """PROD + 3개 URL env 주입 시 정상 생성 + 값 보존."""
    cfg = _prod_config(**_PROD_URLS)

    assert cfg.API_BASE_URL == "https://api.doseph.com"
    assert cfg.FRONTEND_URL == "https://doseph.com"
    assert cfg.KAKAO_REDIRECT_URI == "https://doseph.com/auth/kakao/callback"


@pytest.mark.parametrize("missing", ["API_BASE_URL", "FRONTEND_URL", "KAKAO_REDIRECT_URI"])
def test_prod_missing_url_raises(missing: str) -> None:
    """PROD 인데 필수 URL 중 하나라도 없으면 기동 실패(ValueError)."""
    urls = {k: v for k, v in _PROD_URLS.items() if k != missing}

    with pytest.raises(ValueError, match=missing):
        _prod_config(**urls)


def test_local_still_gets_localhost_defaults() -> None:
    """LOCAL 은 여전히 localhost 기본값을 자동 적용(회귀 방지)."""
    cfg = Config(_env_file=None, ENV=Env.LOCAL)

    assert cfg.API_BASE_URL == "http://localhost:8000"
    assert cfg.FRONTEND_URL == "http://localhost:3000"


def test_env_is_required_and_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    """ENV 가 없으면 기동 실패(fail-closed).

    과거 기본값 Env.LOCAL 은 실패 방향이 잘못됐다 — .env 유실 시 프로덕션이 조용히
    local 로 부팅해 mock IdP 등록 + prod 필수값 검증 스킵으로 이어진다.
    """
    monkeypatch.delenv("ENV", raising=False)

    with pytest.raises(ValidationError, match="ENV"):
        Config(_env_file=None)


def test_prod_env_urls_have_no_hardcoded_platform_defaults() -> None:
    """PROD 프로필에 vercel/duckdns 등 플랫폼 URL 하드코딩이 없어야 함."""
    prod_urls = _ENV_URLS[Env.PROD]

    assert prod_urls["API_BASE_URL"] is None
    assert prod_urls["FRONTEND_URL"] is None
    assert prod_urls["KAKAO_REDIRECT_URI"] is None


def test_docs_urls_hidden_in_prod() -> None:
    """PROD 에서는 Swagger/redoc/openapi 를 노출하지 않음(전부 None)."""
    urls = docs_urls(Env.PROD)

    assert urls["docs_url"] is None
    assert urls["redoc_url"] is None
    assert urls["openapi_url"] is None


@pytest.mark.parametrize("env", [Env.LOCAL, Env.DEV])
def test_docs_urls_exposed_in_non_prod(env: Env) -> None:
    """LOCAL/DEV 는 API 문서를 노출(경로 제공)."""
    urls = docs_urls(env)

    assert urls["docs_url"] == "/api/docs"
    assert urls["redoc_url"] == "/api/redoc"
    assert urls["openapi_url"] == "/api/openapi.json"

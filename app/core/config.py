"""Application configuration module.

This module contains configuration settings for different environments
(local, dev, prod) and handles environment-specific URL configurations.
Follows modern Python configuration patterns with pydantic-settings.
"""

from enum import StrEnum
from pathlib import Path
import secrets
import zoneinfo

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Env(StrEnum):
    """Environment enumeration for different deployment stages.

    Defines the available deployment environments with their
    corresponding configuration requirements.
    """

    LOCAL = "local"
    DEV = "dev"
    PROD = "prod"


# Environment-specific URL configurations
# local/dev: Local Docker environment (same settings, different login button)
# prod: Platform-neutral — public URLs MUST be injected via .env (12-factor).
#       No platform-specific URL is hardcoded here so the app stays portable
#       across hosting providers (GCP/Cloudflare today, anything tomorrow).
_ENV_URLS: dict[Env, dict[str, str | None]] = {
    Env.LOCAL: {
        # Local environment: Local Docker (dev login button visible)
        "COOKIE_DOMAIN": "localhost",
        "API_BASE_URL": "http://localhost:8000",
        "FRONTEND_URL": "http://localhost:3000",
        "KAKAO_REDIRECT_URI": "http://localhost:3000/auth/kakao/callback",
    },
    Env.DEV: {
        # Dev environment: Local Docker (dev login button hidden, for Kakao testing)
        "COOKIE_DOMAIN": "localhost",
        "API_BASE_URL": "http://localhost:8000",
        "FRONTEND_URL": "http://localhost:3000",
        "KAKAO_REDIRECT_URI": "http://localhost:3000/auth/kakao/callback",
    },
    Env.PROD: {
        # Prod environment: URLs come from .env only (validated below). Do NOT
        # hardcode a hosting provider's URL here — it couples code to a platform.
        "COOKIE_DOMAIN": None,  # host-only cookie (FE/API share the same site)
        "API_BASE_URL": None,
        "FRONTEND_URL": None,
        "KAKAO_REDIRECT_URI": None,
    },
}

# Default values for development
_DEFAULT_SECRET_KEY = f"dev-only-secret-key-{secrets.token_hex(16)}"
_DEFAULT_DB_PASSWORD = "change_me_in_production"
_DEFAULT_KAKAO_CLIENT_ID = "mock_kakao_client_id"
_DEFAULT_KAKAO_CLIENT_SECRET = "mock_kakao_client_secret"


class Config(BaseSettings):
    """Application configuration class.

    This class handles all configuration settings for the application,
    including database, JWT, OAuth, and environment-specific settings.
    Uses modern pydantic-settings for robust configuration management.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="allow",
    )

    # ── 환경 선택 (필수 · fail-closed) ────────────────────────────────
    # 기본값을 두지 않는다. 미설정 시 기동 단계에서 즉시 실패시키기 위함이다.
    # 과거 기본값은 Env.LOCAL 이었는데, 이는 실패 방향이 잘못됐다(fail-open):
    # .env 유실·이름 오타·env_file 로딩 실패 시 프로덕션이 조용히 local 로 부팅하고
    #   (1) mock IdP 라우터가 등록되며 (2) prod 필수값 검증이 통째로 스킵된다.
    # 안전한 기본값이 없는 설정은 "명시 필수"가 정답이다(OWASP Secure by Default /
    # Fail Safe Defaults, 12-factor Config).
    ENV: Env
    SECRET_KEY: str = _DEFAULT_SECRET_KEY
    TIMEZONE: zoneinfo.ZoneInfo = Field(default_factory=lambda: zoneinfo.ZoneInfo("Asia/Seoul"))
    TEMPLATE_DIR: str = str(Path(__file__).resolve().parent.parent / "templates")

    # Database settings (not auto-configured by ENV - sensitive information)
    DB_HOST: str = "postgres"
    DB_PORT: int = 5432
    DB_USER: str = "doseph_admin"
    DB_PASSWORD: str = _DEFAULT_DB_PASSWORD
    DB_NAME: str = "doseph_db"
    DB_SSL: bool = False  # 관리형 PG(Neon 등) TLS 연결 시 True — asyncpg ssl="require" 주입 (로컬/DEV 는 False)
    DB_CONNECT_TIMEOUT: int = 10  # asyncpg pool 새 connection 생성 한도 — 5초는 OCR 폴링/RQ 부하 시 일시 timeout 유발
    DB_CONNECTION_POOL_MAXSIZE: int = 20  # SSE long-poll + RQ + 스케줄러 동시 보유로 10 은 한계 — 20 으로 상향

    # Redis (RAG 임베딩·LLM RQ job 큐 + 세션 캐시)
    REDIS_URL: str = "redis://redis:6379/0"

    # URL settings (auto-configured based on ENV)
    COOKIE_DOMAIN: str | None = None
    API_BASE_URL: str | None = None
    FRONTEND_URL: str | None = None

    # JWT settings
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    REFRESH_TOKEN_EXPIRE_MINUTES: int = 14 * 24 * 60  # 14 days
    JWT_LEEWAY: int = 5

    # ── Rate limit (IP 기준 요청 한도) ────────────────────────────────
    # 기본값 = 운영 기준. 한 IP 에서 대량 요청이 정상인 환경(E2E 스위트 등)만
    # env 로 올린다 — 코드는 그대로 두고 값만 환경별로 (12-factor Factor III).
    # 관측 구간(윈도우 초)은 비교 가능성을 위해 코드 상수로 고정.
    RATE_LIMIT_GET_MAX_REQUESTS: int = 200
    RATE_LIMIT_MUTATION_MAX_REQUESTS: int = 30
    RATE_LIMIT_AUTH_MAX_REQUESTS: int = 10

    # External API settings
    OPENAI_API_KEY: str | None = None
    DATA_GO_KR_API_KEY: str | None = None

    # 식약처 회수·판매중지 API (Phase 7) ────────────────────────────────
    # base URL 의 service number 는 04 고정, list/detail method 는 03
    # (식약처가 메서드 버전 갱신 시 코드 수정 없이 env 만 교체)
    DATA_GO_KR_RECALL_BASE_URL: str = "http://apis.data.go.kr/1471000/MdcinRtrvlSleStpgeInfoService04"
    DATA_GO_KR_RECALL_LIST_METHOD: str = "getMdcinRtrvlSleStpgeList03"
    DATA_GO_KR_RECALL_DETAIL_METHOD: str = "getMdcinRtrvlSleStpgeItem03"
    # None 이면 DATA_GO_KR_API_KEY 폴백
    DATA_GO_KR_RECALL_API_KEY: str | None = None
    # 의약외품(치약·칫솔 등) 차단 토글
    RECALL_FILTER_NON_DRUG: bool = True

    # Kakao OAuth settings
    KAKAO_CLIENT_ID: str = _DEFAULT_KAKAO_CLIENT_ID
    KAKAO_CLIENT_SECRET: str = _DEFAULT_KAKAO_CLIENT_SECRET
    KAKAO_REDIRECT_URI: str | None = None

    @model_validator(mode="after")
    def apply_env_defaults(self) -> "Config":
        """Apply environment-specific default values.

        Returns:
            Config: The updated configuration instance.
        """
        env_urls = _ENV_URLS.get(self.ENV, _ENV_URLS[Env.LOCAL])

        if self.COOKIE_DOMAIN is None:
            self.COOKIE_DOMAIN = env_urls["COOKIE_DOMAIN"]
        if self.API_BASE_URL is None:
            self.API_BASE_URL = env_urls["API_BASE_URL"]
        if self.FRONTEND_URL is None:
            self.FRONTEND_URL = env_urls["FRONTEND_URL"]
        if self.KAKAO_REDIRECT_URI is None:
            self.KAKAO_REDIRECT_URI = env_urls["KAKAO_REDIRECT_URI"]

        return self

    @model_validator(mode="after")
    def validate_production_secrets(self) -> "Config":
        """Validate that production secrets are properly configured.

        Raises:
            ValueError: If required production secrets are not set.

        Returns:
            Config: The validated configuration instance.
        """
        if self.ENV == Env.PROD:
            errors = []

            if self.SECRET_KEY == _DEFAULT_SECRET_KEY or self.SECRET_KEY.startswith("dev-only-"):
                errors.append("SECRET_KEY must be set in production environment")

            if self.DB_PASSWORD == _DEFAULT_DB_PASSWORD:
                errors.append("DB_PASSWORD must be set in production environment")

            if self.KAKAO_CLIENT_ID == _DEFAULT_KAKAO_CLIENT_ID:
                errors.append("KAKAO_CLIENT_ID must be set in production environment")

            if self.KAKAO_CLIENT_SECRET == _DEFAULT_KAKAO_CLIENT_SECRET:
                errors.append("KAKAO_CLIENT_SECRET must be set in production environment")

            # 공개 URL 은 프로덕션에서 반드시 env 로 주입되어야 함(하드코딩 폴백 없음).
            # 누락 시 CORS/쿠키/카카오 redirect 가 조용히 깨지므로 기동 단계에서 차단.
            if self.API_BASE_URL is None:
                errors.append("API_BASE_URL must be set in production environment")

            if self.FRONTEND_URL is None:
                errors.append("FRONTEND_URL must be set in production environment")

            if self.KAKAO_REDIRECT_URI is None:
                errors.append("KAKAO_REDIRECT_URI must be set in production environment")

            if errors:
                error_message = f"Production configuration errors: {'; '.join(errors)}"
                raise ValueError(error_message)

        return self


# ── API 문서 노출 정책 ────────────────────────────────────────────────
# 흐름: ENV 판별 -> prod 면 docs/redoc/openapi URL 을 None 으로 반환(비노출)
#       -> 프로덕션에서 API 스키마 정보 유출 차단, 개발/로컬만 문서 제공
def docs_urls(env: Env) -> dict[str, str | None]:
    """Return FastAPI docs URLs, disabled in production.

    Args:
        env: The active deployment environment.

    Returns:
        dict[str, str | None]: docs_url/redoc_url/openapi_url. All None in
        production so the API schema is not exposed publicly.
    """
    if env == Env.PROD:
        return {"docs_url": None, "redoc_url": None, "openapi_url": None}
    return {
        "docs_url": "/api/docs",
        "redoc_url": "/api/redoc",
        "openapi_url": "/api/openapi.json",
    }


# Global configuration instance
config = Config()

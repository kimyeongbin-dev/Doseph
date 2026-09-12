"""FastAPI application main module.

This module contains the FastAPI application setup, middleware configuration,
and global exception handlers.
"""

import logging

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from tortoise.exceptions import BaseORMException, DBConnectionError

from app.apis.v1 import v1_routers
from app.core.config import Env, config, docs_urls
from app.core.logger import log_handled_exception
from app.db.databases import initialize_tortoise
from app.middlewares.rate_limit import RateLimitMiddleware
from app.middlewares.request_context import RequestContextMiddleware
from app.middlewares.security import SecurityMiddleware
from app.workers.scheduler import scheduler_lifespan

logger = logging.getLogger(__name__)

# ── FastAPI 앱 생성 (API 문서는 비프로덕션에서만 노출) ─────────────────
# 흐름: docs_urls(ENV) 로 문서 URL 결정 -> prod 는 None(스키마 비노출)
#       -> 미들웨어/라우터/예외핸들러 등록
app = FastAPI(
    **docs_urls(config.ENV),
    debug=False,  # 하드닝: 디버그 모드 명시적 비활성(예외 스택트레이스/내부정보 노출 차단, 실수로도 안 켜지게)
    redirect_slashes=False,  # 트레일링 슬래시 정규화는 엣지(Cloudflare)에서 처리
    lifespan=scheduler_lifespan,
)


# Global exception handlers


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(_request: Request, exc: RequestValidationError) -> JSONResponse:
    """Handle Pydantic validation errors.

    Converts 422 validation errors to 400 bad request with detailed error info.

    Args:
        request: The incoming request.
        exc: The validation exception.

    Returns:
        JSONResponse: Error response with validation details.
    """
    return JSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST,
        content={
            "error": "validation_error",
            "error_description": "입력값 유효성 검사에 실패했습니다.",
            "details": exc.errors(),
        },
    )


@app.exception_handler(DBConnectionError)
async def db_connection_exception_handler(request: Request, exc: DBConnectionError) -> JSONResponse:
    """Handle database connection errors.

    Args:
        request: The incoming request.
        exc: The database connection exception.

    Returns:
        JSONResponse: 503 Service Unavailable response.
    """
    log_handled_exception(logger, exc, method=request.method, path=request.url.path, kind="db_connection")
    return JSONResponse(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        content={
            "error": "db_connection_failed",
            "error_description": "데이터베이스 연결에 실패했습니다. 잠시 후 다시 시도해주세요.",
        },
    )


@app.exception_handler(BaseORMException)
async def orm_exception_handler(request: Request, exc: BaseORMException) -> JSONResponse:
    """Handle other Tortoise ORM errors.

    Args:
        request: The incoming request.
        exc: The ORM exception.

    Returns:
        JSONResponse: 500 Internal Server Error response.
    """
    log_handled_exception(logger, exc, method=request.method, path=request.url.path, kind="orm")
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "error": "database_error",
            "error_description": "데이터베이스 작업 중 오류가 발생했습니다.",
            "details": str(exc) if app.debug else None,
        },
    )


@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Handle all unexpected errors.

    Args:
        request: The incoming request.
        exc: The general exception.

    Returns:
        JSONResponse: 500 Internal Server Error response.
    """
    log_handled_exception(logger, exc, method=request.method, path=request.url.path, kind="unhandled")
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "error": "internal_server_error",
            "error_description": "서버 내부에서 예상치 못한 오류가 발생했습니다.",
        },
    )


# Middleware configuration

# CORS settings (environment-specific)
# localhost is only accessible from local machine, so it's safe to allow in all environments
# 로컬 독립 API 전환(④): FE(:3000)가 fastapi(:8000)를 직접 호출 → nginx:80 오리진 제거.
_LOCALHOST_ORIGINS = ["http://localhost:3000", "http://127.0.0.1:3000"]

if config.ENV == Env.PROD:
    # Production: FRONTEND_URL (env-injected, e.g. https://doseph.com) + localhost for local prod testing
    cors_origins = [config.FRONTEND_URL, *_LOCALHOST_ORIGINS]
    cors_methods = ["GET", "POST", "PATCH", "DELETE", "OPTIONS"]
    cors_headers = ["Content-Type", "Authorization"]
elif config.ENV == Env.DEV:
    # Development/test: FRONTEND_URL + localhost allowed
    cors_origins = [config.FRONTEND_URL, *_LOCALHOST_ORIGINS]
    cors_methods = ["*"]
    cors_headers = ["*"]
else:
    # Local environment: localhost only
    cors_origins = _LOCALHOST_ORIGINS
    cors_methods = ["*"]
    cors_headers = ["*"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,  # Allow cookies (refresh_token) transmission
    allow_methods=cors_methods,
    allow_headers=cors_headers,
)

# Security middleware (input validation + security headers)
app.add_middleware(SecurityMiddleware)

# Rate limiting middleware (IP-based)
app.add_middleware(RateLimitMiddleware)

# Request context (request_id) — 마지막 등록 = 최외곽(가장 먼저 실행)
# 이후 모든 미들웨어/핸들러/로그가 request_id 를 갖도록 최외곽에 배치.
app.add_middleware(RequestContextMiddleware)

# Initialize database
initialize_tortoise(app)

# Include API routers
app.include_router(v1_routers)

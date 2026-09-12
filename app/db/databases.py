"""Database configuration module.

This module contains Tortoise ORM configuration and initialization
for the FastAPI application with modern Python patterns.
"""

from typing import Any

from fastapi import FastAPI
from tortoise import Tortoise
from tortoise.contrib.fastapi import register_tortoise

from app.core import config
from app.core.config import Config

# Tortoise ORM model modules
TORTOISE_APP_MODELS: list[str] = [
    "aerich.models",
    "app.models.accounts",
    "app.models.refresh_tokens",
    "app.models.profiles",
    "app.models.prescription_group",
    "app.models.medication",
    "app.models.medicine_info",
    "app.models.medicine_chunk",
    "app.models.medicine_ingredient",
    "app.models.lifestyle_guide",
    "app.models.daily_symptom_log",
    "app.models.challenge",
    "app.models.chat_sessions",
    "app.models.messages",
    "app.models.intake_log",
    "app.models.data_sync_log",
    "app.models.ocr_draft",
    "app.models.drug_recall",
]


# ── Tortoise ORM 설정 빌더 ────────────────────────────────────────────
# 흐름: config(DB 자격증명) -> asyncpg credentials 조립 -> DB_SSL 시 ssl 주입
#       -> Tortoise 설정 dict 반환
# DB_SSL=true(Neon 등 관리형 PG)면 asyncpg 에 ssl="require" 전달로 TLS 강제.
# 로컬/DEV Docker postgres 는 기본 False 라 평문 연결 유지(무영향).
def build_tortoise_orm(cfg: Config | None = None) -> dict[str, Any]:
    """Build the Tortoise ORM config dict from application settings.

    Assembles the asyncpg connection credentials and, when ``DB_SSL`` is
    enabled, injects an ``ssl="require"`` credential so managed Postgres
    providers (e.g. Neon) accept the TLS-only connection.

    Args:
        cfg: Application configuration instance. Defaults to the global
            ``config`` singleton when not provided.

    Returns:
        Tortoise ORM configuration dictionary consumed by
        ``register_tortoise`` and aerich.
    """
    settings = cfg or config

    credentials: dict[str, Any] = {
        "host": settings.DB_HOST,
        "port": settings.DB_PORT,
        "user": settings.DB_USER,
        "password": settings.DB_PASSWORD,
        "database": settings.DB_NAME,
        "timeout": settings.DB_CONNECT_TIMEOUT,
        "maxsize": settings.DB_CONNECTION_POOL_MAXSIZE,
    }
    if settings.DB_SSL:
        credentials["ssl"] = "require"

    return {
        "connections": {
            "default": {
                "engine": "tortoise.backends.asyncpg",
                "credentials": credentials,
            },
        },
        "apps": {
            "models": {
                "models": TORTOISE_APP_MODELS,
            },
        },
        "timezone": "Asia/Seoul",
    }


# aerich(pyproject.toml) 와 register_tortoise 가 참조하는 모듈 전역 설정.
TORTOISE_ORM: dict[str, Any] = build_tortoise_orm()


def initialize_tortoise(app: FastAPI) -> None:
    """Initialize Tortoise ORM with FastAPI application.

    Sets up database models and registers Tortoise ORM with the FastAPI app
    for automatic connection management and lifecycle handling.

    Args:
        app: FastAPI application instance to register with.
    """
    Tortoise.init_models(TORTOISE_APP_MODELS, "models")
    register_tortoise(app, config=TORTOISE_ORM)

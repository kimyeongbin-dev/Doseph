"""APScheduler configuration and FastAPI lifespan integration.

Registers cron jobs:
  - 00:05 KST: generate today's IntakeLog records
  - 00:10 KST: deactivate and soft-delete expired medications
  - 03:00 KST: sync MFDS drug-recall notices + dispatch user alerts
  - 03:30 KST: prune stale ocr_drafts (created_at < now - 24h)
"""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import FastAPI

from app.core.http_client import close_http_client
from app.workers.intake_log_worker import generate_today_intake_logs
from app.workers.medication_worker import expire_medications
from app.workers.ocr_cleanup_worker import prune_stale_ocr_drafts
from app.workers.recall_sync_worker import sync_drug_recalls

logger = logging.getLogger(__name__)

_KST = "Asia/Seoul"


@asynccontextmanager
async def scheduler_lifespan(_app: FastAPI) -> AsyncGenerator[None]:
    """Manage APScheduler lifecycle within FastAPI lifespan.

    Starts the scheduler on application startup and shuts it down on exit.

    Args:
        _app: FastAPI application instance (unused, required by lifespan protocol).

    Yields:
        None
    """
    scheduler = AsyncIOScheduler(timezone=_KST)
    scheduler.add_job(generate_today_intake_logs, "cron", hour=0, minute=5, id="generate_intake_logs")
    scheduler.add_job(expire_medications, "cron", hour=0, minute=10, id="expire_medications")
    scheduler.add_job(sync_drug_recalls, "cron", hour=3, minute=0, id="sync_drug_recalls")
    scheduler.add_job(prune_stale_ocr_drafts, "cron", hour=3, minute=30, id="prune_stale_ocr_drafts")
    scheduler.start()
    logger.info(
        "APScheduler started: generate_intake_logs@00:05, expire_medications@00:10, "
        "sync_drug_recalls@03:00, prune_stale_ocr_drafts@03:30 KST",
    )

    yield

    scheduler.shutdown(wait=False)
    # 공유 httpx 클라이언트 정리 — 커넥션·fd 누수 방지.
    await close_http_client()
    logger.info("APScheduler shutdown complete")

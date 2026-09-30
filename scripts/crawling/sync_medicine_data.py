"""Medicine data synchronization CLI script.

Entry point for full or incremental synchronization of drug data
from the Food and Drug Safety public API (data.go.kr)
into the medicine_info database table.

Usage:
    # Full sync (first-time setup)
    python -m scripts.crawling.sync_medicine_data --full

    # Incremental sync (monthly update)
    python -m scripts.crawling.sync_medicine_data

    # With custom API key
    python -m scripts.crawling.sync_medicine_data --api-key YOUR_KEY
"""

import argparse
import asyncio
import logging
import sys

from tortoise import Tortoise

from app.core.config import config
from app.db.databases import TORTOISE_ORM
from app.services.medicine_data_service import MedicineDataService

# ── 로깅 설정 ───────────────────────────────────────────────────────
logging.basicConfig(
  level=logging.INFO,
  format="[%(asctime)s] [%(levelname)s] [%(name)s:%(lineno)d] - %(message)s",
  datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


# ── CLI 인자 파싱 (--full: 전체 동기화, --api-key: API 키 직접 전달) ──


def parse_args() -> argparse.Namespace:
  """Parse command line arguments.

  Returns:
      Parsed argument namespace.
  """
  parser = argparse.ArgumentParser(
    description="Sync medicine data from public API to database",
  )
  parser.add_argument(
    "--full",
    action="store_true",
    help="Perform full sync (default: incremental)",
  )
  parser.add_argument(
    "--api-key",
    type=str,
    default=None,
    help="Public data API key (default: from .env)",
  )
  parser.add_argument(
    "--include-ingredients",
    action="store_true",
    help="Also sync medicine_ingredient table (Mcpn07 endpoint)",
  )
  parser.add_argument(
    "--ingredients-only",
    action="store_true",
    help="Skip medicine_info sync, run ONLY medicine_ingredient sync (Mcpn07).",
  )
  return parser.parse_args()


# ── 동기화 실행 (Tortoise ORM 초기화 -> Service 호출 -> 연결 종료) ────
# 흐름: DB 연결 -> MedicineDataService.sync() -> 결과 로그 -> DB 종료


async def run_sync(
  full_sync: bool,
  api_key: str,
  include_ingredients: bool,
  ingredients_only: bool,
) -> None:
  """Initialize DB connection and run sync operation.

  Args:
      full_sync: Whether to perform full or incremental sync.
      api_key: Public data API key for authentication.
      include_ingredients: If True, also sync medicine_ingredient (Mcpn07).
      ingredients_only: If True, skip medicine_info sync entirely and run
          ONLY medicine_ingredient sync. Implies include_ingredients=True.
  """
  await Tortoise.init(config=TORTOISE_ORM)
  logger.info("Database connection established")

  try:
    service = MedicineDataService(api_key=api_key)

    if not ingredients_only:
      stats = await service.sync(full_sync=full_sync)
      logger.info(
        "Sync result: fetched=%d, inserted=%d, updated=%d",
        stats["fetched"],
        stats["inserted"],
        stats["updated"],
      )

    if include_ingredients or ingredients_only:
      ing_stats = await service.sync_ingredients()
      logger.info(
        "Ingredient sync: fetched=%d, inserted=%d, updated=%d, skipped=%d",
        ing_stats["fetched"],
        ing_stats["inserted"],
        ing_stats["updated"],
        ing_stats["skipped"],
      )
  finally:
    await Tortoise.close_connections()
    logger.info("Database connection closed")


# ── 메인 진입점 (.env에서 API 키 로드 후 asyncio.run으로 실행) ───────


def main() -> None:
  """CLI entry point for medicine data synchronization."""
  args = parse_args()

  api_key = args.api_key or config.DATA_GO_KR_API_KEY
  if not api_key:
    logger.error("API key is required. Set DATA_GO_KR_API_KEY in .env or pass --api-key argument.")
    sys.exit(1)

  if args.ingredients_only:
    logger.info("Starting ingredient-only sync (skipping medicine_info)")
  else:
    sync_type = "full" if args.full else "incremental"
    logger.info("Starting %s medicine data sync", sync_type)

  asyncio.run(
    run_sync(
      full_sync=args.full,
      api_key=api_key,
      include_ingredients=args.include_ingredients,
      ingredients_only=args.ingredients_only,
    )
  )


if __name__ == "__main__":
  main()

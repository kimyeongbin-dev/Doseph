"""Medicine info raw XML 재파싱 CLI — API 호출 없이 기존 ee/ud/nb_doc_data 만 활용.

docs-private/PLAN_DRUG_DB_INGEST.md §7 — `MedicineInfo.precautions` (JSONB) /
``side_effects`` (JSONB list) / ``dosage`` (TEXT) 컬럼을 채우기 위한 1회성
스크립트. 모든 row 의 보존된 raw XML 을 다시 파싱해 새 컬럼을 갱신한다.
``efficacy`` 도 함께 재파싱되어 누락 없이 동기화된다.

API quota 0 — DB 만 접근. 멱등 — 재실행해도 결과 동일.

Usage:
    python -m scripts.crawling.reparse_medicine_docs
    python -m scripts.crawling.reparse_medicine_docs --batch-size 500
"""

import argparse
import asyncio
import logging

from tortoise import Tortoise

from app.db.databases import TORTOISE_ORM
from app.models.medicine_info import MedicineInfo
from app.services.medicine_doc_parser import (
    flatten_doc_plaintext,
    parse_nb_categories,
    parse_ud_plaintext,
)

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] [%(levelname)s] [%(name)s:%(lineno)d] - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Reparse medicine_info raw XML into structured columns (no API calls).",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=500,
        help="Rows per batch (default: 500)",
    )
    return parser.parse_args()


async def reparse_all(batch_size: int) -> tuple[int, int]:
    """모든 medicine_info row 의 raw XML 을 재파싱해 새 컬럼을 갱신한다.

    Returns:
        (processed, updated) — 처리한 row 수, 실제 컬럼 변경된 row 수.
    """
    total = await MedicineInfo.all().count()
    logger.info("Reparsing %d medicine_info rows (batch=%d)", total, batch_size)

    processed = 0
    updated = 0
    offset = 0

    while True:
        rows = await MedicineInfo.all().offset(offset).limit(batch_size)
        if not rows:
            break

        for row in rows:
            efficacy = flatten_doc_plaintext(row.ee_doc_data) or None
            dosage = parse_ud_plaintext(row.ud_doc_data) or None
            precautions, side_effects = parse_nb_categories(row.nb_doc_data)

            patch = {
                "efficacy": efficacy,
                "dosage": dosage,
                "precautions": precautions or None,
                "side_effects": side_effects or None,
            }
            # 변경 없는 row 는 update 호출 자체를 skip
            if (
                row.efficacy == efficacy
                and row.dosage == dosage
                and row.precautions == (precautions or None)
                and row.side_effects == (side_effects or None)
            ):
                processed += 1
                continue

            await MedicineInfo.filter(id=row.id).update(**patch)
            updated += 1
            processed += 1

        offset += batch_size
        logger.info("Progress: %d/%d processed, %d updated", processed, total, updated)

    return processed, updated


async def main_async(batch_size: int) -> None:
    await Tortoise.init(config=TORTOISE_ORM)
    try:
        processed, updated = await reparse_all(batch_size)
        logger.info("Reparse complete — processed=%d updated=%d", processed, updated)
    finally:
        await Tortoise.close_connections()


def main() -> None:
    args = parse_args()
    asyncio.run(main_async(args.batch_size))


if __name__ == "__main__":
    main()

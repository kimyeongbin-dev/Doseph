"""Drug-recall daily cron entrypoint (Phase 7).

Runs at **03:00 KST** via APScheduler. Two-stage flow:

1. ``DrugRecallService.sync()`` — pull MFDS recall data, apply 3-stage
   filter, upsert into ``drug_recalls``. Captures the start time so
   the diff step can isolate "rows added this run".
2. ``recall_notification_service.dispatch_for_recall(row)`` — for each
   newly inserted recall row (``created_at > sync_start``), notify
   every user whose ``medications`` overlaps with that recall. The
   notification dispatcher itself does cron-F3 dedup so a row never
   notifies twice for the same medication.

Logging contract: counts are emitted at INFO so the cron audit can
sanity-check daily totals.
"""

from __future__ import annotations

from datetime import UTC, datetime
import logging

from app.repositories.drug_recall_repository import DrugRecallRepository
from app.services.drug_recall_service import DrugRecallService
from app.services.recall_notification_service import dispatch_for_recall

logger = logging.getLogger(__name__)


# ── 일일 회수 동기화 + 자동 알림 (cron 03:00 KST) ───────────────────
# 흐름: sync_start 캡처 -> DrugRecallService.sync() -> diff_new_recalls
#       -> 각 신규 row 별 dispatch_for_recall


async def sync_drug_recalls() -> dict[str, int]:
  """Run the daily MFDS-recall sync + dispatch alerts for new rows.

  Returns:
      ``{"fetched": int, "inserted": int, "updated": int,
          "alerts": int}`` for cron audit.
  """
  sync_start = datetime.now(tz=UTC)
  logger.info("[RecallCron] start at %s", sync_start.isoformat())

  service = DrugRecallService()
  stats = await service.sync()

  # diff: 본 run 이 INSERT 한 row 만 알림 대상
  repo = DrugRecallRepository()
  new_rows = await repo.diff_new_recalls(since=sync_start)

  alerts = 0
  for row in new_rows:
    try:
      alerts += await dispatch_for_recall(row)
    except Exception:
      logger.exception(
        "[RecallCron] dispatch failed for item_seq=%s reason=%s",
        row.item_seq,
        row.recall_reason,
      )

  logger.info(
    "[RecallCron] done fetched=%d inserted=%d updated=%d alerts=%d",
    stats["fetched"],
    stats["inserted"],
    stats["updated"],
    alerts,
  )
  return {**stats, "alerts": alerts}

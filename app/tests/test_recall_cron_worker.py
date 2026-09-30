"""Recall sync cron worker 테스트 (Phase 7 Step 7).

검증 포인트:
- sync_drug_recalls: service.sync() + diff_new_recalls + dispatch_for_recall 의 호출 순서
- 알림 카운트 누적
- dispatch_for_recall 예외는 cron 전체를 망치지 않음
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.mark.asyncio
async def test_sync_drug_recalls_dispatches_alerts_for_new_rows() -> None:
  from app.workers import recall_sync_worker as worker

  new_rows = [MagicMock(item_seq="X", recall_reason="r", recall_command_date="20260401") for _ in range(2)]

  with (
    patch.object(worker, "DrugRecallService") as svc_cls,
    patch.object(worker, "DrugRecallRepository") as repo_cls,
    patch.object(worker, "dispatch_for_recall", new=AsyncMock(return_value=1)) as dispatch,
  ):
    svc_cls.return_value.sync = AsyncMock(return_value={"fetched": 30, "inserted": 2, "updated": 0})
    repo_cls.return_value.diff_new_recalls = AsyncMock(return_value=new_rows)

    result = await worker.sync_drug_recalls()

  assert result == {"fetched": 30, "inserted": 2, "updated": 0, "alerts": 2}
  assert dispatch.await_count == 2


@pytest.mark.asyncio
async def test_sync_drug_recalls_continues_on_dispatch_error() -> None:
  """알림 dispatch 가 한 row 에서 실패해도 나머지는 계속 처리."""
  from app.workers import recall_sync_worker as worker

  rows = [MagicMock(item_seq=f"X{i}", recall_reason="r", recall_command_date="20260401") for i in range(3)]

  async def dispatch_side_effect(row: Any) -> int:
    if row.item_seq == "X1":
      msg = "boom"
      raise RuntimeError(msg)
    return 1

  with (
    patch.object(worker, "DrugRecallService") as svc_cls,
    patch.object(worker, "DrugRecallRepository") as repo_cls,
    patch.object(worker, "dispatch_for_recall", new=AsyncMock(side_effect=dispatch_side_effect)),
  ):
    svc_cls.return_value.sync = AsyncMock(return_value={"fetched": 30, "inserted": 3, "updated": 0})
    repo_cls.return_value.diff_new_recalls = AsyncMock(return_value=rows)

    result = await worker.sync_drug_recalls()

  # X0, X2 만 성공
  assert result["alerts"] == 2

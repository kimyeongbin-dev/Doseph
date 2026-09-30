"""Data synchronization log model module.

This module defines the DataSyncLog model for tracking
public API data synchronization history and results.
"""

from tortoise import fields, models


class DataSyncLog(models.Model):
  """Data synchronization log for tracking API sync operations.

  Records each sync execution with metrics and status
  to support incremental update scheduling and debugging.

  Attributes:
      id: Auto-increment primary key.
      sync_type: Target data type for synchronization.
      sync_date: Execution timestamp of the sync operation.
      total_fetched: Total records fetched from the API.
      total_inserted: Number of newly inserted records.
      total_updated: Number of updated existing records.
      status: Sync result status (SUCCESS or FAILED).
      error_message: Error details when status is FAILED.
      created_at: Record creation timestamp.
  """

  # ── 동기화 실행 정보 ──────────────────────────────────────────────
  id = fields.BigIntField(pk=True)
  sync_type = fields.CharField(
    max_length=32,
    description="Sync target type (e.g. medicine_info)",
  )
  sync_date = fields.DatetimeField(
    description="Sync execution timestamp",
  )
  # ── 동기화 결과 통계 (수집/삽입/갱신 건수) ─────────────────────────
  total_fetched = fields.IntField(
    default=0,
    description="Total records fetched from API",
  )
  total_inserted = fields.IntField(
    default=0,
    description="Number of newly inserted records",
  )
  total_updated = fields.IntField(
    default=0,
    description="Number of updated existing records",
  )
  # ── 상태 및 에러 추적 ──────────────────────────────────────────────
  status = fields.CharField(
    max_length=16,
    description="Sync result status (SUCCESS / FAILED)",
  )
  error_message = fields.TextField(
    null=True,
    description="Error details when sync fails",
  )
  created_at = fields.DatetimeField(auto_now_add=True)

  class Meta:
    table = "data_sync_log"
    table_description = "Public API data synchronization history"
    indexes = (("sync_type", "status"),)

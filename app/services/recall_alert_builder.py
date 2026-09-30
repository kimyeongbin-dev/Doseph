"""Build recall alert / status DTOs from drug_recall rows (Phase 7 — §A.6.1).

Two pure builder functions used by ``medication_service``:

- ``build_alert(rows)`` — registration-time modal payload.
- ``build_status(rows)`` — my-page label payload (re-uses ``build_alert``
  for ``alert_payload`` so label clicks re-open the same modal).

Severity rule:
    Any row with ``sale_stop_yn="Y"`` → ``critical``. Otherwise
    ``advisory``. ``mixed`` (Y + N together) is not a separate tier —
    Y always wins (§D.5 시연 시나리오 회귀 가드).

Sorting:
    Items are returned in ``recall_command_date`` descending order so
    the most recent recall surfaces first inside the modal.
"""

from __future__ import annotations

from typing import Any

from app.dtos.recall import RecallAlertDTO, RecallAlertItemDTO, RecallStatusDTO

# ── 본문 템플릿 ──────────────────────────────────────────────────────


_CRITICAL_HEADER = "⚠️ 회수·판매중지 알림"
_CRITICAL_BODY = (
  "이 약은 식약처에서 회수·판매중지 명령된 의약품입니다. "
  "즉시 복용을 중단하고, 약을 받은 약국·병원에 문의해 환불 또는 교환을 받으세요."
)

_ADVISORY_HEADER = "회수 안내 (자율회수)"
_ADVISORY_BODY = (
  "이 약은 표시사항·포장 등 비치명적 사유로 자율 회수가 진행 중입니다. "
  "즉시 사용 중단은 필요하지 않습니다. 다음 약국 방문 시 박스를 함께 가져가시면 교환이 가능합니다."
)

_LABEL_CRITICAL = "⚠️ 회수·판매중지"
_LABEL_ADVISORY = "ℹ️ 회수 안내"  # noqa: RUF001 — 시연 라벨에 정보 아이콘 그대로 사용 (§D 노출 텍스트)

_REASON_SUMMARY_MAX_LEN = 60


# ── 내부 헬퍼 ────────────────────────────────────────────────────────


def _to_item(row: Any) -> RecallAlertItemDTO:
  """ORM-like row → DTO 항목 변환. None 필드는 빈 문자열로 정규화."""
  return RecallAlertItemDTO(
    item_seq=getattr(row, "item_seq", "") or "",
    product_name=getattr(row, "product_name", "") or "",
    entrps_name=getattr(row, "entrps_name", "") or "",
    recall_reason=getattr(row, "recall_reason", "") or "",
    recall_command_date=getattr(row, "recall_command_date", "") or "",
    sale_stop_yn=getattr(row, "sale_stop_yn", "") or "",
  )


def _has_critical(rows: list[Any]) -> bool:
  """Y 가 1건이라도 있으면 critical (mixed severity 우선규칙)."""
  return any((getattr(r, "sale_stop_yn", "") or "").upper() == "Y" for r in rows)


# ── 공개 API ─────────────────────────────────────────────────────────


def build_alert(rows: list[Any]) -> RecallAlertDTO | None:
  """Build the modal payload from a list of recall rows.

  Args:
      rows: Drug-recall ORM rows (or ORM-like Mock instances) matched
          for a single medication or for §D.5 mixed input.

  Returns:
      ``RecallAlertDTO`` populated with header/body/items, or ``None``
      if ``rows`` is empty. ``items`` is sorted by
      ``recall_command_date`` descending.
  """
  if not rows:
    return None

  items = sorted(
    (_to_item(r) for r in rows),
    key=lambda it: it.recall_command_date,
    reverse=True,
  )

  if _has_critical(rows):
    return RecallAlertDTO(
      severity="critical",
      header=_CRITICAL_HEADER,
      body=_CRITICAL_BODY,
      items=items,
    )
  return RecallAlertDTO(
    severity="advisory",
    header=_ADVISORY_HEADER,
    body=_ADVISORY_BODY,
    items=items,
  )


def build_status(rows: list[Any]) -> RecallStatusDTO | None:
  """Build the my-page label payload from a list of recall rows.

  Args:
      rows: Drug-recall ORM rows matched for one medication.

  Returns:
      ``RecallStatusDTO`` whose ``alert_payload`` is the same
      ``RecallAlertDTO`` that registration-time would emit, or
      ``None`` if ``rows`` is empty. The label fields use the
      strongest+latest row (Y > N, newest date).
  """
  alert = build_alert(rows)
  if alert is None:
    return None

  label_text = _LABEL_CRITICAL if alert.severity == "critical" else _LABEL_ADVISORY
  # `alert.items` 가 이미 최신순 정렬이라 첫 항목이 라벨 표시 기준.
  latest = alert.items[0]
  reason_short = latest.recall_reason[:_REASON_SUMMARY_MAX_LEN]

  return RecallStatusDTO(
    severity=alert.severity,
    label_text=label_text,
    recall_command_date=latest.recall_command_date,
    recall_reason_short=reason_short,
    alert_payload=alert,
  )

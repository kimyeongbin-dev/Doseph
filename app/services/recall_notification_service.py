"""Recall notification dispatcher (Phase 7).

Persists "회수 발생" 시스템 메시지 as ``ChatMessage`` rows with a
distinguishable ``metadata.kind="recall_alert"`` so the existing
chat-history UI / SSE plumbing can render them without schema changes.

Sender encoding:
    - ``sender_type=ASSISTANT`` (the model only has USER/ASSISTANT;
      no migration needed).
    - ``metadata.kind="recall_alert"`` separates these from regular
      assistant turns and gives FE a render hook.

Dedup strategy (cron-F3):
    - Each notification row stores ``recall_item_seq``,
      ``recall_command_date``, ``recall_reason`` and ``medication_id``
      in metadata.
    - Before insert, the service checks whether a row with the same
      ``(profile_id, recall_item_seq, recall_command_date,
      recall_reason, medication_id)`` already exists for the user's
      messages. If yes → skip.

Session resolution:
    - The service grabs the user's most recent ``ChatSession`` and writes there. If none exists, the alert is
      silently skipped with a warning log — recall alerts assume the
      user has at least one chat session.

F3 hook helper (PLAN §16.3.2):
    ``check_and_alert_on_medication_save`` is the single shared
    entrypoint for ``medication_service.create_medication`` and
    ``ocr_service._save_one_medication``. Both call sites collapse to
    a one-line invocation so the find_match + insert_alert sequence
    lives in exactly one place.
"""

from __future__ import annotations

from datetime import UTC, datetime
import logging
from typing import Any
from uuid import UUID

from tortoise.expressions import Q

from app.models.chat_sessions import ChatSession
from app.models.messages import ChatMessage, SenderType
from app.repositories.drug_recall_repository import DrugRecallRepository

logger = logging.getLogger(__name__)

# Metadata 에 노출되는 알림 종류 식별 키
RECALL_ALERT_KIND = "recall_alert"


def _format_recall_message(recall: Any, medication_name: str) -> str:
    """Render the user-facing alert text in Korean.

    The format is intentionally short so the chat UI can show it as a
    single bubble. Date `YYYYMMDD` → `YYYY-MM-DD` for readability.
    """
    raw_date = recall.recall_command_date or ""
    date_str = (
        f"{raw_date[:4]}-{raw_date[4:6]}-{raw_date[6:8]}" if len(raw_date) == 8 and raw_date.isdigit() else raw_date
    )
    reason = recall.recall_reason or "사유 미기재"
    return f"[안전 알림] {medication_name}이(가) 식약처에서 {reason}로 {date_str} 회수되었습니다."


async def _already_notified(
    *,
    profile_id: UUID,
    recall: Any,
    medication_id: UUID | None,
) -> bool:
    """Return True when this exact recall + medication pair has already
    produced a notification for this profile.
    """
    qs = ChatMessage.filter(
        session__profile_id=profile_id,
        metadata__kind=RECALL_ALERT_KIND,
        metadata__recall_item_seq=recall.item_seq,
        metadata__recall_command_date=recall.recall_command_date,
        metadata__recall_reason=recall.recall_reason,
    )
    if medication_id is not None:
        qs = qs.filter(metadata__medication_id=str(medication_id))
    return await qs.exists()


async def _resolve_target_session_id(profile_id: UUID) -> UUID | None:
    """Return the most recent live chat-session for this profile."""
    session = await ChatSession.filter(profile_id=profile_id).order_by("-created_at").first()
    return session.id if session else None


async def send_recall_alert(
    *,
    profile_id: UUID,
    recall: Any,
    medication: Any | None = None,
) -> ChatMessage | None:
    """Insert one recall-alert ``ChatMessage`` for the user.

    Args:
        profile_id: Receiver.
        recall: ``DrugRecall`` row (Tortoise model or Mock-equivalent).
        medication: Optional ``Medication`` row that triggered the
            alert. Used for ``medicine_name`` display + dedup key.

    Returns:
        The created ``ChatMessage`` row, or ``None`` if the alert was
        skipped (already sent / no chat session).
    """
    medication_id: UUID | None = getattr(medication, "id", None)
    medicine_name = getattr(medication, "medicine_name", None) or recall.product_name or "(이름 없음)"

    if await _already_notified(profile_id=profile_id, recall=recall, medication_id=medication_id):
        logger.info(
            "[RecallAlert] dedup hit profile=%s item_seq=%s reason=%s",
            profile_id,
            recall.item_seq,
            recall.recall_reason,
        )
        return None

    session_id = await _resolve_target_session_id(profile_id)
    if session_id is None:
        logger.warning("[RecallAlert] no active chat session for profile=%s — skip", profile_id)
        return None

    message = await ChatMessage.create(
        session_id=session_id,
        sender_type=SenderType.ASSISTANT,
        content=_format_recall_message(recall, medicine_name),
        metadata={
            "kind": RECALL_ALERT_KIND,
            "recall_item_seq": recall.item_seq,
            "recall_command_date": recall.recall_command_date,
            "recall_reason": recall.recall_reason,
            "medication_id": str(medication_id) if medication_id else None,
            "product_name": recall.product_name,
            "entrps_name": recall.entrps_name,
            "issued_at": datetime.now(tz=UTC).isoformat(),
        },
    )
    logger.info(
        "[RecallAlert] dispatched profile=%s item_seq=%s reason=%s",
        profile_id,
        recall.item_seq,
        recall.recall_reason,
    )
    return message


# ── Cron 진입점 ─────────────────────────────────────────────────────


async def dispatch_for_recall(recall: Any) -> int:
    """For one new recall row, send alerts to every affected user.

    Walks through all `medications.medicine_name` matches:
        1. exact `medicine_name == recall.product_name`
        2. medicine_info join: medicine_info.item_seq == recall.item_seq
           → medicine_name → medication match
    Both stages tolerate misses (S7 OCR-only entries are caught by
    stage 1 ILIKE).

    Returns:
        Number of alerts actually inserted (after dedup).
    """
    from app.models.medication import Medication
    from app.models.medicine_info import MedicineInfo

    candidate_names: set[str] = {recall.product_name} if recall.product_name else set()
    if recall.item_seq:
        rows = await MedicineInfo.filter(item_seq=recall.item_seq).all()
        for r in rows:
            if r.medicine_name:
                candidate_names.add(r.medicine_name)

    if not candidate_names:
        return 0

    name_filter = Q(medicine_name__in=candidate_names) | Q(medicine_name__icontains=recall.product_name)
    medications = await Medication.filter(name_filter).all()

    inserted = 0
    for med in medications:
        result = await send_recall_alert(
            profile_id=med.profile_id,
            recall=recall,
            medication=med,
        )
        if result is not None:
            inserted += 1
    return inserted


# ── F3 후크용 공용 헬퍼 (PLAN §16.3.2) ─────────────────────────────
# 흐름: drug_recall_repo.find_match -> 매칭되면 send_recall_alert 호출
#       -> 첫 매칭 row 반환 (None 이면 매칭 없음)
# 호출자: medication_service.create_medication / ocr_service._save_one_medication


async def check_and_alert_on_medication_save(
    medication: Any,
    drug_recall_repo: DrugRecallRepository | None = None,
) -> Any | None:
    """약품 등록 직후 회수 매칭 검사 + 시스템 알림 발송.

    `medication_service.create_medication` 와 `ocr_service._save_one_medication`
    양쪽에서 동일하게 호출하도록 추출된 공용 후크. 매칭된 회수가 여러 건이면
    각 row 마다 알림을 발송하지만, 호출자에게는 첫 번째 row 만 반환해
    `recall_warning` 응답 한 건을 만들 수 있게 한다.

    Implementation notes:
        - find_match 가 빈 리스트면 즉시 None 반환 (no DB write).
        - 알림 발송 자체는 `send_recall_alert` 의 dedup 로직이 처리하므로
          멱등 호출 안전. 호출자가 예외 격리 (try/except) 를 책임진다 —
          본 헬퍼는 의도적으로 raise 한다.

    Args:
        medication: Tortoise ``Medication`` instance freshly persisted.
        drug_recall_repo: Optional repository injection (테스트 친화).
            None 이면 기본 ``DrugRecallRepository()`` 인스턴스 사용.

    Returns:
        매칭된 첫 ``DrugRecall`` row 또는 매칭 없을 시 ``None``.
    """
    repo = drug_recall_repo or DrugRecallRepository()
    recalls = await repo.find_match(medication)
    if not recalls:
        return None

    profile_id = getattr(medication, "profile_id", None)
    for recall in recalls:
        await send_recall_alert(
            profile_id=profile_id,
            recall=recall,
            medication=medication,
        )
    logger.info(
        "[F3] recall match dispatched medication=%s name=%s recalls=%d",
        getattr(medication, "id", "?"),
        getattr(medication, "medicine_name", "?"),
        len(recalls),
    )
    return recalls[0]

"""OCR service — Producer 측 (FastAPI), DB 영속 저장 정책.

본 서비스는 HTTP 흐름의 thin layer 다:

- ``enqueue_ocr_task``: 업로드 bytes -> dedup 체크 -> ocr_drafts INSERT
  (또는 기존 활성 draft 재사용) -> RQ ``ai`` 큐에 enqueue -> draft_id 반환
- ``get_draft_data``: ocr_drafts SELECT -> ``OcrDraftPollResponse`` (단발 조회)
- ``stream_draft_states``: SSE 용 async generator — status 변화 시점마다 yield,
  terminal 도달 또는 max_seconds 초과 시 close
- ``list_active_drafts``: main 페이지 카드용 — 24h 안 미consume draft 리스트
- ``confirm_and_save``: ocr_drafts 의 consumed_at 을 atomic 으로 설정한 뒤
  Medication 영구 저장

OCR 자체 (CLOVA 호출 + 텍스트 정규화 + DB 매칭) 는 ai-worker 의
``ai_worker.domains.ocr.jobs.process_ocr_task`` 가 비동기로 처리하고
ocr_drafts 를 직접 UPDATE 한다. Redis 는 더 이상 결과 저장에 사용하지 않으며
RQ 큐 broker 로만 쓰인다.
"""

import asyncio
from collections.abc import AsyncIterator
from datetime import datetime
import hashlib
import json
import logging
import os
import time
from typing import Any
from uuid import UUID

from fastapi import UploadFile
from rq import Queue
from tortoise.transactions import in_transaction

from app.core.config import config
from app.core.redis_client import make_sync_redis
from app.dtos.ocr import (
  ConfirmMedicationRequest,
  ExtractedMedicine,
  OcrActiveDraftsResponse,
  OcrDraftPollResponse,
  OcrDraftStatus,
  OcrDraftSummary,
  OcrExtractResponse,
)
from app.models.medication import Medication
from app.models.ocr_draft import OcrDraft
from app.models.prescription_group import PrescriptionGroupSource
from app.repositories.ocr_draft_repository import OcrDraftRepository
from app.repositories.prescription_group_repository import PrescriptionGroupRepository
from app.services.recall_notification_service import check_and_alert_on_medication_save

logger = logging.getLogger(__name__)


def _first_dispensed_date(meds: list[ExtractedMedicine]) -> Any:
  """검수된 약품 list 에서 처방전 그룹 메타로 사용할 dispensed_date 1개를 추출.

  한 처방전 안의 약품들은 보통 같은 dispensed_date 를 가지므로 첫 번째
  non-null 값을 채택. 모두 NULL 이면 None (그룹의 dispensed_date 도 NULL).
  """
  for med in meds:
    if med.dispensed_date is not None:
      return med.dispensed_date
  return None


def _first_department(meds: list[ExtractedMedicine]) -> str | None:
  """그룹 메타 진료과 — 첫 번째 non-null 값 채택."""
  for med in meds:
    if med.department:
      return med.department
  return None


_OCR_JOB_REF = "ai_worker.domains.ocr.jobs.process_ocr_task"

# SSE long-polling 정책 — nginx default proxy_read_timeout(60s) 안에 close
_STREAM_MAX_SECONDS = 50
_STREAM_TICK_SECONDS = 0.5


class OCRService:
  """FastAPI 측 OCR thin service — RQ producer + DB 영속 + 결과 폴링."""

  def __init__(self, repository: OcrDraftRepository | None = None) -> None:
    # RQ enqueue 용 sync client. keepalive 일괄 적용. 결과 저장은 DB 가
    # 담당하므로 polling/delete 용 redis client 는 불필요.
    redis_url = os.environ.get("REDIS_URL", "redis://redis:6379")
    self._queue = Queue("ai", connection=make_sync_redis(redis_url))
    self._repository = repository or OcrDraftRepository()
    self._prescription_group_repository = PrescriptionGroupRepository()

  async def enqueue_ocr_task(self, file: UploadFile, profile_id: UUID | str) -> OcrExtractResponse:
    """업로드 bytes 를 ai-worker 로 enqueue 한다 (dedup 적용).

    같은 사용자 + 같은 image_hash + 미consume 인 draft 가 이미 있으면
    새 enqueue 없이 기존 draft_id 를 반환한다.

    Args:
        file: 사용자가 업로드한 처방전 이미지.
        profile_id: 업로드한 프로필 ID.

    Returns:
        ``OcrExtractResponse`` — draft_id 와 빈 medicines 리스트.
    """
    image_bytes = await file.read()
    image_hash = hashlib.sha256(image_bytes).hexdigest()
    filename = file.filename or "prescription.jpg"

    existing = await self._repository.find_active_by_hash(profile_id, image_hash)
    if existing is not None:
      return OcrExtractResponse(draft_id=str(existing.id), medicines=[])

    draft = await self._repository.create_pending(profile_id, image_hash, filename)
    self._queue.enqueue(_OCR_JOB_REF, image_bytes, filename, str(draft.id))
    return OcrExtractResponse(draft_id=str(draft.id), medicines=[])

  async def get_draft_data(
    self,
    draft_id: UUID | str,
    profile_id: UUID | str,
  ) -> OcrDraftPollResponse | None:
    """폴링 — DB 에서 draft 를 조회해 status + medicines 를 반환한다.

    Args:
        draft_id: enqueue 응답의 draft_id.
        profile_id: 요청자 프로필 ID (ownership 검증).

    Returns:
        ``OcrDraftPollResponse`` 또는 ``None`` (없거나 타인 소유).
    """
    draft = await self._get_owned_draft_or_audit(draft_id, profile_id, action="poll")
    if draft is None:
      return None
    return _to_poll_response(draft)

  async def _get_owned_draft_or_audit(
    self,
    draft_id: UUID | str,
    profile_id: UUID | str,
    *,
    action: str,
  ) -> OcrDraft | None:
    """소유 검증 + ownership 위반 시 audit 로깅.

    repository.get_by_id 가 None 을 반환할 때 (a) 진짜 없음 vs (b) 타인 소유
    인지 한 번 더 확인해, (b) 인 경우 warning 로깅한다. 응답 자체는 어느 쪽이든
    ``None`` — 외부에는 정보 누설 없이 404 로 응답하면서, 운영팀은 의심
    패턴을 추적할 수 있다.

    Args:
        draft_id: 조회 대상 draft ID.
        profile_id: 요청자 프로필 ID.
        action: 감사 로그에 남길 행위 라벨 (poll / stream / discard / confirm).

    Returns:
        본인 소유 draft 또는 ``None``.
    """
    draft = await self._repository.get_by_id(draft_id, profile_id)
    if draft is not None:
      return draft
    await self._audit_ownership_miss(draft_id, profile_id, action=action)
    return None

  async def _audit_ownership_miss(
    self,
    draft_id: UUID | str,
    profile_id: UUID | str,
    *,
    action: str,
  ) -> None:
    """타인 소유 draft 접근 시 warning 로깅. 진짜 없음/이미 consumed 인 경우는 침묵.

    Atomic update (mark_consumed) 의 affected=0 케이스 분류용으로도 호출된다.
    """
    foreign = await OcrDraft.filter(id=str(draft_id)).only("id", "profile_id").first()
    if foreign is not None and str(foreign.profile_id) != str(profile_id):
      logger.warning(
        "[OCR_OWNERSHIP] action=%s requester_profile=%s tried draft=%s owned_by=%s",
        action,
        profile_id,
        draft_id,
        foreign.profile_id,
      )

  async def stream_draft_states(
    self,
    draft_id: UUID | str,
    profile_id: UUID | str,
    *,
    max_seconds: int = _STREAM_MAX_SECONDS,
    tick_seconds: float = _STREAM_TICK_SECONDS,
  ) -> AsyncIterator[str]:
    r"""SSE 스트림 — draft 상태 변화 시점마다 event 를 yield 한다.

    - 첫 호출 시 현재 상태를 즉시 1회 yield (클라이언트가 stale 응답 안 받게).
    - 이후 ``tick_seconds`` 마다 DB 재조회, 상태가 바뀌면 yield.
    - terminal 상태 (ready / no_text / no_candidates / failed) 도달 시 close.
    - ``max_seconds`` 도달 시 timeout event 후 close — 클라이언트는 다시 연결.
    - draft 가 사라지면 error event 후 close.

    Args:
        draft_id: 스트리밍할 draft ID.
        profile_id: ownership 검증용.
        max_seconds: 단일 SSE 연결 최대 유지 시간.
        tick_seconds: DB 재조회 주기.

    Yields:
        ``"event: <name>\\ndata: <json>\\n\\n"`` 형식의 SSE chunk.
    """
    deadline = time.monotonic() + max_seconds
    last_status: OcrDraftStatus | None = None
    while True:
      draft = await self._get_owned_draft_or_audit(draft_id, profile_id, action="stream")
      if draft is None:
        yield _sse_event("error", {"detail": "Draft not found."})
        return

      poll = _to_poll_response(draft)
      if poll.status != last_status:
        yield _sse_event("update", poll.model_dump(mode="json"))
        last_status = poll.status

      if poll.status != OcrDraftStatus.PENDING:
        return
      if time.monotonic() >= deadline:
        yield _sse_event("timeout", {"status": poll.status.value})
        return
      await asyncio.sleep(tick_seconds)

  async def list_active_drafts(self, profile_id: UUID | str) -> OcrActiveDraftsResponse:
    """Main 페이지 카드용 — 사용자의 활성 draft 요약 목록.

    Args:
        profile_id: 요청자 프로필 ID.

    Returns:
        ``OcrActiveDraftsResponse`` — 빈 리스트일 수 있음 (초기 사용자 등).
    """
    drafts = await self._repository.list_active(profile_id)
    return OcrActiveDraftsResponse(drafts=[_to_summary(d) for d in drafts])

  async def discard_draft(self, draft_id: UUID | str, profile_id: UUID | str) -> bool:
    """사용자가 검수 화면에서 "다시 촬영" 등으로 draft 를 폐기 처리.

    ``consumed_at`` 을 설정해 active list 와 dedup 검색에서 제외시킨다
    (soft delete). row 자체는 24h 까지 보관 — 통계·감사용.

    Args:
        draft_id: 폐기할 draft ID.
        profile_id: 요청자 프로필 ID (ownership 검증).

    Returns:
        ``True`` 면 새로 폐기, ``False`` 면 이미 처리됨/없음/타인 소유.
    """
    consumed = await self._repository.mark_consumed(draft_id, profile_id)
    if not consumed:
      await self._audit_ownership_miss(draft_id, profile_id, action="discard")
    return consumed

  async def confirm_and_save(
    self,
    request: ConfirmMedicationRequest,
    profile_id: UUID | str,
  ) -> dict[str, Any]:
    """검수 완료된 약품을 DB 에 영구 저장하고 draft 를 consume 처리.

    Args:
        request: 검수된 약품 리스트 + draft_id.
        profile_id: 요청자 프로필 ID.

    Returns:
        ``{"status": "success", "message": str}``.

    Raises:
        ValueError: draft 가 이미 처리됐거나 만료·없음·타인 소유.
    """
    consumed = await self._repository.mark_consumed(request.draft_id, profile_id)
    if not consumed:
      await self._audit_ownership_miss(request.draft_id, profile_id, action="confirm")
      raise ValueError("이미 처리되었거나 만료된 처방전입니다. 새로 등록해주세요.")

    # 처방전 그룹 + medication bulk insert 트랜잭션 — OCR 한 호출 = 한 처방전
    # 이라는 도메인 의미를 모델 단에서 일관되게 보장.
    # 그룹 메타 (hospital_name / department / dispensed_date) 는 사용자가
    # OCR result 화면에서 입력한 값을 우선 사용 (request.hospital_name 등),
    # 미입력 시 medication list 의 첫 non-null 값으로 fallback.
    async with in_transaction():
      confirmed = list(request.confirmed_medicines)
      group_department = request.department or _first_department(confirmed)
      group_dispensed = _first_dispensed_date(confirmed)
      group = await self._prescription_group_repository.create(
        profile_id=profile_id,
        dispensed_date=group_dispensed,
        department=group_department,
        hospital_name=request.hospital_name,
        source=PrescriptionGroupSource.OCR,
      )
      saved = [await self._save_one_medication(med, profile_id, group_id=group.id) for med in confirmed]

    return {
      "status": "success",
      "message": f"{len(saved)}개의 약품이 성공적으로 저장되었습니다.",
    }

  async def _save_one_medication(
    self,
    med: ExtractedMedicine,
    profile_id: UUID | str,
    *,
    group_id: UUID,
  ) -> Medication:
    """확정된 약품 한 건을 ``Medication`` 으로 저장 (처방전 그룹 FK 채움)."""
    daily_count = med.daily_intake_count or 1
    total_days = med.total_intake_days or 1
    total_count = daily_count * total_days
    today = datetime.now(tz=config.TIMEZONE).date()
    medication = await Medication.create(
      profile_id=str(profile_id),
      prescription_group_id=group_id,
      medicine_name=med.medicine_name,
      department=med.department,
      category=med.category,
      dose_per_intake=med.dose_per_intake,
      intake_instruction=med.intake_instruction,
      daily_intake_count=daily_count,
      total_intake_days=total_days,
      intake_times=[],  # TODO: 복용 시간 설정 기능 (다음 sprint)
      total_intake_count=total_count,
      remaining_intake_count=total_count,
      start_date=med.dispensed_date or today,
      dispensed_date=med.dispensed_date,
      is_active=True,
    )

    # ── F3: OCR 확정 직후 회수 체크 (Phase 7, PLAN §16.3.2 헬퍼 위임) ──
    # OCR 경로는 medication_service 를 거치지 않으므로 동일 헬퍼를
    # 직접 호출해야 한다 (PLAN §16.3.1 우회 경로 가드).
    try:
      await check_and_alert_on_medication_save(medication)
    except Exception:
      logger.exception(
        "[F3-OCR] recall hook failed for medication=%s",
        getattr(medication, "id", "?"),
      )

    return medication


def _to_poll_response(draft: OcrDraft) -> OcrDraftPollResponse:
  """OcrDraft → 폴링 응답 DTO 매핑."""
  return OcrDraftPollResponse(
    draft_id=str(draft.id),
    status=OcrDraftStatus(draft.status),
    medicines=[ExtractedMedicine.model_validate(m) for m in (draft.medicines or [])],
  )


def _to_summary(draft: OcrDraft) -> OcrDraftSummary:
  """OcrDraft → main 카드 summary 매핑."""
  return OcrDraftSummary(
    draft_id=str(draft.id),
    status=OcrDraftStatus(draft.status),
    created_at=draft.created_at,
  )


def _sse_event(event_name: str, data: dict[str, Any]) -> str:
  r"""SSE 한 event 를 직렬화 — ``event:`` + ``data:`` + ``\n\n`` 종료."""
  payload = json.dumps(data, ensure_ascii=False, default=str)
  return f"event: {event_name}\ndata: {payload}\n\n"

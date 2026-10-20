"""OCR RQ jobs — FastAPI 가 ``ai`` 큐로 enqueue 하는 진입점.

본 모듈은 RQ task entry point 만 정의한다. 실제 비즈니스 로직은
도메인 안의 다른 모듈로 위임한다:

- 텍스트 정규화 → ``text_normalizer``
- DB 매칭 → ``medicine_matcher.search_candidates_in_open_db`` (Tortoise 가 이미 열린 상태)
- 결과 영속 저장 → ``ocr_drafts`` 테이블 UPDATE (Redis 미사용)

글자 읽기(OCR)는 브라우저가 기기 안에서 하고, 본 job 은 약 줄만 남긴 글자를
RQ payload 로 받는다. 사진은 서버에 오지 않는다.
draft_id 는 FastAPI 가 ``ocr_drafts`` 에 INSERT 하면서 만든 UUID 다 —
본 job 은 그 row 를 UPDATE 한다.

받은 글자는 화이트리스트를 통과했어도 사용자의 처방 내용이므로 로그에 남기지 않는다
(길이·draft_id 만 남긴다).
"""

import asyncio

from tortoise import Tortoise

from ai_worker.core.logger import get_logger
from ai_worker.domains.ocr.medicine_matcher import search_candidates_in_open_db
from ai_worker.domains.ocr.text_normalizer import clean_ocr_text, extract_medicine_candidates
from app.db.databases import TORTOISE_ORM
from app.dtos.ocr import ExtractedMedicine
from app.models.ocr_draft import OcrDraftStatusValue
from app.repositories.ocr_draft_repository import OcrDraftRepository

logger = get_logger(__name__)


def process_ocr_task(text: str, draft_id: str) -> bool:
  """[RQ Task] 브라우저가 보낸 약 줄 글자를 처리해 ``ocr_drafts`` 를 UPDATE 한다.

  Args:
      text: 기기에서 OCR 후 약 줄만 남긴 글자.
      draft_id: 사전에 INSERT 된 ``ocr_drafts.id`` (UUID 문자열).

  Returns:
      성공 시 ``True``, 실패 시 ``False``.
  """
  logger.info("Starting OCR task: draft_id=%s length=%d", draft_id, len(text))
  try:
    return _process_text(text, draft_id)
  except Exception:
    logger.exception("OCR task failed for %s", draft_id)
    _persist_terminal(draft_id, OcrDraftStatusValue.FAILED)
    return False


# ── OCR 텍스트 처리 ─────────────────────────────────────────────────────
# 흐름: 빈 텍스트 -> NO_TEXT
#       -> 정규화 -> 후보 추출 -> 후보 없음 -> NO_CANDIDATES
#       -> [Tortoise lifecycle] DB 매칭 -> ocr_drafts UPDATE
def _process_text(raw_text: str, draft_id: str) -> bool:
  """OCR 텍스트를 정규화·매칭해 ``ocr_drafts`` 를 UPDATE 한다."""
  if not raw_text.strip():
    logger.warning("No text received for draft %s", draft_id)
    _persist_terminal(draft_id, OcrDraftStatusValue.NO_TEXT)
    return False

  candidates = extract_medicine_candidates(clean_ocr_text(raw_text))
  if not candidates:
    logger.warning("No medicine candidates found in OCR text for draft %s", draft_id)
    _persist_terminal(draft_id, OcrDraftStatusValue.NO_CANDIDATES)
    return False

  matched = asyncio.run(_match_and_save(candidates, draft_id))
  logger.info(
    "OCR task complete for %s: %d candidates -> %d matched",
    draft_id,
    len(candidates),
    len(matched),
  )
  return True


async def _match_and_save(candidates: list[str], draft_id: str) -> list[ExtractedMedicine]:
  """Tortoise 한 번의 lifecycle 안에서 DB 매칭 + ocr_drafts UPDATE."""
  await Tortoise.init(config=TORTOISE_ORM)
  try:
    matched = await search_candidates_in_open_db(candidates)
    serialised = [_to_jsonable_dict(med) for med in matched]
    await OcrDraftRepository().update_result(draft_id, OcrDraftStatusValue.READY, serialised)
    return matched
  finally:
    await Tortoise.close_connections()


def _persist_terminal(draft_id: str, status: OcrDraftStatusValue) -> None:
  """Terminal status (NO_TEXT / NO_CANDIDATES / FAILED) 를 DB 에 기록."""
  asyncio.run(_update_status_only(draft_id, status))


async def _update_status_only(draft_id: str, status: OcrDraftStatusValue) -> None:
  """Terminal failure 의 lifecycle — status + consumed_at 함께 set 해 자동 롤백.

  실패 draft 가 사용자 카드(activeDrafts)에 누적되지 않도록 ai-worker 가 그
  자리에서 ``consumed_at`` 도 채운다. 24h cron 이 hard delete 하기 전까지
  DB 에는 남지만, ``consumed_at IS NULL`` 게이트로 모든 활성 조회에서 제외된다.
  """
  await Tortoise.init(config=TORTOISE_ORM)
  try:
    await OcrDraftRepository().mark_terminal_failure(draft_id, status)
  finally:
    await Tortoise.close_connections()


def _to_jsonable_dict(med: ExtractedMedicine) -> dict[str, object]:
  """ExtractedMedicine -> JSONField 직렬화 가능한 dict (date -> ISO 문자열)."""
  return med.model_dump(mode="json")

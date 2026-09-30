"""OCR RQ jobs — FastAPI 가 ``ai`` 큐로 enqueue 하는 진입점.

본 모듈은 RQ task entry point 만 정의한다. 실제 비즈니스 로직은
도메인 안의 다른 모듈로 위임한다:

- CLOVA OCR 호출 → ``text_extractor``
- 텍스트 정규화 → ``text_normalizer``
- DB 매칭 → ``medicine_matcher.search_candidates_in_open_db`` (Tortoise 가 이미 열린 상태)
- 결과 영속 저장 → ``ocr_drafts`` 테이블 UPDATE (Redis 미사용)

흐름: CLOVA OCR -> 텍스트 정규화 -> 후보 추출
       -> [Tortoise lifecycle] DB 매칭 -> ocr_drafts UPDATE
       (CLOVA·정규화 단계는 sync, DB 단계는 한 번의 init/close 로 묶음)

이미지는 디스크에 저장하지 않고 RQ payload 의 bytes 로 직접 받는다.
draft_id 는 FastAPI 가 ``ocr_drafts`` 에 INSERT 하면서 만든 UUID 다 —
본 job 은 그 row 를 UPDATE 한다.
"""

import asyncio

from tortoise import Tortoise

from ai_worker.core.logger import get_logger
from ai_worker.domains.ocr.medicine_matcher import search_candidates_in_open_db
from ai_worker.domains.ocr.text_extractor import extract_text_from_image_bytes
from ai_worker.domains.ocr.text_normalizer import clean_ocr_text, extract_medicine_candidates
from app.db.databases import TORTOISE_ORM
from app.dtos.ocr import ExtractedMedicine
from app.models.ocr_draft import OcrDraftStatusValue
from app.repositories.ocr_draft_repository import OcrDraftRepository

logger = get_logger(__name__)


def process_ocr_task(image_bytes: bytes, filename: str, draft_id: str) -> bool:
  """[RQ Task] 처방전 이미지 한 장을 처리해 ``ocr_drafts`` 를 UPDATE 한다.

  Args:
      image_bytes: 업로드된 처방전 이미지의 raw bytes.
      filename: 원본 파일명 — CLOVA OCR payload 에 전달.
      draft_id: 사전에 INSERT 된 ``ocr_drafts.id`` (UUID 문자열).

  Returns:
      성공 시 ``True``, 실패 시 ``False``.
  """
  logger.info("Starting OCR task: filename=%s draft_id=%s size=%d", filename, draft_id, len(image_bytes))
  try:
    return _run_pipeline(image_bytes, filename, draft_id)
  except Exception:
    logger.exception("OCR task failed for %s", draft_id)
    _persist_terminal(draft_id, OcrDraftStatusValue.FAILED)
    return False


def _run_pipeline(image_bytes: bytes, filename: str, draft_id: str) -> bool:
  """Sync 단계 (CLOVA + normalize) 후 DB 단계는 한 lifecycle 로 묶어 처리."""
  raw_text = extract_text_from_image_bytes(image_bytes, filename)
  if not raw_text.strip():
    logger.warning("No text extracted from image: %s", filename)
    _persist_terminal(draft_id, OcrDraftStatusValue.NO_TEXT)
    return False

  candidates = extract_medicine_candidates(clean_ocr_text(raw_text))
  if not candidates:
    logger.warning("No medicine candidates found in OCR text")
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


def _to_jsonable_dict(med: ExtractedMedicine) -> dict:
  """ExtractedMedicine -> JSONField 직렬화 가능한 dict (date -> ISO 문자열)."""
  return med.model_dump(mode="json")

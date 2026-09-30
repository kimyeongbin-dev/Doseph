"""OCR draft cleanup worker — 24h 경과 row hard delete.

APScheduler 가 KST 03:30 (저트래픽) 에 1회 호출. ``ocr_drafts`` 테이블의
``created_at < NOW() - 24h`` row 를 정리해 디스크/인덱스 비대화를 막고,
list_active / dedup 검색이 항상 살아있는 row 만 보도록 유지한다.

cleanup 정책:
- consume 여부 무관 (consumed 된 row 도 24h 면 감사 의미가 약해짐)
- soft delete 가 아닌 hard delete (해당 테이블에 FK 가 들어오지 않음)
"""

import logging

from app.repositories.ocr_draft_repository import OcrDraftRepository

logger = logging.getLogger(__name__)


# ── OCR draft 24h 정리 작업 ────────────────────────────────────────────
# 흐름: cutoff 계산 -> stale row 일괄 DELETE -> 처리 row 수 로깅
async def prune_stale_ocr_drafts() -> None:
  """24h 경과 ocr_drafts row 를 한 번에 삭제하고 결과를 로깅한다.

  Repository 가 단일 ``DELETE WHERE created_at < cutoff`` 로 처리하므로
  부분 실패가 없다. 운영 디스크/인덱스 부담을 일정하게 유지한다.
  """
  repository = OcrDraftRepository()
  deleted = await repository.delete_stale(max_age_hours=24)
  logger.info("[OCR_CLEANUP] stale draft 정리 완료 deleted=%d", deleted)

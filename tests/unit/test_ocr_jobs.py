"""Unit tests for ai-worker OCR jobs — terminal failure 시 자동 consumed_at 롤백.

docs-private/PLAN_OCR_DRAFT.md §A — ai-worker 가 terminal failure 도달 시 consumed_at 을
함께 설정하여 DB 정합성 자체로 실패 draft 를 활성 목록에서 자동 제외한다.
"""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.models.ocr_draft import OcrDraftStatusValue
from app.repositories.ocr_draft_repository import OcrDraftRepository

# ── ai-worker 진입 (process_ocr_task) — terminal 분기별 자동 consume 검증 ──


class TestProcessOcrTaskTerminalRollback:
    """process_ocr_task 의 terminal failure 3분기에서 mark_terminal_failure 호출 검증."""

    @pytest.fixture
    def draft_id(self) -> str:
        return str(uuid4())

    def test_no_text_calls_mark_terminal_failure(self, draft_id: str) -> None:
        """raw_text 가 빈 문자열이면 NO_TEXT + consumed_at 자동 설정되어야 한다."""
        mock_repo = MagicMock()
        mock_repo.mark_terminal_failure = AsyncMock()
        mock_repo.update_result = AsyncMock()

        with (
            patch("ai_worker.domains.ocr.jobs.extract_text_from_image_bytes", return_value=""),
            patch("ai_worker.domains.ocr.jobs.Tortoise") as mock_tortoise,
            patch("ai_worker.domains.ocr.jobs.OcrDraftRepository", return_value=mock_repo),
        ):
            mock_tortoise.init = AsyncMock()
            mock_tortoise.close_connections = AsyncMock()

            from ai_worker.domains.ocr.jobs import process_ocr_task

            result = process_ocr_task(b"image-bytes", "rx.jpg", draft_id)

        assert result is False
        mock_repo.mark_terminal_failure.assert_awaited_once_with(draft_id, OcrDraftStatusValue.NO_TEXT)
        mock_repo.update_result.assert_not_awaited()

    def test_no_candidates_calls_mark_terminal_failure(self, draft_id: str) -> None:
        """후보 추출 결과가 빈 리스트면 NO_CANDIDATES + consumed_at 자동 설정."""
        mock_repo = MagicMock()
        mock_repo.mark_terminal_failure = AsyncMock()
        mock_repo.update_result = AsyncMock()

        with (
            patch(
                "ai_worker.domains.ocr.jobs.extract_text_from_image_bytes",
                return_value="처방전 텍스트",
            ),
            patch("ai_worker.domains.ocr.jobs.clean_ocr_text", return_value="정규화"),
            patch("ai_worker.domains.ocr.jobs.extract_medicine_candidates", return_value=[]),
            patch("ai_worker.domains.ocr.jobs.Tortoise") as mock_tortoise,
            patch("ai_worker.domains.ocr.jobs.OcrDraftRepository", return_value=mock_repo),
        ):
            mock_tortoise.init = AsyncMock()
            mock_tortoise.close_connections = AsyncMock()

            from ai_worker.domains.ocr.jobs import process_ocr_task

            result = process_ocr_task(b"image-bytes", "rx.jpg", draft_id)

        assert result is False
        mock_repo.mark_terminal_failure.assert_awaited_once_with(draft_id, OcrDraftStatusValue.NO_CANDIDATES)
        mock_repo.update_result.assert_not_awaited()

    def test_failed_calls_mark_terminal_failure(self, draft_id: str) -> None:
        """파이프라인 어느 단계든 예외 발생 시 FAILED + consumed_at 자동 설정."""
        mock_repo = MagicMock()
        mock_repo.mark_terminal_failure = AsyncMock()

        with (
            patch(
                "ai_worker.domains.ocr.jobs.extract_text_from_image_bytes",
                side_effect=RuntimeError("CLOVA OCR boom"),
            ),
            patch("ai_worker.domains.ocr.jobs.Tortoise") as mock_tortoise,
            patch("ai_worker.domains.ocr.jobs.OcrDraftRepository", return_value=mock_repo),
        ):
            mock_tortoise.init = AsyncMock()
            mock_tortoise.close_connections = AsyncMock()

            from ai_worker.domains.ocr.jobs import process_ocr_task

            result = process_ocr_task(b"image-bytes", "rx.jpg", draft_id)

        assert result is False
        mock_repo.mark_terminal_failure.assert_awaited_once_with(draft_id, OcrDraftStatusValue.FAILED)

    def test_ready_keeps_update_result_path(self, draft_id: str) -> None:
        """정상 처리 흐름에서는 update_result 만 호출되고 mark_terminal_failure 는 호출되지 않는다."""
        mock_repo = MagicMock()
        mock_repo.update_result = AsyncMock()
        mock_repo.mark_terminal_failure = AsyncMock()

        with (
            patch(
                "ai_worker.domains.ocr.jobs.extract_text_from_image_bytes",
                return_value="처방전 텍스트",
            ),
            patch("ai_worker.domains.ocr.jobs.clean_ocr_text", return_value="정규화"),
            patch(
                "ai_worker.domains.ocr.jobs.extract_medicine_candidates",
                return_value=["타이레놀"],
            ),
            patch(
                "ai_worker.domains.ocr.jobs.search_candidates_in_open_db",
                new=AsyncMock(return_value=[]),
            ),
            patch("ai_worker.domains.ocr.jobs.Tortoise") as mock_tortoise,
            patch("ai_worker.domains.ocr.jobs.OcrDraftRepository", return_value=mock_repo),
        ):
            mock_tortoise.init = AsyncMock()
            mock_tortoise.close_connections = AsyncMock()

            from ai_worker.domains.ocr.jobs import process_ocr_task

            result = process_ocr_task(b"image-bytes", "rx.jpg", draft_id)

        assert result is True
        mock_repo.update_result.assert_awaited_once()
        called_args = mock_repo.update_result.await_args
        assert called_args.args[1] == OcrDraftStatusValue.READY
        mock_repo.mark_terminal_failure.assert_not_awaited()


# ── Repository 단위 — mark_terminal_failure 가 status + consumed_at 함께 갱신 ──


class TestMarkTerminalFailure:
    """OcrDraftRepository.mark_terminal_failure 단위 테스트.

    OcrDraft.filter(...).update(...) 의 인자에 status, medicines=[], processed_at,
    consumed_at 이 모두 포함되어야 한다.
    """

    @pytest.fixture
    def repository(self) -> OcrDraftRepository:
        return OcrDraftRepository()

    async def test_sets_status_medicines_processed_at_and_consumed_at(
        self,
        repository: OcrDraftRepository,
    ) -> None:
        draft_id = str(uuid4())
        with patch("app.repositories.ocr_draft_repository.OcrDraft") as mock_model:
            mock_query = MagicMock()
            mock_query.update = AsyncMock(return_value=1)
            mock_model.filter.return_value = mock_query

            await repository.mark_terminal_failure(draft_id, OcrDraftStatusValue.NO_CANDIDATES)

            mock_model.filter.assert_called_once_with(id=draft_id)
            update_kwargs = mock_query.update.await_args.kwargs
            assert update_kwargs["status"] == OcrDraftStatusValue.NO_CANDIDATES.value
            assert update_kwargs["medicines"] == []
            assert isinstance(update_kwargs["processed_at"], datetime)
            assert isinstance(update_kwargs["consumed_at"], datetime)

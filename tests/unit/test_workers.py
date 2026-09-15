"""Unit tests for batch worker functions — intake_log_worker and medication_worker."""

from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch


class TestGenerateTodayIntakeLogs:
    """오늘의 IntakeLog 자동 생성 배치 테스트."""

    async def test_creates_logs_for_each_intake_time(self) -> None:
        """활성 처방전의 각 intake_time마다 IntakeLog가 생성되어야 한다."""
        mock_medication = MagicMock()
        mock_medication.id = "med-uuid"
        mock_medication.profile_id = "profile-uuid"
        mock_medication.intake_times = ["08:00", "13:00", "21:00"]

        with (
            patch("app.workers.intake_log_worker.Medication") as mock_med_model,
            patch("app.workers.intake_log_worker.IntakeLog") as mock_log_model,
            patch("app.workers.intake_log_worker.date") as mock_date,
        ):
            mock_date.today.return_value = date(2026, 4, 18)
            mock_med_model.filter.return_value.all = AsyncMock(return_value=[mock_medication])
            mock_log_model.get_or_create = AsyncMock(return_value=(MagicMock(), True))

            from app.workers.intake_log_worker import generate_today_intake_logs

            await generate_today_intake_logs()

            assert mock_log_model.get_or_create.call_count == 3

    async def test_skips_inactive_medications(self) -> None:
        """비활성 처방전은 IntakeLog를 생성하지 않아야 한다."""
        with (
            patch("app.workers.intake_log_worker.Medication") as mock_med_model,
            patch("app.workers.intake_log_worker.IntakeLog"),
            patch("app.workers.intake_log_worker.date"),
        ):
            mock_med_model.filter.return_value.all = AsyncMock(return_value=[])

            from app.workers.intake_log_worker import generate_today_intake_logs

            await generate_today_intake_logs()

            mock_med_model.filter.assert_called_once_with(is_active=True)

    async def test_idempotent_on_rerun(self) -> None:
        """배치 재실행 시 중복 생성 없이 get_or_create를 사용해야 한다."""
        mock_medication = MagicMock()
        mock_medication.id = "med-uuid"
        mock_medication.profile_id = "profile-uuid"
        mock_medication.intake_times = ["08:00"]

        with (
            patch("app.workers.intake_log_worker.Medication") as mock_med_model,
            patch("app.workers.intake_log_worker.IntakeLog") as mock_log_model,
            patch("app.workers.intake_log_worker.date") as mock_date,
        ):
            mock_date.today.return_value = date(2026, 4, 18)
            mock_med_model.filter.return_value.all = AsyncMock(return_value=[mock_medication])
            mock_log_model.get_or_create = AsyncMock(return_value=(MagicMock(), False))

            from app.workers.intake_log_worker import generate_today_intake_logs

            await generate_today_intake_logs()

            # get_or_create가 호출되었는지 확인 (False = 이미 존재, 중복 없음)
            mock_log_model.get_or_create.assert_called_once()


class TestExpireMedications:
    """처방전 자동 소멸 배치 테스트."""

    async def test_deactivates_medications_past_end_date(self) -> None:
        """end_date가 지난 활성 처방전은 is_active=False가 되어야 한다."""
        mock_medication = MagicMock()
        mock_medication.save = AsyncMock()

        with (
            patch("app.workers.medication_worker.Medication") as mock_med_model,
            patch("app.workers.medication_worker.datetime") as mock_dt,
        ):
            mock_dt.now.return_value.date.return_value = date(2026, 4, 18)
            mock_med_model.filter.return_value.all = AsyncMock(return_value=[mock_medication])
            mock_med_model.filter.return_value.delete = AsyncMock(return_value=0)

            from app.workers.medication_worker import expire_medications

            await expire_medications()

            assert mock_medication.is_active is False
            mock_medication.save.assert_called()

    async def test_deletes_medications_past_expiration_date(self) -> None:
        """expiration_date 가 지난 처방전은 **행 자체가 삭제**되어야 한다.

        ⚠️ 2026-09-15(QA-01): 이 배치는 ``deleted_at=now()`` 로 장부만 남기던
        soft delete 였다. 삭제 의미론이 hard delete 로 통일되면서 계약이 바뀌었다 —
        "지운 표시를 했는가"가 아니라 **"지웠는가"**를 묻는다.
        """
        with (
            patch("app.workers.medication_worker.Medication") as mock_med_model,
            patch("app.workers.medication_worker.datetime") as mock_dt,
        ):
            mock_dt.now.return_value.date.return_value = date(2026, 4, 18)
            mock_med_model.filter.return_value.all = AsyncMock(return_value=[])
            mock_med_model.filter.return_value.delete = AsyncMock(return_value=3)

            from app.workers.medication_worker import expire_medications

            await expire_medications()

            # pass 2 가 expiration_date 조건으로 delete() 를 호출했는가
            mock_med_model.filter.assert_any_call(
                expiration_date__lt=date(2026, 4, 18),
                expiration_date__isnull=False,
            )
            mock_med_model.filter.return_value.delete.assert_awaited_once()

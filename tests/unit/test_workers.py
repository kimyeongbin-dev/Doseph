"""Unit tests for batch worker functions — intake_log_worker and medication_worker."""

from datetime import date, timedelta
import logging
from unittest.mock import AsyncMock, MagicMock, patch

from app.core import config


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

    async def test_delete_cutoff_subtracts_the_grace_period(self) -> None:
        """pass 2 의 삭제 기준일은 **오늘이 아니라 오늘 - 유예일수**여야 한다.

        ⚠️ 이 테스트가 보는 것은 **질의의 모양**뿐이다. "행이 실제로 남았는가"는
        mock 으로 알 수 없어 ``app/tests/db/test_db_medication_purge.py`` 가 본다.
        여기서는 **부호가 거꾸로면(오늘 + 7일) 즉시 드러나게** 하는 역할만 한다.

        경위: QA-01 에서 soft delete 가 폐지되며 이 배치가 실제 삭제가 됐고,
        QA-29 가 그 위에 유예기간을 얹었다.
        """
        today = date(2026, 4, 18)
        expected_cutoff = today - timedelta(days=config.MEDICATION_PURGE_GRACE_DAYS)

        with patch("app.workers.medication_worker.Medication") as mock_med_model:
            mock_med_model.filter.return_value.all = AsyncMock(return_value=[])
            mock_med_model.filter.return_value.delete = AsyncMock(return_value=3)

            from app.workers.medication_worker import expire_medications

            await expire_medications(today=today)

            mock_med_model.filter.assert_any_call(
                expiration_date__lt=expected_cutoff,
                expiration_date__isnull=False,
            )
            assert expected_cutoff < today, "유예를 더하고 있다 — 부호가 거꾸로다"
            mock_med_model.filter.return_value.delete.assert_awaited_once()

    async def test_logs_deletion_receipt_without_personal_data(self, caplog) -> None:
        """삭제 영수증(tombstone)은 건수·사유·기준일을 남기고 **개인정보는 안 남긴다**.

        배치가 사용자 개입 없이 지우므로, 나중에 "무엇이 왜 사라졌나"를 물을 수
        있어야 한다. 동시에 영수증에 약품명이 들어가면 그건 영수증이 아니라
        백업이고 "지웠다"는 말이 거짓이 된다(로깅 규칙 §9-4).

        ⚠️ ``caplog`` 은 루트 logger 에 핸들러를 붙이는데, 우리 앱 logger 는
        ``propagate = False`` 다(``app/core/logger.py``). 그래서 로그가 콘솔에
        멀쩡히 찍히는데도 ``caplog.text`` 는 비어 있다. 핸들러를 **그 logger 에
        직접** 붙여야 잡힌다.
        """
        secret_name = "타이레놀정500mg"
        worker_logger = logging.getLogger("app.workers.medication_worker")
        worker_logger.addHandler(caplog.handler)

        try:
            with (
                caplog.at_level(logging.INFO, logger="app.workers.medication_worker"),
                patch("app.workers.medication_worker.Medication") as mock_med_model,
            ):
                mock_medication = MagicMock()
                mock_medication.save = AsyncMock()
                mock_medication.medicine_name = secret_name
                mock_med_model.filter.return_value.all = AsyncMock(return_value=[mock_medication])
                mock_med_model.filter.return_value.delete = AsyncMock(return_value=3)

                from app.workers.medication_worker import expire_medications

                await expire_medications(today=date(2026, 4, 18))
        finally:
            worker_logger.removeHandler(caplog.handler)

        assert "deleted=3" in caplog.text, "몇 건을 지웠는지 남지 않았다"
        assert "reason=batch_expiry" in caplog.text, "왜 지웠는지 남지 않았다"
        assert f"grace_days={config.MEDICATION_PURGE_GRACE_DAYS}" in caplog.text
        assert secret_name not in caplog.text, "영수증에 약품명이 들어갔다 — 개인정보 유출"

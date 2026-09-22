"""Daily symptom log repository module.

This module provides data access layer for the daily_symptom_logs table,
handling creation and retrieval of user-reported symptom entries.
"""

from datetime import date, datetime, timedelta
from uuid import UUID, uuid4

from app.core import config
from app.models.daily_symptom_log import DailySymptomLog


class DailySymptomLogRepository:
    """Daily symptom log database repository."""

    async def upsert(
        self,
        profile_id: UUID,
        log_date: date,
        symptoms: list[str],
        note: str | None = None,
    ) -> DailySymptomLog:
        """Create or update the daily symptom log for (profile_id, log_date).

        증상 로그는 사용자의 그 날 신체 상태로 (profile_id, log_date) 단위 1건만
        있어야 정합성 유지. 같은 키의 row 가 이미 존재하면 symptoms / note 를
        교체하고, 없으면 새로 생성한다. 멱등성 — 같은 입력 반복 호출 안전.

        Args:
            profile_id: Owner profile UUID.
            log_date: Date of the symptom report.
            symptoms: List of reported symptom strings (replaces existing).
            note: Optional free-text note (replaces existing; null 가능).

        Returns:
            DailySymptomLog: Upserted log instance.
        """
        existing = (
            await DailySymptomLog.filter(profile_id=profile_id, log_date=log_date).order_by("-created_at").first()
        )
        if existing:
            existing.symptoms = symptoms
            existing.note = note
            await existing.save(update_fields=["symptoms", "note"])
            return existing
        return await DailySymptomLog.create(
            id=uuid4(),
            profile_id=profile_id,
            log_date=log_date,
            symptoms=symptoms,
            note=note,
        )

    # 하위 호환 — 기존 호출지가 있을 수 있어 alias 유지. 신규 코드는 upsert 사용.
    async def create(
        self,
        profile_id: UUID,
        log_date: date,
        symptoms: list[str],
        note: str | None = None,
    ) -> DailySymptomLog:
        """Insert one daily symptom log row."""
        return await self.upsert(profile_id, log_date, symptoms, note)

    async def get_recent_by_profile(
        self,
        profile_id: UUID,
        days: int,
    ) -> list[DailySymptomLog]:
        """Get symptom logs for the past N days for a profile.

        Args:
            profile_id: Profile UUID.
            days: Number of days to look back from today.

        Returns:
            list[DailySymptomLog]: Logs ordered newest first.
        """
        cutoff = datetime.now(tz=config.TIMEZONE).date() - timedelta(days=days)
        return (
            await DailySymptomLog
            .filter(
                profile_id=profile_id,
                log_date__gte=cutoff,
            )
            .order_by("-log_date")
            .all()
        )

    async def bulk_delete_by_profile(self, profile_id: UUID) -> int:
        """프로필의 모든 daily symptom log 일괄 hard-delete.

        Profile cascade 삭제 흐름의 일부로 호출된다.

        Args:
            profile_id: 대상 프로필 UUID.

        Returns:
            삭제된 row 수.
        """
        return await DailySymptomLog.filter(profile_id=profile_id).delete()

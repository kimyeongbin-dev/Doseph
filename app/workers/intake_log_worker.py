"""Intake log batch worker module.

Generates today's IntakeLog records from active medications at 00:05 KST.
Uses get_or_create for idempotency — safe to re-run.
"""

from datetime import date, time
import logging
from uuid import uuid4

from app.models.intake_log import IntakeLog
from app.models.medication import Medication

logger = logging.getLogger(__name__)


async def generate_today_intake_logs() -> None:
    """Generate IntakeLog records for all active medications for today.

    Fetches all active (non-deleted) medications and creates one IntakeLog
    per scheduled intake_time using get_or_create to prevent duplicates.
    """
    today = date.today()
    medications = await Medication.filter(is_active=True).all()

    created_count = 0
    skipped_count = 0

    for medication in medications:
        for time_str in medication.intake_times:
            scheduled_time = time.fromisoformat(time_str)
            _, created = await IntakeLog.get_or_create(
                medication_id=medication.id,
                profile_id=medication.profile_id,
                scheduled_date=today,
                scheduled_time=scheduled_time,
                defaults={
                    "id": uuid4(),
                    "intake_status": "SCHEDULED",
                },
            )
            if created:
                created_count += 1
            else:
                skipped_count += 1

    logger.info(
        "generate_today_intake_logs completed: date=%s created=%d skipped=%d",
        today,
        created_count,
        skipped_count,
    )

"""Intake log model module.

This module defines the IntakeLog model for tracking medication intake schedules
and completion status.
"""

from tortoise import fields, models


class IntakeLog(models.Model):
    """Intake log model for tracking medication intake.

    This model tracks scheduled medication intake times and completion status.
    Profile ID is denormalized for query performance optimization.

    Attributes:
        id: Primary key UUID.
        medication: Foreign key to Medication model.
        profile: Foreign key to Profile model (denormalized for performance).
        scheduled_date: Scheduled intake date.
        scheduled_time: Scheduled intake time.
        intake_status: Current intake status (default: SCHEDULED).
        taken_at: Actual intake completion timestamp.
        created_at: Record creation timestamp.
        updated_at: Last update timestamp.
    """

    id = fields.UUIDField(pk=True)

    medication = fields.ForeignKeyField("models.Medication", related_name="intake_logs")
    # Profile ID denormalized here for query performance (minimize joins)
    profile = fields.ForeignKeyField("models.Profile", related_name="intake_logs")

    scheduled_date = fields.DateField(description="Scheduled intake date")
    scheduled_time = fields.TimeField(description="Scheduled intake time")

    # Default status changed from PENDING to SCHEDULED
    intake_status = fields.CharField(max_length=16, default="SCHEDULED", description="Intake status")
    taken_at = fields.DatetimeField(null=True, description="Actual intake completion time")

    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    class Meta:
        table = "intake_logs"
        indexes = (
            ("profile_id", "scheduled_date"),
            ("scheduled_date", "intake_status"),
        )

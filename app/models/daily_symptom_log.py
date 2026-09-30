"""Daily symptom log model module.

This module defines the DailySymptomLog model for storing user-reported
daily symptom entries linked to their profile.
"""

from tortoise import fields, models


class DailySymptomLog(models.Model):
  """Daily symptom log for tracking user-reported health symptoms.

  Allows users to record symptoms each day. Used alongside lifestyle guides
  to monitor medication side effects and general health trends.

  Attributes:
      id: Primary key UUID.
      profile: Foreign key to Profile model.
      log_date: The date this symptom entry represents.
      symptoms: JSON array of symptom strings reported by the user.
      note: Optional free-text note for additional context.
      created_at: Record creation timestamp.
  """

  id = fields.UUIDField(primary_key=True)
  profile = fields.ForeignKeyField(
    "models.Profile",
    related_name="symptom_logs",
    description="Log owner profile",
  )

  log_date = fields.DateField(description="Date of symptom report")

  # JSON array e.g. ["두통", "메스꺼움"]
  symptoms = fields.JSONField(default=list, description="List of reported symptoms")

  note = fields.CharField(max_length=512, null=True, description="Free-text note")

  created_at = fields.DatetimeField(auto_now_add=True)

  class Meta:
    table = "daily_symptom_logs"
    indexes = (("profile_id", "log_date"),)

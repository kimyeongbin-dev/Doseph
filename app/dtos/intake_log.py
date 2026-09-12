"""Intake log DTO models module.

This module contains data transfer objects for medication intake log operations
including creation and response serialization.
"""

from datetime import date, datetime, time
from uuid import UUID
import zoneinfo

from pydantic import BaseModel, ConfigDict, Field, field_validator

# DTO 경계에서 naive datetime 유입을 차단하기 위한 KST 타임존 상수
_KST = zoneinfo.ZoneInfo("Asia/Seoul")


def _make_aware(v: datetime | None) -> datetime | None:
    """Return timezone-aware datetime; assume KST if tzinfo is missing.

    tzinfo가 없는 naive datetime은 KST로 간주하여 aware datetime으로 변환합니다.
    이미 aware datetime이면 그대로 반환합니다.
    """
    if v is None:
        return v
    return v if v.tzinfo is not None else v.replace(tzinfo=_KST)


class BaseIntakeLog(BaseModel):
    """Base intake log model — 클라이언트가 지정하는 스케줄 공통 필드.

    복용 상태(intake_status)·실제 복용시각(taken_at)은 서버가 결정하는 값이라
    생성 요청에 유입되지 않도록 base 에서 제외하고 응답 DTO 에만 둔다.
    """

    scheduled_date: date = Field(..., description="Scheduled intake date")
    scheduled_time: time = Field(..., description="Scheduled intake time")


class IntakeLogCreate(BaseIntakeLog):
    """Intake log creation request model.

    복용 상태는 서버가 항상 SCHEDULED 로 결정하며, 실제 복용시각(taken_at)은
    별도 ``/take``·``/skip`` 엔드포인트에서 기록한다. 따라서 생성 요청은 스케줄과
    대상(medication/profile) 만 받는다.
    """

    medication_id: UUID = Field(..., description="Connected medication ID")
    profile_id: UUID = Field(..., description="Connected profile ID")


class StreakResponse(BaseModel):
    """Medication streak response model.

    Used for returning consecutive medication days count for a profile.
    """

    streak_days: int = Field(..., description="Number of consecutive days with at least one taken medication")


class IntakeLogResponse(BaseIntakeLog):
    """Intake log response model.

    Used for serializing intake log data in API responses.
    Includes all intake log fields and metadata.
    """

    model_config = ConfigDict(from_attributes=True)

    id: UUID = Field(..., description="Intake log record ID")
    medication_id: UUID = Field(..., description="Connected medication ID")
    profile_id: UUID = Field(..., description="Connected profile ID")
    intake_status: str = Field(..., max_length=16, description="Intake status (e.g., SCHEDULED, TAKEN, MISSED)")
    taken_at: datetime | None = Field(None, description="Actual intake completion time")
    created_at: datetime = Field(..., description="Creation timestamp")
    updated_at: datetime = Field(..., description="Last update timestamp")

    @field_validator("taken_at", mode="before")
    @classmethod
    def ensure_aware_taken_at(cls, v: datetime | None) -> datetime | None:
        """Reject naive datetime; assume KST when tzinfo is absent."""
        return _make_aware(v)

"""Profile DTO models module.

This module contains data transfer objects for user profile operations
including creation, updates, and response serialization.
"""

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.models.profiles import Gender, RelationType


class BaseProfile(BaseModel):
    """Base profile model with common fields.

    Provides shared fields for profile operations including relationship type,
    gender, and health survey data.
    """

    relation_type: RelationType = Field(
        ...,
        description="가족 관계 (SELF / FATHER / MOTHER / SON / DAUGHTER / HUSBAND / WIFE / OTHER)",
    )
    gender: Gender | None = Field(
        None,
        description="성별 (MALE / FEMALE). 명시적 가족 관계 6종은 BE 가 default 자동 채움.",
    )
    name: str = Field(..., max_length=32, description="Profile name")
    health_survey: dict[str, Any] | None = Field(default=None, description="Health survey results (JSON)")


class ProfileCreate(BaseProfile):
    """Profile creation request model.

    Used for creating new user profiles. The owning account is set by the
    backend from the authenticated context — NOT accepted from the client
    (mass-assignment 방지).
    """


class ProfileUpdate(BaseModel):
    """Profile update request model.

    Used for partial updates to existing profiles.
    All fields are optional for flexible updates.
    """

    relation_type: RelationType | None = Field(None, description="가족 관계")
    gender: Gender | None = Field(None, description="성별 (MALE / FEMALE)")
    name: str | None = Field(None, max_length=32, description="Profile name")
    health_survey: dict[str, Any] | None = Field(None, description="Health survey results")


class ProfileSummaryResponse(BaseModel):
    """Profile summary response model for list endpoints.

    Lightweight response with minimal health survey data for UI matching.
    Used for profile listing and switching UI.
    """

    model_config = ConfigDict(from_attributes=True)

    id: UUID = Field(..., description="Profile unique ID")
    account_id: UUID = Field(..., description="Connected account ID")
    name: str = Field(..., description="Profile name")
    relation_type: RelationType = Field(..., description="가족 관계")
    gender: Gender | None = Field(None, description="성별")


class ProfileResponse(BaseProfile):
    """Profile response model.

    Used for serializing profile data in API responses.
    Includes all profile fields and metadata.
    """

    model_config = ConfigDict(from_attributes=True)

    id: UUID = Field(..., description="Profile unique ID")
    account_id: UUID = Field(..., description="Connected account ID")
    created_at: datetime = Field(..., description="Creation timestamp")
    updated_at: datetime = Field(..., description="Last update timestamp")

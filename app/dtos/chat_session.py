"""Chat session DTO models module.

This module contains data transfer objects for chat session operations
including creation and response serialization.
"""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ChatSessionCreate(BaseModel):
    """Chat session creation request model."""

    profile_id: UUID = Field(..., description="Connected profile ID")
    title: str | None = Field(None, max_length=64, description="Session title")


class ChatSessionUpdate(BaseModel):
    """Chat session update request model (PATCH).

    Currently only the title is mutable; creation timestamps and foreign
    keys are intentionally immutable from the client side.
    """

    title: str = Field(..., max_length=64, description="New session title")

    @field_validator("title", mode="before")
    @classmethod
    def _strip_and_require_non_empty(cls, value: object) -> object:
        """Trim surrounding whitespace and reject empty/whitespace-only titles."""
        if not isinstance(value, str):
            return value
        stripped = value.strip()
        if not stripped:
            raise ValueError("title must not be empty or whitespace only")
        return stripped


class ChatSessionResponse(BaseModel):
    """Chat session response model.

    Used for serializing chat session data in API responses.
    Includes all session fields and metadata.
    """

    model_config = ConfigDict(from_attributes=True)

    id: UUID = Field(..., description="Session unique ID")
    profile_id: UUID = Field(..., description="Connected profile ID")
    title: str | None = Field(None, description="Session title")
    created_at: datetime = Field(..., description="Creation timestamp")
    updated_at: datetime = Field(..., description="Last update timestamp")

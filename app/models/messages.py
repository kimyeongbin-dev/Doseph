"""Chat message model module.

This module defines the ChatMessage model and related enums for storing
chat conversation messages between users and the AI assistant.
"""

from enum import StrEnum

from tortoise import fields, models


class SenderType(StrEnum):
    """Message sender type enumeration."""

    USER = "USER"
    ASSISTANT = "ASSISTANT"


class ChatMessage(models.Model):
    """Chat message model for conversation storage.

    This model stores individual messages within chat sessions,
    tracking sender type and message content.

    Attributes:
        id: Primary key UUID.
        session: Foreign key to ChatSession model.
        sender_type: Type of message sender (USER or ASSISTANT).
        content: Message content text.
        created_at: Message creation timestamp.
    """

    id = fields.UUIDField(pk=True)
    session = fields.ForeignKeyField("models.ChatSession", related_name="messages")
    sender_type = fields.CharEnumField(enum_type=SenderType, max_length=16)
    content = fields.TextField()
    metadata = fields.JSONField(
        default=dict,
        description="RAG debug/audit metadata (intent, medicine_names, scores, token usage)",
    )
    created_at = fields.DatetimeField(auto_now_add=True)

    class Meta:
        table = "messages"
        indexes = [
            ("session_id", "created_at"),
        ]

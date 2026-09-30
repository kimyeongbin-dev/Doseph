"""Tests for the messages.metadata JSONB field and repository plumbing.

The `metadata` field holds RAG debug/audit data (intent, medicine_names,
retrieval scores, token usage, etc.). This file only pins the schema +
repository contract; the actual RAG pipeline wiring is covered in later
commits (RAGResponse extension + MessageService integration).
"""

import inspect

from tortoise import fields

from app.models.messages import ChatMessage
from app.repositories.message_repository import MessageRepository


class TestChatMessageSchema:
  """ChatMessage must carry a JSONB metadata field with a dict default."""

  def test_metadata_field_exists(self) -> None:
    assert "metadata" in ChatMessage._meta.fields_map

  def test_metadata_is_jsonfield(self) -> None:
    field = ChatMessage._meta.fields_map["metadata"]
    assert isinstance(field, fields.JSONField)

  def test_metadata_default_is_empty_dict(self) -> None:
    field = ChatMessage._meta.fields_map["metadata"]
    default = field.default
    resolved = default() if callable(default) else default
    assert resolved == {}


class TestMessageRepositoryCreateSignatures:
  """create / create_user_message / create_assistant_message accept metadata."""

  def test_create_accepts_metadata_kwarg(self) -> None:
    params = inspect.signature(MessageRepository.create).parameters
    assert "metadata" in params

  def test_create_user_message_accepts_metadata_kwarg(self) -> None:
    params = inspect.signature(MessageRepository.create_user_message).parameters
    assert "metadata" in params

  def test_create_assistant_message_accepts_metadata_kwarg(self) -> None:
    params = inspect.signature(MessageRepository.create_assistant_message).parameters
    assert "metadata" in params

  def test_metadata_kwarg_has_none_default(self) -> None:
    """Metadata kwarg must default to None so the repository can pick {} on persist."""
    params = inspect.signature(MessageRepository.create).parameters
    assert params["metadata"].default is None

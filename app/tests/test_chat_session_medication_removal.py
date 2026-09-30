"""Tests verifying the removal of ChatSession.medication FK and related plumbing.

The medication FK on chat_sessions was unused in both the API flow and the
RAG pipeline. It stays only as stale plumbing that adds confusion and an
unused index. These tests pin the absence of every touchpoint so the
migration that drops the column stays green.
"""

import inspect

from app.dtos.chat_session import ChatSessionCreate, ChatSessionResponse
from app.models.chat_sessions import ChatSession
from app.repositories.chat_session_repository import ChatSessionRepository
from app.services.chat_session_service import ChatSessionService


class TestChatSessionModelSchema:
  """Verify the ORM model no longer exposes the medication FK."""

  def test_medication_field_is_removed(self) -> None:
    assert "medication" not in ChatSession._meta.fields_map
    assert "medication_id" not in ChatSession._meta.fields_map


class TestChatSessionDto:
  """DTO must not accept or expose medication_id anymore."""

  def test_create_dto_has_no_medication_id(self) -> None:
    assert "medication_id" not in ChatSessionCreate.model_fields

  def test_response_dto_has_no_medication_id(self) -> None:
    assert "medication_id" not in ChatSessionResponse.model_fields


class TestChatSessionRepository:
  """Repository surface no longer carries medication-specific methods."""

  def test_get_by_medication_is_removed(self) -> None:
    assert not hasattr(ChatSessionRepository, "get_by_medication")

  def test_create_signature_has_no_medication_id(self) -> None:
    params = inspect.signature(ChatSessionRepository.create).parameters
    assert "medication_id" not in params


class TestChatSessionService:
  """Service create methods no longer accept medication_id."""

  def test_create_session_signature(self) -> None:
    params = inspect.signature(ChatSessionService.create_session).parameters
    assert "medication_id" not in params

  def test_create_session_with_owner_check_signature(self) -> None:
    params = inspect.signature(ChatSessionService.create_session_with_owner_check).parameters
    assert "medication_id" not in params

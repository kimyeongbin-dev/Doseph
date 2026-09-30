"""Tests for ChatSessionService title update (PATCH) path.

Covers the ownership-checked title update flow introduced to back the
sidebar's inline rename UX. DTO field validation is covered at the
schema layer; here we verify service behavior with a mocked repository.
"""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from fastapi import HTTPException
from pydantic import ValidationError
import pytest

from app.dtos.chat_session import ChatSessionUpdate
from app.services.chat_session_service import ChatSessionService


class TestChatSessionUpdateDto:
  """Validation rules on the PATCH request DTO."""

  def test_rejects_empty_title(self) -> None:
    with pytest.raises(ValidationError):
      ChatSessionUpdate(title="")

  def test_rejects_whitespace_only_title(self) -> None:
    with pytest.raises(ValidationError):
      ChatSessionUpdate(title="   ")

  def test_strips_surrounding_whitespace(self) -> None:
    dto = ChatSessionUpdate(title="  제목  ")
    assert dto.title == "제목"

  def test_rejects_title_longer_than_limit(self) -> None:
    with pytest.raises(ValidationError):
      ChatSessionUpdate(title="a" * 65)

  def test_accepts_64_char_title(self) -> None:
    dto = ChatSessionUpdate(title="a" * 64)
    assert dto.title == "a" * 64


class TestUpdateSessionTitleWithOwnerCheck:
  """ChatSessionService.update_session_title_with_owner_check behavior."""

  @pytest.mark.asyncio
  async def test_updates_title_when_owner_matches(self) -> None:
    account_id = uuid4()
    session_id = uuid4()
    session = MagicMock()
    session.account_id = account_id

    service = ChatSessionService()
    with (
      patch.object(service.repository, "get_by_id", new=AsyncMock(return_value=session)),
      patch.object(service.repository, "update", new=AsyncMock(return_value=session)) as mock_update,
    ):
      result = await service.update_session_title_with_owner_check(
        session_id=session_id,
        account_id=account_id,
        title="새 제목",
      )

    assert result is session
    mock_update.assert_awaited_once_with(session, title="새 제목")

  @pytest.mark.asyncio
  async def test_raises_403_when_owner_mismatch(self) -> None:
    account_id = uuid4()
    other_account_id = uuid4()
    session = MagicMock()
    session.account_id = other_account_id

    service = ChatSessionService()
    with (
      patch.object(service.repository, "get_by_id", new=AsyncMock(return_value=session)),
      pytest.raises(HTTPException) as exc_info,
    ):
      await service.update_session_title_with_owner_check(
        session_id=uuid4(),
        account_id=account_id,
        title="새 제목",
      )
    assert exc_info.value.status_code == 403

  @pytest.mark.asyncio
  async def test_raises_404_when_session_missing(self) -> None:
    service = ChatSessionService()
    with (
      patch.object(service.repository, "get_by_id", new=AsyncMock(return_value=None)),
      pytest.raises(HTTPException) as exc_info,
    ):
      await service.update_session_title_with_owner_check(
        session_id=uuid4(),
        account_id=uuid4(),
        title="새 제목",
      )
    assert exc_info.value.status_code == 404

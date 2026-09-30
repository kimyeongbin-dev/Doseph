"""Chat session API router module.

This module contains HTTP endpoints for chat session operations
including creating, reading, and deleting chat sessions.
"""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, status

from app.dependencies.security import get_current_account
from app.dtos.chat_session import ChatSessionCreate, ChatSessionResponse, ChatSessionUpdate
from app.models.accounts import Account
from app.services.chat_session_service import ChatSessionService

router = APIRouter(prefix="/chat-sessions", tags=["Chat"])


def get_chat_session_service() -> ChatSessionService:
  """Get chat session service instance.

  Returns:
      ChatSessionService: Chat session service instance.
  """
  return ChatSessionService()


# Type aliases for dependency injection
ChatSessionServiceDep = Annotated[ChatSessionService, Depends(get_chat_session_service)]
CurrentAccount = Annotated[Account, Depends(get_current_account)]


@router.post(
  "",
  response_model=ChatSessionResponse,
  status_code=status.HTTP_201_CREATED,
  summary="Create chat session",
)
async def create_chat_session(
  data: ChatSessionCreate,
  current_account: CurrentAccount,
  service: ChatSessionServiceDep,
) -> ChatSessionResponse:
  """Create a new chat consultation session.

  Args:
      data: Chat session creation data.
      current_account: Current authenticated account.
      service: Chat session service instance.

  Returns:
      ChatSessionResponse: Created chat session information.
  """
  # Use authenticated account ID (ignore account_id from request body)
  session = await service.create_session_with_owner_check(
    account_id=current_account.id,
    profile_id=data.profile_id,
    title=data.title,
  )
  return ChatSessionResponse.model_validate(session)


@router.get(
  "/{session_id}",
  response_model=ChatSessionResponse,
  summary="Get chat session details",
)
async def get_chat_session(
  session_id: UUID,
  current_account: CurrentAccount,
  service: ChatSessionServiceDep,
) -> ChatSessionResponse:
  """Get detailed information about a specific chat session.

  Args:
      session_id: Chat session ID to retrieve.
      current_account: Current authenticated account.
      service: Chat session service instance.

  Returns:
      ChatSessionResponse: Chat session details.
  """
  session = await service.get_session_with_owner_check(session_id, current_account.id)
  return ChatSessionResponse.model_validate(session)


@router.get(
  "",
  response_model=list[ChatSessionResponse],
  summary="List chat sessions",
)
async def list_chat_sessions(
  current_account: CurrentAccount,
  service: ChatSessionServiceDep,
  profile_id: UUID | None = None,
) -> list[ChatSessionResponse]:
  """List chat sessions with optional filtering by profile.

  Args:
      current_account: Current authenticated account.
      service: Chat session service instance.
      profile_id: Optional profile ID to filter by.

  Returns:
      list[ChatSessionResponse]: List of chat sessions.
  """
  if profile_id:
    sessions = await service.get_sessions_by_profile_with_owner_check(profile_id, current_account.id)
  else:
    sessions = await service.get_sessions_by_account(current_account.id)
  return [ChatSessionResponse.model_validate(s) for s in sessions]


@router.patch(
  "/{session_id}",
  response_model=ChatSessionResponse,
  summary="Update chat session title",
)
async def update_chat_session(
  session_id: UUID,
  data: ChatSessionUpdate,
  current_account: CurrentAccount,
  service: ChatSessionServiceDep,
) -> ChatSessionResponse:
  """Update a chat session's title (only title is mutable).

  Args:
      session_id: Chat session ID to update.
      data: Fields to update; only `title` is currently supported.
      current_account: Current authenticated account.
      service: Chat session service instance.

  Returns:
      ChatSessionResponse: Updated chat session.
  """
  session = await service.update_session_title_with_owner_check(
    session_id=session_id,
    account_id=current_account.id,
    title=data.title,
  )
  return ChatSessionResponse.model_validate(session)


@router.delete(
  "/{session_id}",
  status_code=status.HTTP_204_NO_CONTENT,
  summary="Delete chat session",
)
async def delete_chat_session(
  session_id: UUID,
  current_account: CurrentAccount,
  service: ChatSessionServiceDep,
) -> None:
  """Delete a chat session.

  Args:
      session_id: Chat session ID to delete.
      current_account: Current authenticated account.
      service: Chat session service instance.
  """
  await service.delete_session_with_owner_check(session_id, current_account.id)

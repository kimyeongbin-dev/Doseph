"""Message API router module.

This module contains HTTP endpoints for chat message operations
including sending messages, retrieving chat history, and AI responses.
"""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Response, status

from app.dependencies.security import get_current_account
from app.dtos.message import (
  ChatAskPendingResponse,
  ChatAskRequest,
  ChatAskResponse,
  MessageCreate,
  MessageResponse,
  ToolResultRequest,
  ToolResultResponse,
)
from app.models.accounts import Account
from app.services.message_service import MessageService

router = APIRouter(prefix="/messages", tags=["Chat"])


def get_message_service() -> MessageService:
  """Get message service instance.

  Returns:
      MessageService: Message service instance.
  """
  return MessageService()


# Type aliases for dependency injection
MessageServiceDep = Annotated[MessageService, Depends(get_message_service)]
CurrentAccount = Annotated[Account, Depends(get_current_account)]


@router.post(
  "/ask",
  response_model=ChatAskResponse | ChatAskPendingResponse,
  status_code=status.HTTP_200_OK,
  summary="Send user question, receive AI answer or GPS-callback handoff",
  responses={
    status.HTTP_200_OK: {"model": ChatAskResponse, "description": "Assistant answer ready"},
    status.HTTP_202_ACCEPTED: {
      "model": ChatAskPendingResponse,
      "description": "A location tool was requested; submit GPS to /tool-result",
    },
  },
)
async def ask_message(
  data: ChatAskRequest,
  current_account: CurrentAccount,
  service: MessageServiceDep,
  response: Response,
) -> ChatAskResponse | ChatAskPendingResponse:
  """Route the user message through the Router LLM and fan out.

  Three outcomes the FE must handle:

  - **200** — the Router answered directly (text or RAG fallback) or
    every requested tool could run now (keyword-only). The response
    body contains both the user turn and the assistant turn.
  - **202** — the Router requested at least one location-based tool.
    The user turn is saved, the rest of the turn is held in Redis
    under ``turn_id``, and the client is expected to POST geolocation
    (or a denial) to ``/messages/tool-result``.

  Args:
      data: ``{session_id, content}`` chat ask payload.
      current_account: Authenticated account from the security dep.
      service: ``MessageService`` (DI).
      response: FastAPI response object, used to flip the status code
          to 202 when the turn is parked.

  Returns:
      ``ChatAskResponse`` on the 200 path or ``ChatAskPendingResponse``
      on the 202 path.
  """
  result = await service.ask_with_tools(
    session_id=data.session_id,
    account_id=current_account.id,
    content=data.content,
  )

  user_dto = MessageResponse.model_validate(result.user_message)

  if result.pending is not None:
    response.status_code = status.HTTP_202_ACCEPTED
    return ChatAskPendingResponse(
      user_message=user_dto,
      turn_id=result.pending.turn_id,
      session_id=data.session_id,
      ttl_sec=result.pending.ttl_sec,
    )

  return ChatAskResponse(
    user_message=user_dto,
    assistant_message=MessageResponse.model_validate(result.assistant_message),
  )


@router.post(
  "/tool-result",
  response_model=ToolResultResponse,
  status_code=status.HTTP_200_OK,
  summary="Resolve a pending turn with a geolocation callback",
  responses={
    status.HTTP_400_BAD_REQUEST: {"description": "status='ok' without lat/lng"},
    status.HTTP_403_FORBIDDEN: {"description": "turn_id belongs to another account"},
    status.HTTP_410_GONE: {"description": "turn_id expired or unknown"},
  },
)
async def submit_tool_result(
  data: ToolResultRequest,
  current_account: CurrentAccount,
  service: MessageServiceDep,
) -> ToolResultResponse:
  """Complete a turn that was paused for GPS permission.

  The 400 / 403 / 410 branches are raised by the service layer (see
  ``MessageService.resolve_pending_turn``) and bubble up unchanged as
  standard FastAPI ``HTTPException`` responses.

  Args:
      data: Callback payload ``{turn_id, status, lat?, lng?}``.
      current_account: Authenticated account; must own the pending turn.
      service: ``MessageService`` (DI).

  Returns:
      ``ToolResultResponse`` wrapping the freshly-built assistant turn.
  """
  result = await service.resolve_pending_turn(
    turn_id=data.turn_id,
    account_id=current_account.id,
    status=data.status,
    lat=data.lat,
    lng=data.lng,
  )
  return ToolResultResponse(
    assistant_message=MessageResponse.model_validate(result.assistant_message),
  )


@router.post(
  "",
  response_model=MessageResponse,
  status_code=status.HTTP_201_CREATED,
  summary="Send message",
)
async def send_message(
  data: MessageCreate,
  current_account: CurrentAccount,
  service: MessageServiceDep,
) -> MessageResponse:
  """Send a message within a chat session.

  Args:
      data: Message creation data.
      current_account: Current authenticated account.
      service: Message service instance.

  Returns:
      MessageResponse: Created message information.
  """
  message = await service.create_user_message_with_owner_check(
    session_id=data.session_id,
    account_id=current_account.id,
    content=data.content,
  )
  return MessageResponse.model_validate(message)


@router.get(
  "/session/{session_id}",
  response_model=list[MessageResponse],
  summary="Get chat history",
)
async def list_messages(
  session_id: UUID,
  current_account: CurrentAccount,
  service: MessageServiceDep,
  limit: int | None = None,
) -> list[MessageResponse]:
  """Get all message history for a specific chat session in chronological order.

  Args:
      session_id: Chat session ID to retrieve messages from.
      current_account: Current authenticated account.
      service: Message service instance.
      limit: Optional limit on number of messages to retrieve.

  Returns:
      list[MessageResponse]: List of messages in chronological order.
  """
  messages = await service.get_messages_by_session_with_owner_check(session_id, current_account.id, limit)
  return [MessageResponse.model_validate(m) for m in messages]


@router.delete(
  "/{message_id}",
  status_code=status.HTTP_204_NO_CONTENT,
  summary="Delete message",
)
async def delete_message(
  message_id: UUID,
  current_account: CurrentAccount,
  service: MessageServiceDep,
) -> None:
  """Delete a specific message.

  Args:
      message_id: Message ID to delete.
      current_account: Current authenticated account.
      service: Message service instance.
  """
  await service.delete_message_with_owner_check(message_id, current_account.id)

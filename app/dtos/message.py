"""Message DTO models module.

This module contains data transfer objects for chat message operations
including creation, AI chat requests, and response serialization.
"""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.models.messages import SenderType


class MessageCreate(BaseModel):
    """Message creation request model.

    서버가 발신자를 USER 로 강제하므로 sender_type 은 요청에서 받지 않는다
    (클라이언트가 ASSISTANT 로 위조 지정하는 것을 계약 수준에서 차단). ASSISTANT
    메시지는 서버 내부(recall_notification 등)에서 모델 레벨로만 생성된다.
    """

    session_id: UUID = Field(..., description="Connected chat session ID")
    content: str = Field(..., description="Message content")


class ChatAskRequest(BaseModel):
    """Chat ask request model.

    Used for user questions that trigger AI responses
    in the RAG-based chat system.
    """

    session_id: UUID = Field(..., description="Connected chat session ID")
    content: str = Field(..., description="User question")


class MessageResponse(BaseModel):
    """Message response model.

    Used for serializing message data in API responses.
    Includes all message fields and metadata.
    """

    model_config = ConfigDict(from_attributes=True)

    id: UUID = Field(..., description="Message unique ID")
    session_id: UUID = Field(..., description="Connected session ID")
    sender_type: SenderType = Field(..., description="Sender type")
    content: str = Field(..., description="Message content")
    created_at: datetime = Field(..., description="Send timestamp")


class ChatAskResponse(BaseModel):
    """Chat ask response model.

    Used for returning both user and AI assistant messages
    in a single response after AI processing.
    """

    user_message: MessageResponse
    assistant_message: MessageResponse


class ChatAskPendingResponse(BaseModel):
    """202 response shape when a turn is paused for a GPS callback (Y-7).

    The Router LLM requested at least one location-based tool, so the
    server has persisted the user message, stored a pending turn in
    Redis, and now waits for the client to POST geolocation (or a
    denial) to ``/messages/tool-result``.

    ``action`` is fixed to ``"request_geolocation"`` so future Phase Y
    iterations can add new pending actions (e.g. OAuth re-auth) without
    breaking clients that route on this tag.
    """

    user_message: MessageResponse = Field(..., description="Already-persisted user message")
    action: Literal["request_geolocation"] = Field(
        default="request_geolocation",
        description="Tag telling the FE what capability to request next",
    )
    turn_id: str = Field(..., description="Pending turn id to echo back on callback")
    session_id: UUID = Field(..., description="Chat session id for client routing")
    ttl_sec: int = Field(..., description="Seconds before the pending turn expires")


class ToolResultRequest(BaseModel):
    """``POST /messages/tool-result`` request body (Y-7).

    ``status="ok"`` requires both ``lat`` and ``lng``; the service layer
    (``resolve_pending_turn``) enforces this at runtime and returns 400
    on violation, so we keep the fields optional here to surface the
    denial path as a single validated shape.
    """

    turn_id: str = Field(..., description="Pending turn id from the /ask 202 response")
    status: Literal["ok", "denied"] = Field(..., description="Geolocation permission outcome")
    lat: float | None = Field(default=None, description="Latitude (WGS84) when status='ok'")
    lng: float | None = Field(default=None, description="Longitude (WGS84) when status='ok'")


class ToolResultResponse(BaseModel):
    """``POST /messages/tool-result`` 200 response."""

    assistant_message: MessageResponse = Field(..., description="LLM answer built from tool results")

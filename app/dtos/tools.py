"""DTOs for the tool-calling subsystem (Phase Y).

These models cross layer boundaries (router → service → external API →
LLM), so they must stay decoupled from Tortoise ORM and framework-
specific types. Keep them to plain Pydantic models.

The module starts with ``KakaoPlace`` (Y-1). Additional DTOs used by
later Y phases — ``ToolCall``, ``PendingTurn``, ``ToolResultRequest``,
``RequestGeolocationResponse`` — are added in their
respective phases and will live here alongside ``KakaoPlace``.
"""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class KakaoPlace(BaseModel):
  """Normalized view of one Kakao Local API ``documents[i]`` entry.

  Carries only the fields downstream code (LLM prompt, frontend map
  cards, message metadata) actually consumes. Raw distance strings,
  URLs, and region metadata are dropped on purpose — re-add if a
  concrete use case appears.
  """

  id: str = Field(description="Kakao-issued place id")
  place_name: str = Field(description="Display name of the place")
  address: str = Field(description="Jibun address (address_name)")
  road_address: str | None = Field(default=None, description="Road address (road_address_name)")
  phone: str | None = Field(default=None, description="Phone number")
  category_name: str | None = Field(default=None, description="Full category path, e.g. '의료,건강 > 약국'")
  category_group_code: str | None = Field(
    default=None,
    description="Kakao category group code: PM9 (약국), HP8 (병원), etc.",
  )
  lat: float = Field(description="Latitude (WGS84), mapped from Kakao 'y'")
  lng: float = Field(description="Longitude (WGS84), mapped from Kakao 'x'")


class ToolCall(BaseModel):
  """One LLM-issued function call inside a turn (Y-3, Y-4).

  The ``needs_geolocation`` flag is computed by the router after parsing
  arguments: ``True`` when the function is location-based and the user's
  coordinates are not yet known. Used to decide whether the whole turn
  must wait for a frontend GPS callback.
  """

  tool_call_id: str = Field(description="OpenAI-issued id matching tool_calls[i].id")
  name: str = Field(description="Function name, e.g. 'search_hospitals_by_location'")
  arguments: dict[str, Any] = Field(default_factory=dict, description="Parsed JSON arguments")
  needs_geolocation: bool = Field(default=False, description="True if this call requires a GPS callback")


class PendingTurn(BaseModel):
  """A whole conversation turn paused while waiting for a frontend callback.

  Stored as a single JSON blob in Redis under ``pending:turn:{turn_id}``
  with a TTL. ``eager_results`` caches results of tool calls that could
  be executed immediately (e.g. keyword search) so we do not re-run them
  after the geolocation callback arrives.
  """

  turn_id: str = Field(description="UUID assigned by the store; echoed back to FE")
  session_id: str = Field(description="Chat session UUID")
  account_id: str = Field(description="Owner account UUID; checked on callback")
  messages_snapshot: list[dict[str, Any]] = Field(
    description="Original messages + Router LLM assistant message with tool_calls",
  )
  tool_calls: list[ToolCall] = Field(description="All tool calls the LLM issued in this turn")
  eager_results: dict[str, Any] = Field(
    default_factory=dict,
    description="Pre-executed tool results keyed by tool_call_id (e.g. keyword search outputs)",
  )
  created_at: datetime = Field(description="Aware UTC timestamp")


class AskPending(BaseModel):
  """Handoff payload returned when a turn is paused for a GPS callback (Y-6).

  Carries only what the frontend needs to complete the callback:
  the server-issued ``turn_id`` and how many seconds the turn will
  stay alive in the pending store.
  """

  turn_id: str = Field(description="Pending turn id echoed back on callback")
  ttl_sec: int = Field(description="Seconds remaining before the turn expires")


class AskResult(BaseModel):
  """Union-shaped result of ``MessageService.ask_with_tools`` (Y-6).

  One shape covers three branches the router produces:

  - **text / full tool run**: both ``user_message`` and
    ``assistant_message`` are set, ``pending`` is ``None``.
  - **location pending**: ``user_message`` is set, ``assistant_message``
    is ``None``, and ``pending`` carries the ``AskPending`` handoff.

  ``user_message`` and ``assistant_message`` are ORM-level
  ``ChatMessage`` instances, so the field type is ``Any`` to avoid a
  cross-layer import and preserve the service's DB coupling point.
  """

  model_config = {"arbitrary_types_allowed": True}

  user_message: Any = Field(default=None, description="Saved user-turn ChatMessage (or None)")
  assistant_message: Any = Field(default=None, description="Saved assistant-turn ChatMessage (or None if pending)")
  pending: AskPending | None = Field(default=None, description="Set when the turn is paused for a GPS callback")

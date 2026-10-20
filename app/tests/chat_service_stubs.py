"""챗봇 서비스(``MessageService``) 단위 테스트용 가짜 저장소·분류기.

``test_message_service_*`` 파일들이 같은 가짜(메시지·세션·저장소 메서드 6개·분류기)를
각자 복사해 들고 있었다(약 70줄씩). 한 곳에 모아 둔다 — 저장소 시그니처가 바뀌면
여기 한 곳만 고친다.

DB 를 쓰지 않는다. 저장소 메서드를 클래스 단위로 바꿔치기하므로 ``monkeypatch`` 가
테스트가 끝나면 되돌린다.
"""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID, uuid4

import pytest

from app.dtos.query_rewriter import IntentType, LocationQuery, QueryRewriterOutput, RecallQuery
from app.repositories.chat_session_repository import ChatSessionRepository
from app.repositories.message_repository import MessageRepository


class StubChatMessage:
  """``ChatMessage`` 대역 — 서비스가 읽는 속성만 가진다."""

  def __init__(self, *, content: str, sender_type: str, metadata: dict[str, Any] | None = None) -> None:
    self.id = str(uuid4())
    self.content = content
    self.sender_type = sender_type
    self.metadata: dict[str, Any] = metadata or {}


class StubSession:
  """``ChatSession`` 대역 — 소유 검증과 프로필 조회에 쓰는 속성만 가진다."""

  def __init__(self, *, session_id: UUID, account_id: UUID, profile_id: UUID) -> None:
    self.id = session_id
    self.account_id = account_id
    self.profile_id = profile_id
    self.summary = None


@dataclass
class ChatStubs:
  """설치된 가짜 저장소의 식별자와, 저장소에 들어간 메시지 기록."""

  session_id: UUID = field(default_factory=uuid4)
  account_id: UUID = field(default_factory=uuid4)
  profile_id: UUID = field(default_factory=uuid4)
  user_contents: list[str] = field(default_factory=list)
  assistant_contents: list[str] = field(default_factory=list)


# ── 저장소 가짜 설치 ────────────────────────────────────────────────
# 흐름: 세션 조회 -> 최근 메시지(빈 목록) -> 사용자·어시스턴트 메시지 저장(기록)
#       -> 메시지 수(0) -> 메시지 삭제(무시)
def install_chat_repo_stubs(monkeypatch: pytest.MonkeyPatch) -> ChatStubs:
  """``ChatSessionRepository``·``MessageRepository`` 를 DB 없는 가짜로 바꾼다."""
  stubs = ChatStubs()

  async def get_session(_self: ChatSessionRepository, _session_id: UUID) -> StubSession:
    return StubSession(session_id=stubs.session_id, account_id=stubs.account_id, profile_id=stubs.profile_id)

  async def recent(_self: MessageRepository, _session_id: UUID, limit: int = 10) -> list[StubChatMessage]:
    return []

  async def create_user(
    _self: MessageRepository, _session_id: UUID, content: str, metadata: dict[str, Any] | None = None
  ) -> StubChatMessage:
    stubs.user_contents.append(content)
    return StubChatMessage(content=content, sender_type="USER", metadata=metadata)

  async def create_assistant(
    _self: MessageRepository, _session_id: UUID, content: str, metadata: dict[str, Any] | None = None
  ) -> StubChatMessage:
    stubs.assistant_contents.append(content)
    return StubChatMessage(content=content, sender_type="ASSISTANT", metadata=metadata)

  async def count(_self: MessageRepository, _session_id: UUID) -> int:
    return 0

  async def delete(_self: MessageRepository, message: StubChatMessage) -> StubChatMessage:
    return message

  monkeypatch.setattr(ChatSessionRepository, "get_by_id", get_session)
  monkeypatch.setattr(MessageRepository, "get_recent_by_session", recent)
  monkeypatch.setattr(MessageRepository, "create_user_message", create_user)
  monkeypatch.setattr(MessageRepository, "create_assistant_message", create_assistant)
  monkeypatch.setattr(MessageRepository, "count_by_session", count)
  monkeypatch.setattr(MessageRepository, "soft_delete", delete)
  return stubs


ClassifyFn = Callable[[UUID, list[dict[str, str]]], Awaitable[tuple[str, str, QueryRewriterOutput]]]


def make_classify(
  intent: IntentType,
  *,
  recall_query: RecallQuery | None = None,
  location_query: LocationQuery | None = None,
) -> ClassifyFn:
  """``classify_user_turn`` 대역 — 정해 둔 의도·조건을 그대로 돌려준다."""
  output = QueryRewriterOutput(intent=intent, recall_query=recall_query, location_query=location_query)

  async def classify(_profile_id: UUID, _messages: list[dict[str, str]]) -> tuple[str, str, QueryRewriterOutput]:
    return ("", "", output)

  return classify

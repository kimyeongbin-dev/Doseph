"""Message repository module.

This module provides data access layer for the messages table,
handling chat message storage and retrieval operations.
"""

from uuid import UUID, uuid4

from app.models.messages import ChatMessage, SenderType


class MessageRepository:
    """Chat message database repository for conversation management."""

    async def get_by_id(self, message_id: UUID) -> ChatMessage | None:
        """Get message by ID.

        Args:
            message_id: Message UUID.

        Returns:
            ChatMessage | None: Message if found, None otherwise.
        """
        return await ChatMessage.filter(
            id=message_id,
        ).first()

    async def count_by_session(self, session_id: UUID) -> int:
        """세션의 메시지 수 — 옵션 D 의 compact trigger 입력."""
        return await ChatMessage.filter(session_id=session_id).count()

    async def get_by_session(self, session_id: UUID, limit: int | None = None) -> list[ChatMessage]:
        """Get all messages in a session (chronological order).

        Args:
            session_id: Session UUID.
            limit: Optional limit on number of messages.

        Returns:
            list[ChatMessage]: List of messages in chronological order.
        """
        query = ChatMessage.filter(
            session_id=session_id,
        ).order_by("created_at")

        if limit:
            query = query.limit(limit)

        return await query.all()

    async def get_recent_by_session(self, session_id: UUID, limit: int = 10) -> list[ChatMessage]:
        """Get recent messages in a session.

        Args:
            session_id: Session UUID.
            limit: Maximum number of messages to retrieve.

        Returns:
            list[ChatMessage]: List of recent messages.
        """
        return (
            await ChatMessage
            .filter(
                session_id=session_id,
            )
            .order_by("-created_at")
            .limit(limit)
            .all()
        )

    async def create(
        self,
        session_id: UUID,
        sender_type: SenderType,
        content: str,
        metadata: dict | None = None,
    ) -> ChatMessage:
        """Create new message.

        Args:
            session_id: Session UUID.
            sender_type: Type of sender (USER or ASSISTANT).
            content: Message content.
            metadata: Optional RAG metadata (intent, medicine_names, scores,
                token usage). None is persisted as an empty dict.

        Returns:
            ChatMessage: Created message.
        """
        return await ChatMessage.create(
            id=uuid4(),
            session_id=session_id,
            sender_type=sender_type,
            content=content,
            metadata=metadata if metadata is not None else {},
        )

    async def create_user_message(
        self,
        session_id: UUID,
        content: str,
        metadata: dict | None = None,
    ) -> ChatMessage:
        """Create user message.

        Args:
            session_id: Session UUID.
            content: Message content.
            metadata: Optional RAG metadata attached to the user turn.

        Returns:
            ChatMessage: Created user message.
        """
        return await self.create(session_id, SenderType.USER, content, metadata=metadata)

    async def create_assistant_message(
        self,
        session_id: UUID,
        content: str,
        metadata: dict | None = None,
    ) -> ChatMessage:
        """Create assistant message.

        Args:
            session_id: Session UUID.
            content: Message content.
            metadata: Optional RAG metadata attached to the assistant turn.

        Returns:
            ChatMessage: Created assistant message.
        """
        return await self.create(session_id, SenderType.ASSISTANT, content, metadata=metadata)

    async def soft_delete(self, message: ChatMessage) -> ChatMessage:
        """Delete a message row.

        ⚠️ 이름은 ``soft_delete`` 지만 **물리 삭제**다(QA-01, 2026-09-15).

        Args:
            message: Message to delete.

        Returns:
            ChatMessage: The (now deleted) instance.
        """
        await ChatMessage.filter(id=message.id).delete()
        return message

    async def bulk_soft_delete_by_session(self, session_id: UUID) -> int:
        """세션의 모든 메시지를 일괄 삭제한다.

        ⚠️ 이름과 달리 **물리 삭제**다(QA-01). 멱등하다.

        세션을 지우는 경우에는 **부를 필요가 없다** — ``messages.session_id`` 가
        ``ON DELETE CASCADE`` 라 DB 가 알아서 지운다. 세션은 남기고 메시지만
        비우는 경우에만 쓴다.

        Args:
            session_id: 대상 세션 UUID.

        Returns:
            삭제된 row 수.
        """
        return await ChatMessage.filter(session_id=session_id).delete()

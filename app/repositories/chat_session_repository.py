"""Chat session repository module.

This module provides data access layer for the chat_sessions table,
handling conversation session management operations.
"""

from datetime import UTC, datetime
from uuid import UUID, uuid4

from app.models.chat_sessions import ChatSession


class ChatSessionRepository:
    """Chat session database repository for conversation management."""

    async def get_by_id(self, session_id: UUID) -> ChatSession | None:
        """Get session by ID.

        Args:
            session_id: Session UUID.

        Returns:
            ChatSession | None: Session if found, None otherwise.
        """
        return await ChatSession.filter(
            id=session_id,
        ).first()

    async def get_all_by_account(self, account_id: UUID) -> list[ChatSession]:
        """Get all chat sessions for an account.

        Args:
            account_id: Account UUID.

        Returns:
            list[ChatSession]: List of chat sessions.
        """
        return (
            await ChatSession
            .filter(
                account_id=account_id,
            )
            .order_by("-created_at")
            .all()
        )

    async def get_by_profile(self, profile_id: UUID) -> list[ChatSession]:
        """Get chat sessions for a profile.

        Args:
            profile_id: Profile UUID.

        Returns:
            list[ChatSession]: List of chat sessions.
        """
        return (
            await ChatSession
            .filter(
                profile_id=profile_id,
            )
            .order_by("-created_at")
            .all()
        )

    async def create(
        self,
        account_id: UUID,
        profile_id: UUID,
        title: str | None = None,
    ) -> ChatSession:
        """Create new chat session.

        Args:
            account_id: Account UUID.
            profile_id: Profile UUID.
            title: Optional session title.

        Returns:
            ChatSession: Created session.
        """
        return await ChatSession.create(
            id=uuid4(),
            account_id=account_id,
            profile_id=profile_id,
            title=title,
        )

    async def update(self, session: ChatSession, **kwargs) -> ChatSession:
        """Update chat session information.

        Args:
            session: Session to update.
            **kwargs: Fields to update.

        Returns:
            ChatSession: Updated session.
        """
        await session.update_from_dict(kwargs).save()
        return session

    async def update_summary(self, session_id: UUID, summary: str) -> int:
        """세션 요약 + 갱신 timestamp UPDATE — compact RQ job 종료 시 호출.

        Args:
            session_id: 갱신 대상 세션 UUID.
            summary: SessionCompactService 가 만든 마크다운 요약 본문.

        Returns:
            UPDATE 된 row 수 (정상이면 1, 세션 없으면 0).
        """
        return await ChatSession.filter(id=session_id).update(
            summary=summary,
            summary_updated_at=datetime.now(UTC),
        )

    async def soft_delete(self, session: ChatSession) -> ChatSession:
        """Delete a chat session row — 메시지는 FK 가 함께 지운다.

        ⚠️ 이름은 ``soft_delete`` 지만 **물리 삭제**다(QA-01, 2026-09-15).
        ``messages.session_id`` 가 ``ON DELETE CASCADE`` 라 세션을 지우면 그 세션의
        메시지도 DB 가 함께 지운다 — 호출자가 메시지를 따로 지울 필요가 없다.

        Args:
            session: Session to delete.

        Returns:
            ChatSession: The (now deleted) instance.
        """
        await ChatSession.filter(id=session.id).delete()
        return session

    async def bulk_soft_delete_by_account(self, account_id: UUID) -> int:
        """계정 소유의 모든 chat session 을 일괄 삭제한다.

        ⚠️ 이름과 달리 **물리 삭제**다(QA-01). 메시지는 FK CASCADE 가 함께 지운다.

        Args:
            account_id: 대상 계정 UUID.

        Returns:
            삭제된 row 수.
        """
        return await ChatSession.filter(account_id=account_id).delete()

    async def bulk_soft_delete_by_profile(self, profile_id: UUID) -> int:
        """프로필 단위 chat session 일괄 삭제 (Profile cascade 흐름).

        ⚠️ 이름과 달리 **물리 삭제**다(QA-01). 메시지는 FK CASCADE 가 함께 지운다.

        Args:
            profile_id: 대상 프로필 UUID.

        Returns:
            삭제된 row 수.
        """
        return await ChatSession.filter(profile_id=profile_id).delete()

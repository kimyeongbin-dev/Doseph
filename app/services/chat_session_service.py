"""Chat session service module.

This module provides business logic for chat session management operations
including creation, updates, and ownership verification.
"""

from uuid import UUID

from fastapi import HTTPException, status

from app.models.chat_sessions import ChatSession
from app.repositories.chat_session_repository import ChatSessionRepository
from app.repositories.message_repository import MessageRepository
from app.repositories.profile_repository import ProfileRepository


class ChatSessionService:
    """Chat session business logic service for conversation management."""

    def __init__(self) -> None:
        self.repository = ChatSessionRepository()
        self.profile_repository = ProfileRepository()
        self.message_repository = MessageRepository()

    async def _verify_profile_ownership(self, profile_id: UUID, account_id: UUID) -> None:
        """Verify profile ownership.

        Args:
            profile_id: Profile UUID to verify.
            account_id: Account UUID that should own the profile.

        Raises:
            HTTPException: If profile not found or access denied.
        """
        profile = await self.profile_repository.get_by_id(profile_id)
        if not profile:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Profile not found.",
            )
        if profile.account_id != account_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied to this profile.",
            )

    async def _verify_session_ownership(self, session: ChatSession, account_id: UUID) -> None:
        """Verify chat session ownership.

        Args:
            session: Chat session to verify ownership for.
            account_id: Account UUID that should own the session.

        Raises:
            HTTPException: If access denied to session.
        """
        if session.account_id != account_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied to this chat session.",
            )

    async def get_session(self, session_id: UUID) -> ChatSession:
        """Get chat session by ID.

        Args:
            session_id: Session UUID.

        Returns:
            ChatSession: Chat session object.

        Raises:
            HTTPException: If session not found.
        """
        session = await self.repository.get_by_id(session_id)
        if not session:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Chat session not found.",
            )
        return session

    async def get_session_with_owner_check(self, session_id: UUID, account_id: UUID) -> ChatSession:
        """Get chat session with ownership verification.

        Args:
            session_id: Session UUID.
            account_id: Account UUID for ownership check.

        Returns:
            ChatSession: Chat session if owned by account.
        """
        session = await self.get_session(session_id)
        await self._verify_session_ownership(session, account_id)
        return session

    async def get_sessions_by_account(self, account_id: UUID) -> list[ChatSession]:
        """Get all chat sessions for an account.

        Args:
            account_id: Account UUID.

        Returns:
            list[ChatSession]: List of chat sessions.
        """
        return await self.repository.get_all_by_account(account_id)

    async def get_sessions_by_profile(self, profile_id: UUID) -> list[ChatSession]:
        """Get chat sessions for a profile.

        Args:
            profile_id: Profile UUID.

        Returns:
            list[ChatSession]: List of chat sessions.
        """
        return await self.repository.get_by_profile(profile_id)

    async def get_sessions_by_profile_with_owner_check(self, profile_id: UUID, account_id: UUID) -> list[ChatSession]:
        """Get chat sessions for a profile with ownership verification.

        Args:
            profile_id: Profile UUID.
            account_id: Account UUID for ownership check.

        Returns:
            list[ChatSession]: List of chat sessions if profile is owned by account.
        """
        await self._verify_profile_ownership(profile_id, account_id)
        return await self.repository.get_by_profile(profile_id)

    async def create_session(
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
            ChatSession: Created chat session.
        """
        return await self.repository.create(
            account_id=account_id,
            profile_id=profile_id,
            title=title,
        )

    async def create_session_with_owner_check(
        self,
        account_id: UUID,
        profile_id: UUID,
        title: str | None = None,
    ) -> ChatSession:
        """Create chat session with ownership verification.

        Args:
            account_id: Account UUID.
            profile_id: Profile UUID.
            title: Optional session title.

        Returns:
            ChatSession: Created chat session if profile is owned by account.
        """
        await self._verify_profile_ownership(profile_id, account_id)
        return await self.create_session(
            account_id=account_id,
            profile_id=profile_id,
            title=title,
        )

    async def update_session_title(self, session_id: UUID, title: str) -> ChatSession:
        """Update chat session title.

        Args:
            session_id: Session UUID.
            title: New session title.

        Returns:
            ChatSession: Updated chat session.
        """
        session = await self.get_session(session_id)
        return await self.repository.update(session, title=title)

    async def update_session_title_with_owner_check(
        self,
        session_id: UUID,
        account_id: UUID,
        title: str,
    ) -> ChatSession:
        """Update chat session title after ownership verification.

        Args:
            session_id: Session UUID.
            account_id: Account UUID required to own the session.
            title: New session title (caller is expected to have validated
                length/whitespace via the DTO).

        Returns:
            ChatSession: Updated chat session.

        Raises:
            HTTPException: 404 if session not found, 403 if not owned by account.
        """
        session = await self.get_session_with_owner_check(session_id, account_id)
        return await self.repository.update(session, title=title)

    # ── 세션 삭제 (FK CASCADE) ─────────────────────────────────────────
    # 흐름: 세션 행 삭제 -> messages.session_id 의 ON DELETE CASCADE 가 메시지 삭제
    # 트랜잭션으로 묶던 2단계 처리는 QA-01 에서 제거됐다 — DB 가 원자적으로 한다.

    async def delete_session(self, session_id: UUID) -> None:
        """Delete a chat session — 자식 메시지는 FK 가 함께 지운다.

        Args:
            session_id: Session UUID to delete.
        """
        session = await self.get_session(session_id)
        # 메시지는 FK(messages.session_id ON DELETE CASCADE)가 함께 지운다.
        # 손으로 한 번 더 지우던 코드를 제거했다(QA-01) — 같은 일을 두 번 하면
        # 두 경로가 어긋날 때 조용한 불일치가 생긴다.
        await self.repository.soft_delete(session)

    async def delete_session_with_owner_check(self, session_id: UUID, account_id: UUID) -> None:
        """Delete a chat session with ownership verification — 메시지는 FK 가 함께 지운다.

        Args:
            session_id: Session UUID to delete.
            account_id: Account UUID for ownership check.
        """
        session = await self.get_session_with_owner_check(session_id, account_id)
        # 메시지는 FK CASCADE 가 함께 지운다(위 delete_session 주석 참조).
        await self.repository.soft_delete(session)

"""Account repository module.

This module provides data access layer for the accounts table,
handling social login account management operations.
"""

from uuid import UUID, uuid4

from app.models.accounts import Account, AuthProvider


class AccountRepository:
    """Account database repository for social login management."""

    async def get_by_provider(self, provider: AuthProvider, provider_account_id: str) -> Account | None:
        """Get account by social login provider information.

        Args:
            provider: Authentication provider.
            provider_account_id: Provider account ID.

        Returns:
            Account | None: Account if found, None otherwise.
        """
        return await Account.filter(
            auth_provider=provider,
            provider_account_id=provider_account_id,
        ).first()

    async def get_by_id(self, account_id: UUID) -> Account | None:
        """Get account by ID.

        Args:
            account_id: Account UUID.

        Returns:
            Account | None: Account if found, None otherwise.
        """
        return await Account.filter(
            id=account_id,
        ).first()

    async def create(
        self,
        provider: AuthProvider,
        provider_account_id: str,
        nickname: str,
        profile_image_url: str | None = None,
    ) -> Account:
        """Create new account.

        Args:
            provider: Authentication provider.
            provider_account_id: Provider account ID.
            nickname: User nickname.
            profile_image_url: Optional profile image URL.

        Returns:
            Account: Created account.
        """
        return await Account.create(
            id=uuid4(),
            auth_provider=provider,
            provider_account_id=provider_account_id,
            nickname=nickname,
            profile_image_url=profile_image_url,
            is_active=True,
        )

    async def update_login_info(
        self,
        account: Account,
        nickname: str,
        profile_image_url: str | None = None,
    ) -> Account:
        """Update account with latest login information.

        Args:
            account: Account to update.
            nickname: Updated nickname.
            profile_image_url: Updated profile image URL.

        Returns:
            Account: Updated account.
        """
        account.nickname = nickname
        account.profile_image_url = profile_image_url
        await account.save()
        return account

    async def deactivate(self, account: Account) -> Account:
        """Deactivate account.

        Args:
            account: Account to deactivate.

        Returns:
            Account: Deactivated account.
        """
        account.is_active = False
        await account.save()
        return account

    async def delete(self, account: Account) -> None:
        """Delete an account row — 자식은 FK CASCADE 가 함께 지운다.

        탈퇴는 폐기가 아니라 **erasure** 다(QA-01/QA-02, 2026-09-15).
        ``accounts`` 를 참조하는 FK(profiles · chat_sessions · refresh_tokens)가
        ``ON DELETE CASCADE`` 이므로 이 한 줄이 계정 이하 전부를 정리한다.

        이전에는 ``is_active=False`` + ``deleted_at`` 으로 행을 남겼는데,
        ``UNIQUE(auth_provider, provider_account_id)`` 때문에 **같은 신원으로 재가입이
        불가능**했다(2026-09-15 테스트로 실증 — UniqueViolationError).
        행을 지우면 제약이 풀려 정상 재가입이 된다.

        Args:
            account: 삭제 대상 Account.
        """
        await Account.filter(id=account.id).delete()

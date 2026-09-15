"""Refresh token repository module.

This module provides data access layer for refresh token storage and management.
Stores SHA-256 hash values only (not original tokens) for security.
Supports RTR (Refresh Token Rotation) with Grace Period for concurrent requests.
"""

from datetime import datetime, timedelta
import hashlib
from uuid import UUID

from tortoise.expressions import Q

from app.core import config
from app.models.refresh_tokens import RefreshToken

# Grace Period: Handle concurrent requests (old token temporarily valid after RTR)
GRACE_PERIOD_SECONDS = 2


class RefreshTokenRepository:
    """Refresh token database repository with RTR and Grace Period support."""

    @staticmethod
    def _hash_token(token: str) -> str:
        """Convert token to SHA-256 hash.

        Args:
            token: Original token string.

        Returns:
            str: SHA-256 hash of token.
        """
        return hashlib.sha256(token.encode()).hexdigest()

    async def create(self, account_id: UUID, token: str) -> RefreshToken:
        """Store new refresh token.

        Args:
            account_id: Account UUID.
            token: Refresh token string.

        Returns:
            RefreshToken: Created token record.
        """
        token_hash = self._hash_token(token)
        expires_at = datetime.now(tz=config.TIMEZONE) + timedelta(minutes=config.REFRESH_TOKEN_EXPIRE_MINUTES)

        return await RefreshToken.create(
            account_id=account_id,
            token_hash=token_hash,
            expires_at=expires_at,
            is_revoked=False,
        )

    async def get_by_token(self, token: str) -> RefreshToken | None:
        """Get token by token string (valid tokens only).

        Args:
            token: Token string to search for.

        Returns:
            RefreshToken | None: Token record if found and valid, None otherwise.
        """
        token_hash = self._hash_token(token)
        return await RefreshToken.filter(
            token_hash=token_hash,
            is_revoked=False,
            expires_at__gt=datetime.now(tz=config.TIMEZONE),
        ).first()

    async def validate_with_grace(self, token: str) -> tuple[RefreshToken | None, bool]:
        """Validate token considering Grace Period.

        Args:
            token: Token string to validate.

        Returns:
            tuple[RefreshToken | None, bool]: (token_record, is_valid)
            - (token, True): Valid token
            - (token, True): RTR'd but within Grace Period (valid)
            - (token, False): Grace Period exceeded (suspected theft)
            - (None, False): Token not found
        """
        token_hash = self._hash_token(token)
        now = datetime.now(tz=config.TIMEZONE)

        # 1. Find token by hash (regardless of revoked status)
        refresh_token = await RefreshToken.filter(token_hash=token_hash).first()

        if not refresh_token:
            return None, False

        # 2. Check expiration
        if refresh_token.expires_at < now:
            return refresh_token, False

        # 3. Not yet revoked token → valid
        if not refresh_token.is_revoked:
            return refresh_token, True

        # 4. Revoked token → check Grace Period
        if refresh_token.rotated_at:
            grace_deadline = refresh_token.rotated_at + timedelta(seconds=GRACE_PERIOD_SECONDS)
            if now <= grace_deadline:
                # Within Grace Period → valid (allow concurrent requests)
                return refresh_token, True

        # 5. Grace Period exceeded → suspected theft
        return refresh_token, False

    async def rotate(self, old_token: str, account_id: UUID, new_token: str) -> tuple[RefreshToken | None, bool]:
        """Rotate token (RTR) with optimistic locking to prevent race conditions.

        1. Invalidate old token only if not yet revoked
        2. Create new token
        3. Record replaced_by_id in old token

        Args:
            old_token: Token to replace.
            account_id: Account UUID.
            new_token: New token string.

        Returns:
            tuple[RefreshToken | None, bool]: (new_token, success)
            - (new_token, True): Normal rotation
            - (None, False): Already rotated by another request (Race Condition)
        """
        old_token_hash = self._hash_token(old_token)
        now = datetime.now(tz=config.TIMEZONE)

        # 1. Optimistic locking: update only if is_revoked=False
        updated = await RefreshToken.filter(
            token_hash=old_token_hash,
            is_revoked=False,  # Only not yet revoked tokens
        ).update(
            is_revoked=True,
            rotated_at=now,
        )

        # Already rotated by another request
        if updated == 0:
            return None, False

        # 2. Create new token
        new_refresh_token = await self.create(account_id, new_token)

        # 3. Update replaced_by_id (for tracking)
        await RefreshToken.filter(token_hash=old_token_hash).update(
            replaced_by_id=new_refresh_token.id,
        )

        return new_refresh_token, True

    async def revoke(self, token: str) -> bool:
        """Revoke token (logout).

        Args:
            token: Token to revoke.

        Returns:
            bool: True if token was revoked, False if not found.
        """
        token_hash = self._hash_token(token)
        updated = await RefreshToken.filter(
            token_hash=token_hash,
            is_revoked=False,
        ).update(is_revoked=True)
        return updated > 0

    async def delete_all_for_account(self, account_id: UUID) -> int:
        """Hard-delete every refresh token row of an account (withdrawal only).

        ⚠️ 이름 그대로 **행을 지운다**. 이전에는 ``revoke_all_for_account`` 가
        ``is_revoked=True`` 로 표시만 했는데, 호출처의 주석은 *"hard-delete (보안 우선)"*
        이라 **주석과 실제가 달랐다**(QA-02, 2026-09-15 DB 테스트가 발견).

        왜 탈퇴만 hard delete 인가:
            **폐기(revocation)와 계정 삭제(erasure)는 다른 동작이다.**
            운영 중 개별 토큰 폐기는 감사 추적이 필요해 행을 남기는 게 타당하다
            (``revoke`` 는 그대로 둔다). 반면 탈퇴는 GDPR Art.17 "잊힐 권리" +
            데이터 최소화의 영역이라, **재사용 가능한 비밀(token_hash)을 남기면 안 된다.**

        Args:
            account_id: Account UUID.

        Returns:
            int: Number of rows deleted.
        """
        return await RefreshToken.filter(account_id=account_id).delete()

    async def cleanup_expired_tokens(self, days_old: int = 7) -> int:
        """Clean up expired tokens (prevent database bloat).

        Deletes tokens that are:
        - Past expires_at timestamp
        - Revoked and rotated_at is older than days_old

        Recommended to run periodically (cron job or scheduler).

        Args:
            days_old: Days threshold for cleanup.

        Returns:
            int: Number of tokens deleted.
        """
        cutoff = datetime.now(tz=config.TIMEZONE) - timedelta(days=days_old)

        # Condition: expired tokens OR (revoked and old rotated_at)
        deleted = await RefreshToken.filter(
            Q(expires_at__lt=cutoff) | Q(is_revoked=True, rotated_at__lt=cutoff)
        ).delete()

        return deleted

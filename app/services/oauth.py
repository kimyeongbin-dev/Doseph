"""OAuth authentication service module.

This module provides OAuth authentication services for social login providers.
Supports both development/test environments with mock servers and production
environments with actual provider servers. Follows modern async patterns.
"""

from datetime import datetime
import logging
from typing import Any
from uuid import uuid4

from fastapi import HTTPException, status
import httpx
from tortoise.transactions import in_transaction

from app.core import config
from app.core.config import Env
from app.core.http_client import get_http_client
from app.core.logger import log_boundary
from app.models.accounts import Account, AuthProvider
from app.models.profiles import Gender, Profile, RelationType
from app.repositories.account_repository import AccountRepository
from app.repositories.chat_session_repository import ChatSessionRepository
from app.repositories.message_repository import MessageRepository
from app.repositories.profile_repository import ProfileRepository
from app.repositories.refresh_token_repository import RefreshTokenRepository
from app.services.profile_service import ProfileService
from app.services.rate_limiter import RateLimiter
from app.utils.jwt.tokens import AccessToken, RefreshToken

logger = logging.getLogger(__name__)


class OAuthService:
    """OAuth authentication service.

    Handles OAuth authentication flow for social login providers.
    Supports both mock servers for development and actual provider servers
    for production environments with modern async patterns.
    """

    def __init__(
        self,
        account_repo: AccountRepository | None = None,
        refresh_token_repo: RefreshTokenRepository | None = None,
        rate_limiter: RateLimiter | None = None,
    ) -> None:
        """Initialize OAuth service with repositories and rate limiter.

        Args:
            account_repo: Account repository instance.
            refresh_token_repo: Refresh token repository instance.
            rate_limiter: Rate limiter instance.
        """
        self.account_repo = account_repo or AccountRepository()
        self.refresh_token_repo = refresh_token_repo or RefreshTokenRepository()
        self.rate_limiter = rate_limiter
        # 회원탈퇴 cascade 의존
        self.profile_repo = ProfileRepository()
        self.profile_service = ProfileService()
        self.chat_session_repo = ChatSessionRepository()
        self.message_repo = MessageRepository()

        if config.ENV == Env.LOCAL:
            # Local: Use mock server (for development convenience)
            # When backend calls itself (mock server) in Docker environment,
            # use API_BASE_URL for direct internal network communication
            base_url = config.API_BASE_URL
            self.kakao_token_url = f"{base_url}/api/v1/mock/kakao/oauth/token"
            self.kakao_userinfo_url = f"{base_url}/api/v1/mock/kakao/v2/user/me"
        else:
            # Dev/prod: Use actual Kakao server
            self.kakao_token_url = "https://kauth.kakao.com/oauth/token"
            self.kakao_userinfo_url = "https://kapi.kakao.com/v2/user/me"

    def _check_rate_limit(self, client_ip: str) -> None:
        """Check rate limit if rate limiter is injected.

        Args:
            client_ip: Client IP address for rate limiting.
        """
        if self.rate_limiter:
            self.rate_limiter.check(client_ip)

    async def _exchange_code_for_token(self, code: str) -> dict[str, str]:
        """Exchange authorization code for access token from Kakao (or mock) server.

        Args:
            code: Authorization code from OAuth provider.

        Returns:
            dict[str, str]: Token response from provider.

        Raises:
            HTTPException: If token exchange fails.
        """
        data = {
            "grant_type": "authorization_code",
            "client_id": config.KAKAO_CLIENT_ID,
            "client_secret": config.KAKAO_CLIENT_SECRET,
            "redirect_uri": config.KAKAO_REDIRECT_URI,
            "code": code.strip(),
        }

        # 공유 클라이언트 재사용(커넥션 풀). secret 은 client 기본값 아닌 요청별로 전달.
        client = get_http_client()
        try:
            # 경계 계측: 실패(예: KOE320)가 HTTPException 번역 전에 서버 로그에 남도록.
            async with log_boundary(logger, "kakao_token_exchange", url=self.kakao_token_url):
                response = await client.post(self.kakao_token_url, data=data)
                response.raise_for_status()
                return response.json()
        except httpx.HTTPStatusError as e:
            error_detail = e.response.json() if e.response.content else {"error": "token_exchange_failed"}
            raise HTTPException(
                status_code=e.response.status_code,
                detail=error_detail,
            ) from e
        except httpx.RequestError as e:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail={
                    "error": "network_error",
                    "error_description": "Cannot communicate with authentication server. Please try again later.",
                },
            ) from e

    async def _get_user_info(self, access_token: str) -> dict[str, Any]:
        """Get user information from Kakao (or mock) server using access token.

        Args:
            access_token: Access token from OAuth provider.

        Returns:
            dict[str, Any]: User information from provider.

        Raises:
            HTTPException: If user info retrieval fails.
        """
        headers = {
            "Authorization": f"Bearer {access_token.strip()}",
            "Content-type": "application/x-www-form-urlencoded;charset=utf-8",
        }

        # 공유 클라이언트 재사용(커넥션 풀). access_token 은 요청별 헤더로만 전달.
        client = get_http_client()
        try:
            # 경계 계측: 토큰 만료/권한 실패가 HTTPException 번역 전에 서버 로그에 남도록.
            async with log_boundary(logger, "kakao_userinfo", url=self.kakao_userinfo_url):
                response = await client.get(self.kakao_userinfo_url, headers=headers)
                response.raise_for_status()
                return response.json()
        except httpx.HTTPStatusError as e:
            error_detail = e.response.json() if e.response.content else {"error": "userinfo_failed"}
            raise HTTPException(
                status_code=e.response.status_code,
                detail=error_detail,
            ) from e
        except httpx.RequestError as e:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail={
                    "error": "network_error",
                    "error_description": "Cannot communicate with user info server.",
                },
            ) from e

    async def kakao_callback(self, code: str, client_ip: str) -> tuple[Account, bool]:
        """Process Kakao OAuth callback.

        1. Exchange authorization code for access token
        2. Get user information with access token
        3. Create account or handle login

        Args:
            code: Authorization code from Kakao.
            client_ip: Client IP address for rate limiting.

        Returns:
            tuple[Account, bool]: (account, is_new_user)

        Raises:
            HTTPException: If authentication process fails.
        """
        self._check_rate_limit(client_ip)

        # 1. 인가 코드로 액세스 토큰 교환
        token_data = await self._exchange_code_for_token(code)
        kakao_access_token = token_data["access_token"]

        # 2. 액세스 토큰으로 사용자 정보 조회
        user_info = await self._get_user_info(kakao_access_token)

        # Parse user information
        provider_account_id = str(user_info["id"])
        kakao_account = user_info.get("kakao_account", {})
        profile = kakao_account.get("profile", {})
        nickname = profile.get("nickname", f"KakaoUser_{provider_account_id[:4]}")
        profile_image_url = profile.get("profile_image_url")

        # 3. Query database account
        account = await self.account_repo.get_by_provider(
            provider=AuthProvider.KAKAO,
            provider_account_id=provider_account_id,
        )

        is_new_user = False

        if account:
            # Existing account - check active status
            if not account.is_active:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail={
                        "error": "account_disabled",
                        "error_description": "Account is disabled. Please contact customer service.",
                    },
                )

            # Update with latest information
            await self.account_repo.update_login_info(
                account=account,
                nickname=nickname,
                profile_image_url=profile_image_url,
            )
        else:
            # Create new account
            account = await self.account_repo.create(
                provider=AuthProvider.KAKAO,
                provider_account_id=provider_account_id,
                nickname=nickname,
                profile_image_url=profile_image_url,
            )
            is_new_user = True

        # SELF 프로필 자동 생성 (idempotent — 신규 가입 + 기존 사용자 누락분 backfill)
        await self._ensure_self_profile(account, nickname=nickname)

        return account, is_new_user

    # ── SELF 프로필 자동 생성 (회원가입 흐름 공용) ─────────────────────
    # 흐름: 기존 SELF 조회 -> 없으면 INSERT (idempotent)
    # 회원가입 직후 main 페이지 진입 시 ProfileContext 가 빈 배열을 받지
    # 않도록 보장. 기존 사용자가 어떤 사유로든 SELF 가 없는 경우에도 다음
    # 로그인 시 자동 backfill.

    async def _ensure_self_profile(
        self,
        account: Account,
        *,
        nickname: str,
        gender: Gender | None = None,
        health_survey: dict[str, Any] | None = None,
    ) -> None:
        """계정에 SELF 프로필이 없으면 생성. 이미 있으면 no-op.

        Args:
            account: 대상 Account.
            nickname: SELF 프로필 이름 베이스 (카카오 닉네임 또는 dev nickname).
            gender: SELF 의 성별. dev_login 은 'MALE', 카카오는 None (사용자
                추후 mypage 에서 입력) — SELF 는 RELATION_DEFAULT_GENDER 미적용.
            health_survey: 초기 health_survey JSON (dev 한정 — 운영 카카오는 None).
        """
        existing = await Profile.filter(
            account_id=account.id,
            relation_type=RelationType.SELF,
            deleted_at__isnull=True,
        ).first()
        if existing:
            return

        # name max_length=32 — 카카오 닉네임이 그보다 길 수도 있어 truncate 가드
        await Profile.create(
            id=uuid4(),
            account_id=account.id,
            name=(nickname or "사용자")[:32],
            relation_type=RelationType.SELF,
            gender=gender,
            health_survey=health_survey,
        )
        logger.info("[OAUTH] SELF profile auto-created account_id=%s nickname=%s", account.id, nickname)

    async def issue_tokens(self, account: Account) -> dict[str, str]:
        """Issue JWT tokens and store refresh token in database.

        Args:
            account: User account for token issuance.

        Returns:
            dict[str, str]: Dictionary containing access_token and refresh_token.
        """
        # Create Access Token
        access_token = AccessToken()
        access_token["sub"] = str(account.id)
        access_token["provider"] = account.auth_provider

        # Create Refresh Token
        refresh_token = RefreshToken()
        refresh_token["sub"] = str(account.id)

        refresh_token_str = str(refresh_token)

        # Store Refresh Token in database
        await self.refresh_token_repo.create(
            account_id=account.id,
            token=refresh_token_str,
        )

        return {
            "access_token": str(access_token),
            "refresh_token": refresh_token_str,
        }

    async def refresh_access_token(self, refresh_token_str: str) -> dict[str, str]:
        """RTR (Refresh Token Rotation) 흐름 — 검증 → 계정조회 → 새 토큰 → 회전.

        Returns:
            ``{"access_token": "...", "refresh_token": "..."}``.

        Raises:
            HTTPException: 401 토큰 만료/무효, 403 탈취/비활성, 409 race rotation.
        """
        db_token = await self._validate_refresh_token_or_raise(refresh_token_str)
        account = await self._load_active_account_or_raise(db_token.account_id)
        new_access, new_refresh_str = self._mint_token_pair(account)
        await self._rotate_or_409(refresh_token_str, account, new_refresh_str)
        return {"access_token": str(new_access), "refresh_token": new_refresh_str}

    async def _validate_refresh_token_or_raise(self, refresh_token_str: str) -> Any:
        """Grace-period 검증 후 ``RefreshTokenRow`` 를 반환. 위반 시 401/403."""
        db_token, is_valid = await self.refresh_token_repo.validate_with_grace(refresh_token_str)
        if not db_token:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={"error": "invalid_token", "error_description": "유효하지 않은 토큰입니다."},
            )
        if not is_valid:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={"error": "token_compromised", "error_description": "보안을 위해 재로그인이 필요합니다."},
            )
        return db_token

    async def _load_active_account_or_raise(self, account_id: Any) -> Account:
        """``account_id`` 로 계정 조회 + 활성 여부 확인. 위반 시 403."""
        account = await self.account_repo.get_by_id(account_id)
        if not account or not account.is_active:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={"error": "account_disabled", "error_description": "비활성화된 계정입니다."},
            )
        return account

    @staticmethod
    def _mint_token_pair(account: Account) -> tuple[AccessToken, str]:
        """Access + Refresh 새 토큰을 만들어 (access_token_obj, refresh_str) 반환."""
        new_access = AccessToken()
        new_access["sub"] = str(account.id)
        new_access["provider"] = account.auth_provider
        new_refresh = RefreshToken()
        new_refresh["sub"] = str(account.id)
        return new_access, str(new_refresh)

    async def _rotate_or_409(self, old_token: str, account: Account, new_refresh_str: str) -> None:
        """RTR rotate 호출 — race condition 시 409 로 명시적 안내."""
        _new_db_token, success = await self.refresh_token_repo.rotate(
            old_token=old_token,
            account_id=account.id,
            new_token=new_refresh_str,
        )
        if not success:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "error": "token_already_rotated",
                    "error_description": "토큰이 이미 갱신되었습니다. 잠시 후 다시 시도해주세요.",
                },
            )

    async def revoke_refresh_token(self, token: str) -> bool:
        """Refresh Token 무효화 (로그아웃)"""
        return await self.refresh_token_repo.revoke(token)

    # ── 회원탈퇴 (cascade soft-delete) ────────────────────────────────
    # 흐름: refresh_tokens hard -> profiles cascade (medication/challenge/session/...)
    #       -> account 의 직접 chat_sessions soft + messages soft
    #       -> account 비활성화 + deleted_at = now() (단일 트랜잭션)
    # SELF guard 우회: profile_service._cascade_delete_profile 직접 호출.

    async def delete_account(self, account: Account) -> bool:
        """회원 탈퇴 — 자식 모두 cascade.

        Args:
            account: 탈퇴 대상 Account.

        Returns:
            True (성공 시).

        Raises:
            HTTPException: 500 — cascade 도중 예외.
        """
        try:
            # 회원의 chat_sessions 미리 수집 (messages cascade 용)
            account_sessions = await self.chat_session_repo.get_all_by_account(account.id)
            profiles = await self.profile_repo.get_all_by_account(account.id)

            async with in_transaction():
                # 1) refresh_tokens hard-delete (보안 우선)
                await self.refresh_token_repo.revoke_all_for_account(account.id)

                # 2) profiles cascade — SELF 포함 모두 (회원탈퇴는 SELF guard 우회)
                for profile in profiles:
                    await self.profile_service.cascade_delete_profile(profile)

                # 3) account 의 직접 chat_sessions soft + 그 messages soft
                #    profile_id 만 가진 세션은 이미 위 cascade 에서 처리됨.
                await self.chat_session_repo.bulk_soft_delete_by_account(account.id)
                for session in account_sessions:
                    await self.message_repo.bulk_soft_delete_by_session(session.id)

                # 4) 계정 비활성화 + deleted_at
                await self.account_repo.deactivate(account)
                if hasattr(account, "deleted_at"):
                    account.deleted_at = datetime.now(config.TIMEZONE)
                    await account.save()

            return True
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail={"error": "delete_failed", "error_description": "회원 탈퇴 처리 중 오류가 발생했습니다."},
            ) from e

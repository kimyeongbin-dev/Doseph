"""하이브리드 인증 회귀 테스트 (로드맵 ④).

웹=HttpOnly 쿠키 / 앱=Bearer. 응답 형식은 자격증명 도착방식(refresh·logout) 또는
명시신호(callback=`X-Client-Type: native`)로 결정한다:
- 쿠키 모드: Set-Cookie 로만 발급(토큰을 body 에 노출하지 않음 — XSS 방어 유지).
- 앱 모드: body 로 토큰 발급, 쿠키 미설정.
읽기 경로(`_extract_token`)는 이미 하이브리드 — 회귀 가드.
"""

import types

from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials
from httpx import AsyncClient
import pytest

from app.apis.v1.oauth_routers import _generate_state, get_oauth_service
from app.dependencies.security import _extract_token
from app.main import app


class _FakeOAuthService:
    """라우터의 I/O 형식만 검증하기 위한 최소 목(서비스/DB 우회)."""

    def __init__(self) -> None:
        self.revoked: list[str] = []

    async def kakao_callback(self, code: str, client_ip: str) -> tuple[object, bool]:
        return (object(), False)  # (account, is_new_user)

    async def issue_tokens(self, account: object) -> dict[str, str]:
        return {"access_token": "acc_tok", "refresh_token": "ref_tok"}

    async def refresh_access_token(self, refresh_token: str) -> dict[str, str]:
        return {"access_token": "new_acc", "refresh_token": "new_ref"}

    async def revoke_refresh_token(self, refresh_token: str) -> None:
        self.revoked.append(refresh_token)


@pytest.fixture
def fake_oauth() -> _FakeOAuthService:
    """get_oauth_service 를 최소 목으로 오버라이드(라우터 I/O 형식만 검증)."""
    fake = _FakeOAuthService()
    app.dependency_overrides[get_oauth_service] = lambda: fake
    yield fake
    app.dependency_overrides.pop(get_oauth_service, None)


class TestExtractTokenHybrid:
    """읽기 경로: 쿠키 우선 → Bearer 폴백 (이미 구현, 회귀 가드)."""

    def test_cookie_takes_priority(self) -> None:
        request = types.SimpleNamespace(cookies={"access_token": "cook_tok"})
        cred = HTTPAuthorizationCredentials(scheme="Bearer", credentials="hdr_tok")
        assert _extract_token(request, cred) == "cook_tok"

    def test_bearer_fallback_when_no_cookie(self) -> None:
        request = types.SimpleNamespace(cookies={})
        cred = HTTPAuthorizationCredentials(scheme="Bearer", credentials="hdr_tok")
        assert _extract_token(request, cred) == "hdr_tok"

    def test_raises_401_when_neither(self) -> None:
        request = types.SimpleNamespace(cookies={})
        with pytest.raises(HTTPException) as exc:
            _extract_token(request, None)
        assert exc.value.status_code == 401


class TestRefreshHybrid:
    """refresh: 쿠키 유무로 웹/앱 자동 판별."""

    @pytest.mark.asyncio
    async def test_refresh_cookie_mode_sets_cookie_no_body_refresh(
        self, client: AsyncClient, fake_oauth: _FakeOAuthService
    ) -> None:
        """웹(쿠키) 모드: Set-Cookie 회전 + body access_token, body 에 refresh_token 없음."""
        response = await client.post("/api/v1/auth/refresh", cookies={"refresh_token": "old_ref"})

        assert response.status_code == 200
        body = response.json()
        assert body["access_token"] == "new_acc"
        assert "refresh_token" not in body
        assert any("access_token=" in h for h in response.headers.get_list("set-cookie"))

    @pytest.mark.asyncio
    async def test_refresh_bearer_mode_returns_body_tokens_no_cookie(
        self, client: AsyncClient, fake_oauth: _FakeOAuthService
    ) -> None:
        """앱(Bearer) 모드: 쿠키 없이 Authorization 헤더 → body 에 access+refresh, Set-Cookie 없음."""
        response = await client.post(
            "/api/v1/auth/refresh",
            headers={"Authorization": "Bearer old_ref"},
        )

        assert response.status_code == 200
        body = response.json()
        assert body["access_token"] == "new_acc"
        assert body["refresh_token"] == "new_ref"
        assert not response.headers.get_list("set-cookie")


class TestCallbackHybrid:
    """callback: X-Client-Type: native 신호로 웹/앱 분기(최초 로그인은 쿠키가 없어 도착방식 불가)."""

    @pytest.mark.asyncio
    async def test_callback_web_sets_cookie_no_body_tokens(
        self, client: AsyncClient, fake_oauth: _FakeOAuthService
    ) -> None:
        """웹(기본): 쿠키 발급, body 에 토큰 노출 안 함."""
        state = _generate_state()
        response = await client.get(
            "/api/v1/auth/kakao/callback",
            params={"code": "authcode", "state": state},
        )

        assert response.status_code == 200
        body = response.json()
        assert "access_token" not in body
        assert any("access_token=" in h for h in response.headers.get_list("set-cookie"))

    @pytest.mark.asyncio
    async def test_callback_native_returns_body_tokens_no_cookie(
        self, client: AsyncClient, fake_oauth: _FakeOAuthService
    ) -> None:
        """앱(X-Client-Type: native): body 에 토큰, 쿠키 미설정."""
        state = _generate_state()
        response = await client.get(
            "/api/v1/auth/kakao/callback",
            params={"code": "authcode", "state": state},
            headers={"X-Client-Type": "native"},
        )

        assert response.status_code == 200
        body = response.json()
        assert body["access_token"] == "acc_tok"
        assert body["refresh_token"] == "ref_tok"
        assert not response.headers.get_list("set-cookie")


class TestLogoutHybrid:
    """logout: 쿠키 없으면 Authorization 헤더의 refresh 로 폐기."""

    @pytest.mark.asyncio
    async def test_logout_bearer_mode_revokes_header_token(
        self, client: AsyncClient, fake_oauth: _FakeOAuthService
    ) -> None:
        response = await client.post(
            "/api/v1/auth/logout",
            headers={"Authorization": "Bearer app_ref"},
        )

        assert response.status_code == 204
        assert "app_ref" in fake_oauth.revoked

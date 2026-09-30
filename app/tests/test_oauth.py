"""OAuth 인증 API 테스트"""

from httpx import AsyncClient
import pytest


class TestKakaoOAuthConfig:
  """카카오 OAuth 설정 조회 테스트"""

  @pytest.mark.asyncio
  async def test_get_kakao_config_success(self, client: AsyncClient) -> None:
    """카카오 OAuth 설정 조회 성공"""
    response = await client.get("/api/v1/auth/kakao/config")

    assert response.status_code == 200
    data = response.json()
    assert "client_id" in data
    assert "redirect_uri" in data
    assert "authorize_url" in data
    assert "state" in data

  @pytest.mark.asyncio
  async def test_kakao_config_state_format(self, client: AsyncClient) -> None:
    """State 값이 HMAC 서명 형식인지 확인"""
    response = await client.get("/api/v1/auth/kakao/config")

    data = response.json()
    state = data["state"]
    # state 형식: {timestamp}.{nonce}.{signature}
    parts = state.split(".")
    assert len(parts) == 3


class TestKakaoCallback:
  """카카오 콜백 테스트"""

  @pytest.mark.asyncio
  async def test_callback_without_code(self, client: AsyncClient) -> None:
    """Code 없이 콜백 호출 시 400 에러"""
    response = await client.get("/api/v1/auth/kakao/callback")

    assert response.status_code == 400
    data = response.json()
    assert data["detail"]["error"] == "invalid_request"

  @pytest.mark.asyncio
  async def test_callback_with_invalid_state(self, client: AsyncClient) -> None:
    """잘못된 state로 콜백 호출 시 400 에러"""
    response = await client.get(
      "/api/v1/auth/kakao/callback",
      params={"code": "test_code", "state": "invalid_state"},
    )

    assert response.status_code == 400
    data = response.json()
    assert data["detail"]["error"] == "invalid_state"

  @pytest.mark.asyncio
  async def test_callback_with_kakao_error(self, client: AsyncClient) -> None:
    """카카오에서 에러 응답 시 400 에러"""
    response = await client.get(
      "/api/v1/auth/kakao/callback",
      params={"error": "access_denied", "error_description": "User denied"},
    )

    assert response.status_code == 400
    data = response.json()
    assert data["detail"]["error"] == "access_denied"


class TestTokenRefresh:
  """토큰 갱신 테스트"""

  @pytest.mark.asyncio
  async def test_refresh_without_token(self, client: AsyncClient) -> None:
    """Refresh token 없이 갱신 시도 시 401 에러"""
    response = await client.post("/api/v1/auth/refresh")

    assert response.status_code == 401
    data = response.json()
    assert data["detail"]["error"] == "missing_token"


class TestLogout:
  """로그아웃 테스트"""

  @pytest.mark.asyncio
  async def test_logout_without_token(self, client: AsyncClient) -> None:
    """토큰 없이 로그아웃 시 성공 (204)"""
    response = await client.post("/api/v1/auth/logout")

    # 토큰 없어도 로그아웃은 성공 처리
    assert response.status_code == 204

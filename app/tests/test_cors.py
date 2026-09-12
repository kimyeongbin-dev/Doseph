"""CORS 패리티 회귀 테스트 (로컬 독립 API 전환 ④).

로컬 FE(:3000)가 fastapi(:8000)를 cross-origin 으로 직접 호출 → preflight(OPTIONS) +
credentialed 경로가 실제로 동작해야 한다. nginx same-origin 프록시 제거 후 이 경로가
유일한 진입이므로, 허용 오리진 echo + credentials 허용을 가드한다.
"""

from httpx import AsyncClient
import pytest


class TestCorsParity:
    """cross-origin credentialed 요청 경로 가드."""

    @pytest.mark.asyncio
    async def test_preflight_allows_localhost_3000_with_credentials(self, client: AsyncClient) -> None:
        """허용 오리진(:3000) preflight → ACAO echo + ACAC true."""
        response = await client.options(
            "/api/v1/auth/refresh",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "POST",
            },
        )

        assert response.status_code in (200, 204)
        assert response.headers.get("access-control-allow-origin") == "http://localhost:3000"
        assert response.headers.get("access-control-allow-credentials") == "true"

    @pytest.mark.asyncio
    async def test_preflight_disallowed_origin_not_echoed(self, client: AsyncClient) -> None:
        """허용 안 된 오리진은 ACAO 로 echo 되지 않아야 한다(자격증명 유출 방지)."""
        response = await client.options(
            "/api/v1/auth/refresh",
            headers={
                "Origin": "http://evil.example.com",
                "Access-Control-Request-Method": "POST",
            },
        )

        assert response.headers.get("access-control-allow-origin") != "http://evil.example.com"

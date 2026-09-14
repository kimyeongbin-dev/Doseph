"""Mock OAuth API router module.

This module provides mock implementations of Kakao OAuth endpoints
for development and testing purposes.
"""

import json
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, Form, Header, HTTPException, Query, status
from fastapi.responses import RedirectResponse

from app.core import config
from app.core.config import Env


# ── mock IdP 접근 차단 가드 (fail-closed) ─────────────────────────────
# 흐름: 요청 진입 -> ENV 확인 -> local 이 아니면 404
# 이 라우터는 카카오를 대신해 "이 사용자는 정상"이라고 우리 서버가 선언하는 테스트 대역이다.
# 노출되면 인증 우회로 직결되므로, 등록 단계 게이팅(app/apis/v1/__init__.py)에 더해
# 핸들러 단에서도 스스로 막는다. 등록 로직이 바뀌거나 실수로 포함돼도 서비스되지 않는다.
# 존재 자체를 알리지 않도록 403 이 아닌 404 를 반환한다.
def _local_only() -> None:
    """Reject any request when the app is not running in the local environment.

    Raises:
        HTTPException: 404 if the current environment is not local.
    """
    if config.ENV != Env.LOCAL:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not Found")


mock_router = APIRouter(
    prefix="/mock/kakao",
    tags=["mock"],
    dependencies=[Depends(_local_only)],
)
MOCK_DATA_DIR = Path(__file__).resolve().parent.parent.parent / "tests" / "mock_data"


@mock_router.get("/authorize")
async def mock_authorize(
    client_id: str,
    redirect_uri: str,
    response_type: str = "code",
    state: str | None = None,
    scenario: str = Query(
        "existing_user",
        description="Test scenario (e.g., existing_user, new_user, no_email_user)",
    ),
) -> RedirectResponse:
    """Mock Kakao login authorization page.

    Dynamically finds trigger_code from JSON file based on scenario parameter
    and redirects to the callback URL.

    Args:
        client_id: OAuth client ID.
        redirect_uri: Callback URI after authorization.
        response_type: OAuth response type (should be 'code').
        state: CSRF protection state parameter.
        scenario: Test scenario to simulate.

    Returns:
        RedirectResponse: Redirect to callback URL with authorization code.

    Raises:
        HTTPException: If mock data file not found or invalid scenario.
    """
    token_file = MOCK_DATA_DIR / "kakao_token_responses.json"

    if not token_file.exists():
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Mock data file not found.",
        )

    # Load JSON data
    data = json.loads(token_file.read_text(encoding="utf-8"))

    # Find trigger_code for requested scenario
    trigger_code = None
    for resp in data.get("responses", []):
        if resp.get("scenario") == scenario:
            trigger_code = resp.get("trigger_code")
            break

    # Handle invalid scenario request
    if not trigger_code:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Undefined mock scenario: {scenario}",
        )

    # Build redirect URL with extracted code
    redirect_url = f"{redirect_uri}?code={trigger_code}"
    if state:
        redirect_url += f"&state={state}"

    return RedirectResponse(url=redirect_url)


@mock_router.post("/oauth/token")
async def mock_token(
    grant_type: Annotated[str, Form()],
    client_id: Annotated[str, Form()],
    redirect_uri: Annotated[str, Form()],
    code: Annotated[str, Form()],
    client_secret: Annotated[str, Form(description="Client secret for security")],
) -> dict:
    """Mock Kakao token issuance API.

    Simulates POST https://kauth.kakao.com/oauth/token endpoint.

    Args:
        grant_type: OAuth grant type (must be 'authorization_code').
        client_id: OAuth client ID.
        redirect_uri: Callback URI.
        code: Authorization code from authorize endpoint.
        client_secret: Client secret for verification.

    Returns:
        dict: Token response data.

    Raises:
        HTTPException: If invalid grant type, client secret, or authorization code.
    """
    if grant_type != "authorization_code":
        raise HTTPException(status_code=400, detail="unsupported_grant_type")

    # Verify client secret against mock environment variable
    if client_secret != config.KAKAO_CLIENT_SECRET:
        raise HTTPException(
            status_code=401,
            detail={
                "error": "KOE010",
                "error_description": "Bad client credentials",
                "error_code": "KOE010",
            },
        )

    token_file = MOCK_DATA_DIR / "kakao_token_responses.json"
    data = json.loads(token_file.read_text(encoding="utf-8")) if token_file.exists() else {}

    # Find response matching trigger_code in JSON
    for resp in data.get("responses", []):
        if resp.get("trigger_code") == code:
            if resp.get("http_status") != 200:
                raise HTTPException(status_code=resp.get("http_status"), detail=resp.get("body"))
            return resp.get("body")

    # No matching code found
    raise HTTPException(
        status_code=400,
        detail={
            "error": "KOE320",
            "error_description": "authorization code not found for the given value",
            "error_code": "KOE320",
        },
    )


@mock_router.get("/v2/user/me")
async def mock_user_info(
    authorization: Annotated[str, Header(description="Bearer {access_token}")],
) -> dict:
    """Mock Kakao user info API.

    Simulates GET https://kapi.kakao.com/v2/user/me endpoint.

    Args:
        authorization: Authorization header with Bearer token.

    Returns:
        dict: User information response data.

    Raises:
        HTTPException: If invalid token format or token not found.
    """
    # Extract token from "Bearer mock_access_token_..." format
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="invalid_token_format")

    access_token = authorization.split(" ")[1]

    userinfo_file = MOCK_DATA_DIR / "kakao_userinfo_responses.json"
    data = json.loads(userinfo_file.read_text(encoding="utf-8")) if userinfo_file.exists() else {}

    # Find response matching trigger_access_token in JSON
    for resp in data.get("responses", []):
        if resp.get("trigger_access_token") == access_token:
            if resp.get("http_status") != 200:
                raise HTTPException(status_code=resp.get("http_status"), detail=resp.get("body"))
            return resp.get("body")

    # No matching token found
    raise HTTPException(
        status_code=401,
        detail={"msg": "this access token does not exist", "code": -401},
    )

"""mock IdP(카카오) 라우터의 이중 방어를 각각 잠근다 (`QA-41`).

mock 라우터는 카카오 대신 «이 사용자는 정상» 이라고 우리 서버가 선언하는 테스트 대역이라
노출되면 인증 우회로 이어진다. 방어는 두 겹이다.

- ① 등록 게이팅 — ``app/apis/v1/__init__.py`` 가 ``ENV == local`` 일 때만 라우터를 붙인다
- ② 핸들러 가드 — 라우터의 ``_local_only`` 의존성이 local 이 아니면 **404** 를 낸다

🔑 **둘을 따로 잰다** — 하나만 재면 다른 하나가 죽어도 초록이다.
각 방어마다 **local 에서는 통과한다**는 음성 대조를 같이 둔다(그래야 «항상 404» 인 가드와 구분된다).
"""

import os
import subprocess
import sys

from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
import pytest

from app.apis.v1 import mock_oauth_routers
from app.core.config import Env

_AUTHORIZE = "/mock/kakao/authorize?client_id=FAKE_client&redirect_uri=http://localhost/cb"

#: 라우터 목록에서 mock 경로를 뽑아 인쇄한다 — 등록 판정은 import 시점이라 하위 프로세스에서 잰다.
_PROBE = (
  "from app.apis.v1 import v1_routers;"
  "paths = [r.path for r in v1_routers.routes];"
  "print(len(paths), sum('/mock/' in p for p in paths))"
)


def _registered_routes(env: str) -> tuple[int, int]:
  """``ENV=env`` 로 새 인터프리터를 띄워 (전체 라우트 수, mock 라우트 수) 를 돌려준다."""
  result = subprocess.run(  # noqa: S603 — 고정 인자, 셸 없음
    [sys.executable, "-c", _PROBE],
    env={**os.environ, "ENV": env},
    capture_output=True,
    text=True,
    check=True,
  )
  total, mock = result.stdout.split()
  return int(total), int(mock)


class TestRegistrationGate:
  """① 등록 게이팅 — local 이 아니면 라우터가 붙지 않는다."""

  def test_mock_routes_are_not_registered_outside_local(self) -> None:
    total, mock = _registered_routes(Env.DEV)
    assert total > 0, "라우트를 하나도 못 셌다 — 측정이 돌지 않았다"
    assert mock == 0, "local 이 아닌데 mock IdP 경로가 등록됐다"

  def test_mock_routes_are_registered_in_local(self) -> None:
    """음성 대조 — local 에서는 붙어야 한다(안 붙으면 위 단언은 아무것도 증명하지 않는다)."""
    _, mock = _registered_routes(Env.LOCAL)
    assert mock > 0


def _app_with_mock_router() -> FastAPI:
  """등록 게이팅을 건너뛰고 mock 라우터를 **강제로** 붙인 앱 — 핸들러 가드만 남긴다."""
  app = FastAPI()
  app.include_router(mock_oauth_routers.mock_router)
  return app


async def _get_authorize() -> int:
  transport = ASGITransport(app=_app_with_mock_router())
  async with AsyncClient(transport=transport, base_url="http://test") as client:
    response = await client.get(_AUTHORIZE, follow_redirects=False)
  return response.status_code


class TestHandlerGuard:
  """② 핸들러 가드 — 실수로 등록돼도 local 이 아니면 404 다."""

  @pytest.mark.asyncio
  @pytest.mark.parametrize("env", [Env.DEV, Env.PROD])
  async def test_the_guard_answers_404_outside_local(self, monkeypatch: pytest.MonkeyPatch, env: Env) -> None:
    # 🔑 가드가 읽는 것은 `app.core` 패키지의 config 인스턴스다(`app.core.config.config` 와 다른 객체)
    monkeypatch.setattr(mock_oauth_routers.config, "ENV", env)
    assert await _get_authorize() == 404

  @pytest.mark.asyncio
  async def test_the_guard_lets_local_through(self, monkeypatch: pytest.MonkeyPatch) -> None:
    """음성 대조 — local 에서는 가드를 지난다(404 가 아니다)."""
    monkeypatch.setattr(mock_oauth_routers.config, "ENV", Env.LOCAL)
    assert await _get_authorize() != 404

"""Request context middleware — 요청마다 request_id 부여/전파.

순수 ASGI 미들웨어(BaseHTTPMiddleware 아님)로 ``request_id`` contextvar 를
설정해, 엔드포인트가 실행되는 **동일 async 컨텍스트**에서 request_id 가 유효하도록
보장한다(BaseHTTPMiddleware 의 contextvar 전파 유실 회피). 모든 로그에는
RequestIdFilter 가 이 값을 자동 첨부하고, 응답에는 ``X-Request-ID`` 헤더로 반환한다.
"""

import re
from uuid import uuid4

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.logger import request_id_var

_HEADER = b"x-request-id"
# 승계할 유입 ID 의 규격 — 값이 모든 로그 줄과 응답 헤더에 실리므로 좁게 받는다(QA-69).
# 128 = uuid(36)·흔한 프록시 추적 ID 를 넉넉히 덮으면서 로그 비대를 막는 상한.
MAX_REQUEST_ID_LEN = 128
_VALID_REQUEST_ID = re.compile(rb"[A-Za-z0-9._-]{1,%d}" % MAX_REQUEST_ID_LEN)


def _accepted_request_id(incoming: bytes | None) -> str:
  """규격 안의 유입 ID 는 승계하고, 없거나 규격 밖이면 새로 만든다."""
  if incoming is not None and _VALID_REQUEST_ID.fullmatch(incoming):
    return incoming.decode("ascii")
  return uuid4().hex


# ── 요청 컨텍스트 미들웨어 (request_id) ────────────────────────────────
# 흐름: 유입 X-Request-ID 가 규격 안이면 승계, 아니면 신규 생성 -> contextvar set
#       -> 하위 앱 실행(엔드포인트/로그가 동일 컨텍스트에서 값 참조)
#       -> 응답 start 에 X-Request-ID 헤더 주입 -> 종료 시 contextvar reset
class RequestContextMiddleware:
  """요청마다 request_id 를 contextvar 에 설정하고 응답 헤더로 반환."""

  def __init__(self, app: ASGIApp) -> None:
    self.app = app

  async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
    """Bind a request id to the context for the lifetime of one HTTP scope."""
    if scope["type"] != "http":
      await self.app(scope, receive, send)
      return

    request_id = _accepted_request_id(dict(scope["headers"]).get(_HEADER))
    token = request_id_var.set(request_id)

    async def send_wrapper(message: Message) -> None:
      if message["type"] == "http.response.start":
        headers = message.setdefault("headers", [])
        headers.append((_HEADER, request_id.encode("latin-1")))
      await send(message)

    try:
      await self.app(scope, receive, send_wrapper)
    finally:
      request_id_var.reset(token)

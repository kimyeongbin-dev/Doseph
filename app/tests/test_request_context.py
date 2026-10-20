"""Tests for the request-context (request_id) ASGI middleware (B2).

Pure ASGI middleware is exercised directly with a minimal scope/receive/send
via ``asyncio.run`` — no app import / pytest-asyncio needed.
"""

import asyncio

from starlette.types import Message, Receive, Scope, Send

from app.core.logger import get_request_id
from app.middlewares.request_context import RequestContextMiddleware


def _run(scope: Scope) -> tuple[dict[str, str], list[Message], str]:
  """미들웨어를 더미 앱으로 1회 실행 → (앱 진입 시점 캡처, 전송 메시지들, 끝난 뒤 request_id).

  끝난 뒤 값은 미들웨어를 await 한 **같은 코루틴 안에서** 읽는다.
  ``asyncio.run`` 은 컨텍스트를 복사해 돌리므로 바깥에서 읽으면 리셋을 빼먹어도 안 보인다.
  """
  captured: dict[str, str] = {}
  sent: list[Message] = []

  async def dummy_app(_scope: Scope, _receive: Receive, send: Send) -> None:
    captured["id_in_ctx"] = get_request_id()
    await send({"type": "http.response.start", "status": 200, "headers": []})
    await send({"type": "http.response.body", "body": b""})

  async def receive() -> Message:
    return {"type": "http.request"}

  async def send(message: Message) -> None:
    sent.append(message)

  async def _call() -> str:
    await RequestContextMiddleware(dummy_app)(scope, receive, send)
    return get_request_id()

  after = asyncio.run(_call())
  return captured, sent, after


def _response_header(sent: list[Message], key: bytes) -> bytes | None:
  start = next(m for m in sent if m["type"] == "http.response.start")
  for header_key, value in start["headers"]:
    if header_key == key:
      return bytes(value)
  return None


def test_middleware_generates_id_and_sets_header() -> None:
  """유입 헤더 없으면 새 request_id 생성 → contextvar 설정 + 응답헤더 반영."""
  captured, sent, _ = _run({"type": "http", "headers": []})

  assert captured["id_in_ctx"] != "-"
  assert captured["id_in_ctx"]  # 비어있지 않음
  assert _response_header(sent, b"x-request-id") == captured["id_in_ctx"].encode()


def test_middleware_honors_incoming_id() -> None:
  """유입 X-Request-ID 가 있으면 그 값을 승계."""
  captured, sent, _ = _run({"type": "http", "headers": [(b"x-request-id", b"abc123")]})

  assert captured["id_in_ctx"] == "abc123"
  assert _response_header(sent, b"x-request-id") == b"abc123"


def test_middleware_resets_contextvar_after_request() -> None:
  """요청 종료 후 contextvar 는 기본값으로 복원(요청 간 누수 방지)."""
  captured, _, after = _run({"type": "http", "headers": []})

  assert captured["id_in_ctx"] != "-"  # 요청 중에는 설정돼 있었다
  assert after == "-"

"""Test configuration - common fixtures.

This module provides common test fixtures and configuration
for the test suite.
"""

from collections.abc import AsyncGenerator

from httpx import ASGITransport, AsyncClient
import pytest
import pytest_asyncio

from app.main import app
from app.tests.chat_service_stubs import ChatStubs, install_chat_repo_stubs

TEST_BASE_URL = "http://test"


@pytest_asyncio.fixture
async def client() -> AsyncGenerator[AsyncClient]:
  """Async test client fixture.

  Yields:
      AsyncClient: HTTP client for testing API endpoints.
  """
  async with AsyncClient(
    transport=ASGITransport(app=app),
    base_url=TEST_BASE_URL,
  ) as ac:
    yield ac


@pytest.fixture
def chat_stubs(monkeypatch: pytest.MonkeyPatch) -> ChatStubs:
  """챗봇 서비스 테스트용 — 세션·메시지 저장소를 DB 없는 가짜로 바꾼다."""
  return install_chat_repo_stubs(monkeypatch)

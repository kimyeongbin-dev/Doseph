"""Test configuration - common fixtures.

This module provides common test fixtures and configuration
for the test suite.
"""

from collections.abc import AsyncGenerator

from httpx import ASGITransport, AsyncClient
import pytest_asyncio

from app.main import app

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

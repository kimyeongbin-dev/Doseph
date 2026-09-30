"""Basic application tests.

This module contains basic tests for the FastAPI application
including app creation and documentation endpoints.
"""

from httpx import AsyncClient
import pytest

from app.main import app


def test_app_created() -> None:
  """Test FastAPI app instance creation.

  Verifies that the FastAPI application instance is properly created
  and has the expected configuration.
  """
  assert app is not None
  assert app.title == "FastAPI"


class TestDocs:
  """API documentation endpoint tests.

  This class contains tests for API documentation endpoints
  including OpenAPI schema, Swagger UI, and ReDoc.
  """

  @pytest.mark.asyncio
  async def test_openapi_endpoint(self, client: AsyncClient) -> None:
    """Test OpenAPI schema endpoint access.

    Args:
        client: Async HTTP client fixture.
    """
    response = await client.get("/api/openapi.json")
    assert response.status_code == 200
    data = response.json()
    assert "paths" in data
    assert "openapi" in data

  @pytest.mark.asyncio
  async def test_docs_endpoint(self, client: AsyncClient) -> None:
    """Test Swagger UI endpoint access.

    Args:
        client: Async HTTP client fixture.
    """
    response = await client.get("/api/docs")
    assert response.status_code == 200

  @pytest.mark.asyncio
  async def test_redoc_endpoint(self, client: AsyncClient) -> None:
    """Test ReDoc endpoint access.

    Args:
        client: Async HTTP client fixture.
    """
    response = await client.get("/api/redoc")
    assert response.status_code == 200

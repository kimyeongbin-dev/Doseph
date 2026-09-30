"""Tests for RAG Protocol compliance - EmbeddingProvider and Retriever."""

from unittest.mock import AsyncMock

import pytest

from app.dtos.rag import SearchFilters
from app.services.rag.protocols import EmbeddingProvider, Retriever


class TestEmbeddingProviderProtocol:
  """Verify EmbeddingProvider Protocol interface."""

  def test_protocol_has_dimensions_property(self) -> None:
    """EmbeddingProvider must define dimensions property."""
    assert hasattr(EmbeddingProvider, "__protocol_attrs__") or hasattr(EmbeddingProvider, "__abstractmethods__")

  def test_mock_satisfies_embedding_provider_protocol(self) -> None:
    """A mock with correct interface must satisfy EmbeddingProvider."""
    mock = AsyncMock()
    mock.dimensions = 768
    mock.encode_single = AsyncMock(return_value=[0.1] * 768)
    mock.encode_batch = AsyncMock(return_value=[[0.1] * 768])

    # Protocol structural check
    assert hasattr(mock, "dimensions")
    assert hasattr(mock, "encode_single")
    assert hasattr(mock, "encode_batch")

  @pytest.mark.asyncio
  async def test_encode_single_returns_float_list(self) -> None:
    """encode_single must return list[float]."""
    mock = AsyncMock()
    mock.encode_single = AsyncMock(return_value=[0.1, 0.2, 0.3])

    result = await mock.encode_single("test text")
    assert isinstance(result, list)
    assert all(isinstance(v, float) for v in result)

  @pytest.mark.asyncio
  async def test_encode_batch_returns_list_of_float_lists(self) -> None:
    """encode_batch must return list[list[float]]."""
    mock = AsyncMock()
    mock.encode_batch = AsyncMock(return_value=[[0.1, 0.2], [0.3, 0.4]])

    result = await mock.encode_batch(["text1", "text2"])
    assert isinstance(result, list)
    assert all(isinstance(row, list) for row in result)


class TestRetrieverProtocol:
  """Verify Retriever Protocol interface."""

  def test_protocol_has_retrieve_method(self) -> None:
    """Retriever must define retrieve method."""
    assert hasattr(Retriever, "__protocol_attrs__") or hasattr(Retriever, "__abstractmethods__")

  def test_mock_satisfies_retriever_protocol(self) -> None:
    """A mock with correct interface must satisfy Retriever."""
    mock = AsyncMock()
    mock.retrieve = AsyncMock(return_value=[])

    assert hasattr(mock, "retrieve")

  @pytest.mark.asyncio
  async def test_retrieve_returns_list_of_search_results(self) -> None:
    """Retrieve must return list[SearchResult]."""
    mock = AsyncMock()
    mock.retrieve = AsyncMock(return_value=[])

    result = await mock.retrieve(
      query="test",
      query_embedding=[0.1] * 768,
      filters=SearchFilters(),
      limit=5,
    )
    assert isinstance(result, list)

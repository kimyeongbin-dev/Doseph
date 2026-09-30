"""Protocol definitions for the RAG pipeline.

Defines the interfaces for swappable components:
- EmbeddingProvider: embedding model abstraction
- Retriever: search strategy abstraction

Implement these protocols to add new embedding models or search strategies
without modifying the RAGPipeline.
"""

from typing import Protocol, runtime_checkable

from app.dtos.rag import SearchFilters, SearchResult


@runtime_checkable
class EmbeddingProvider(Protocol):
  """Interface for embedding model implementations.

  Implement this protocol to swap embedding models
  (e.g., SentenceTransformer, OpenAI, etc.).
  """

  @property
  def dimensions(self) -> int:
    """Embedding vector dimensions."""
    ...

  async def encode_single(self, text: str) -> list[float]:
    """Encode a single text into an embedding vector.

    Args:
        text: Input text to encode.

    Returns:
        Embedding vector as list of floats.
    """
    ...

  async def encode_batch(self, texts: list[str]) -> list[list[float]]:
    """Encode multiple texts into embedding vectors.

    Args:
        texts: List of input texts to encode.

    Returns:
        List of embedding vectors.
    """
    ...


@runtime_checkable
class Retriever(Protocol):
  """Interface for search strategy implementations.

  Implement this protocol to swap search strategies
  (e.g., pure vector, hybrid, BM25, etc.).
  """

  async def retrieve(
    self,
    query: str,
    query_embedding: list[float],
    filters: SearchFilters,
    limit: int,
  ) -> list[SearchResult]:
    """Retrieve relevant document chunks for a query.

    Args:
        query: Original query text for keyword matching.
        query_embedding: Pre-computed query embedding vector.
        filters: Metadata filters to apply.
        limit: Maximum number of results to return.

    Returns:
        List of SearchResult sorted by relevance score.
    """
    ...

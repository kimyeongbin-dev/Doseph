"""Tests for RAG embedding configuration constants.

Verifies that embedding model and dimension constants are exposed from
`app.services.rag.config` as a single source of truth. Swapping models
should only require changing these constants plus a migration.
"""

from app.services.rag import config as rag_config


class TestEmbeddingConfigConstants:
  """Tests for centralized embedding configuration."""

  def test_embedding_model_name_is_defined(self) -> None:
    """EMBEDDING_MODEL_NAME constant must exist and be a non-empty string."""
    assert hasattr(rag_config, "EMBEDDING_MODEL_NAME")
    assert isinstance(rag_config.EMBEDDING_MODEL_NAME, str)
    assert rag_config.EMBEDDING_MODEL_NAME

  def test_embedding_dimensions_is_defined(self) -> None:
    """EMBEDDING_DIMENSIONS constant must exist and be a positive int."""
    assert hasattr(rag_config, "EMBEDDING_DIMENSIONS")
    assert isinstance(rag_config.EMBEDDING_DIMENSIONS, int)
    assert rag_config.EMBEDDING_DIMENSIONS > 0

  def test_embedding_defaults_match_current_model(self) -> None:
    """현재 기본값: Gemini ``gemini-embedding-001``, 3072 차원.

    2026-10-16 v2.0 재배포 PLAN S1 — OpenAI ``text-embedding-3-large`` 에서 바꿨다(무료 등급).
    차원은 그대로 둔다 — ``halfvec(3072)`` 스키마를 안 바꾸고, 3072 는 API 가 정규화해 준다.
    벡터가 운영·로컬 모두 0건이라 옛 벡터와 섞일 일이 없다.
    🔑 정본 = `app/services/rag/config.py`. 이 테스트가 그것을 잠근다.
    """
    assert rag_config.EMBEDDING_MODEL_NAME == "gemini-embedding-001"
    assert rag_config.EMBEDDING_DIMENSIONS == 3072

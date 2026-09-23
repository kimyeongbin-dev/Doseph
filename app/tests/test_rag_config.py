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
        """Current defaults: OpenAI text-embedding-3-large, 3072 dimensions.

        사라진 계획 «feature/RAG» §0 — ko-sroberta (768d) 폐기, OpenAI 통합.
        🔑 정본 = `app/services/rag/config.py`. 이 테스트가 그것을 잠근다.
        """
        assert rag_config.EMBEDDING_MODEL_NAME == "text-embedding-3-large"
        assert rag_config.EMBEDDING_DIMENSIONS == 3072

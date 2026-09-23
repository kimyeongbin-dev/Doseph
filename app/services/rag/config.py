"""Centralized embedding configuration for the RAG pipeline.

Single source of truth for the embedding model and its vector dimensions.
사라진 계획 «feature/RAG» §0 — OpenAI text-embedding-3-large (3072d) 사용.
🔑 **정본은 이 파일이다**(`EMBEDDING_MODEL_NAME`·`EMBEDDING_DIMENSIONS`) — 계획이 아니라.
ko-sroberta (jhgan/ko-sroberta-multitask, 768d) 는 폐기.
"""

EMBEDDING_MODEL_NAME: str = "text-embedding-3-large"
EMBEDDING_DIMENSIONS: int = 3072

"""Centralized embedding configuration for the RAG pipeline.

Single source of truth for the embedding model and its vector dimensions.
사라진 계획 «feature/RAG» §0 — 처음엔 OpenAI text-embedding-3-large (3072d) 였고,
2026-10-16 v2.0 재배포 PLAN 에서 Gemini 무료 등급 ``gemini-embedding-001`` 로 바꿨다(차원 3072 유지).
🔑 **정본은 이 파일이다**(`EMBEDDING_MODEL_NAME`·`EMBEDDING_DIMENSIONS`) — 계획이 아니라.
ko-sroberta (jhgan/ko-sroberta-multitask, 768d) 는 폐기.
"""

EMBEDDING_MODEL_NAME: str = "gemini-embedding-001"
EMBEDDING_DIMENSIONS: int = 3072

"""RAG service package — feature/RAG 4단 파이프라인 잔여 모듈.

⚠️ 이 목록은 **실재하는 모듈만** 적는다. 2026-09-23 까지 ``retrievers.hybrid`` 와
``retrievers.rrf`` 를 설명하고 있었으나 **둘 다 없었다**(RRF 는 단일 query 검색으로
바뀌며 폐기). 구조 지도는 처음 오는 사람이 먼저 읽는 자리라 없는 모듈을 찾아 헤매게 한다.

본 패키지의 책임:

- ``app.services.rag.config`` — 임베딩 모델 이름·차원 (text-embedding-3-large, 3072d)
- ``app.services.rag.openai_embedding`` — query 측 OpenAI Embedding 호출
- ``app.services.rag.retrievers.hybrid_metadata`` — JSONB ``?|`` 메타 필터 + halfvec cosine top-K
- ``app.services.rag.protocols`` — ``EmbeddingProvider`` / ``Retriever`` Protocol 정의

Public 진입점은 explicit submodule path 로만 노출한다.
"""

"""OpenAI text-embedding-3-large query-side 임베딩 — 3072d.

사라진 계획 «feature/RAG» §0 결정 — chunk 임베딩과 동일 모델/dim 사용.
🔑 모델·차원의 정본 = `app/services/rag/config.py`.

medicine_chunk 의 embedding 컬럼은 vector(3072) (28번 마이그). 사용자 query 도
같은 모델 + 같은 dim 으로 임베딩해야 cosine 유사도 비교 정확.

사용처:
- RRF Hybrid Retrieval 의 vector 검색 step
- 다음 사이클 (29번 마이그) 의 ANN 인덱스 검색

ai_worker 측의 embed_text_job 과 분리:
- ai_worker: medicine_chunk batch 임베딩 (scripts/embed_medicine_chunks.py 가 처리)
- app/services: 사용자 query 단건 임베딩 (RAG retrieval 시 호출)

batch 입력 지원 (fanout_queries N 개를 한 번에 임베딩).
"""

import logging

from openai import APIConnectionError, APITimeoutError, AsyncOpenAI, RateLimitError

from app.core.config import config
from app.services.tools.retry import retry_async

logger = logging.getLogger(__name__)

_RETRYABLE = (APIConnectionError, APITimeoutError, RateLimitError, ConnectionError, TimeoutError)

EMBEDDING_MODEL = "text-embedding-3-large"
EMBEDDING_DIMENSIONS = 3072

_client: AsyncOpenAI | None = None
_initialised: bool = False


def _get_client() -> AsyncOpenAI | None:
    """AsyncOpenAI 싱글톤 — config.OPENAI_API_KEY 가 없으면 None.

    ai_worker.core.openai_client 와 동일 패턴 — 매 호출마다 재할당 X.
    """
    global _client, _initialised

    if _initialised:
        return _client

    api_key = config.OPENAI_API_KEY
    if not api_key:
        logger.warning("OPENAI_API_KEY 미설정 — encode_query 비활성")
        _initialised = True
        return None

    _client = AsyncOpenAI(api_key=api_key)
    _initialised = True
    return _client


@retry_async(retryable=_RETRYABLE)
async def _embed_one(client: AsyncOpenAI, query: str) -> list[float]:
    response = await client.embeddings.create(
        model=EMBEDDING_MODEL,
        input=query,
        dimensions=EMBEDDING_DIMENSIONS,
    )
    return list(response.data[0].embedding)


@retry_async(retryable=_RETRYABLE)
async def _embed_batch(client: AsyncOpenAI, queries: list[str]) -> list[list[float]]:
    response = await client.embeddings.create(
        model=EMBEDDING_MODEL,
        input=queries,
        dimensions=EMBEDDING_DIMENSIONS,
    )
    # response.data 는 input 순서 그대로 반환 (OpenAI 명세 보장)
    return [list(d.embedding) for d in response.data]


async def encode_query(query: str) -> list[float]:
    """단일 query 를 3072d 임베딩 벡터로 변환.

    Args:
        query: 사용자 query 또는 fanout_query 문자열.

    Returns:
        3072 float 의 list. 빈 query 또는 client 부재 시 영벡터.
    """
    if not query:
        return [0.0] * EMBEDDING_DIMENSIONS

    client = _get_client()
    if client is None:
        return [0.0] * EMBEDDING_DIMENSIONS

    return await _embed_one(client, query)


async def encode_queries_batch(queries: list[str]) -> list[list[float]]:
    """여러 query 를 batch 로 한 번에 임베딩 (단일 OpenAI API 호출).

    Args:
        queries: query 문자열 list. 빈 list 면 빈 list 반환.

    Returns:
        각 query 에 대응하는 3072d 임베딩 list 의 list. queries 와 같은 길이.
    """
    if not queries:
        return []

    client = _get_client()
    if client is None:
        return [[0.0] * EMBEDDING_DIMENSIONS for _ in queries]

    return await _embed_batch(client, queries)

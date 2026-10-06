"""Unit tests for app.services.rag.openai_embedding — 사용자 query 측 임베딩.

PLAN.md §4.1 — text-embedding-3-large + dimensions=3072 검증.
Phase 3 [Implement] Green — AsyncOpenAI mock 으로 실 호출 우회.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.rag import openai_embedding
from app.services.rag.config import EMBEDDING_DIMENSIONS, EMBEDDING_MODEL_NAME
from app.services.rag.openai_embedding import (
  encode_queries_batch,
  encode_query,
)


class TestConstants:
  """모델/차원 상수가 chunk 임베딩과 일치하는지."""

  def test_model_name(self) -> None:
    assert EMBEDDING_MODEL_NAME == "text-embedding-3-large"

  def test_the_module_reads_the_canonical_name(self) -> None:
    """🔴 중복 선언을 막는다 — 이 모듈은 정본을 **그대로** 써야 한다.

    2026-10-07(`QA-07` ①)까지 `openai_embedding` 과 `scripts/embed_medicine_chunks` 가
    같은 값을 **각자** 들고 있었다. `config.py` 가 docstring 에 *«정본은 이 파일이다»* 를
    적어 두고도 그랬다. 같은 객체인지 보면 중복이 다시 생기는 것을 막는다.
    """
    assert openai_embedding.EMBEDDING_MODEL_NAME is EMBEDDING_MODEL_NAME

  def test_dimensions(self) -> None:
    assert EMBEDDING_DIMENSIONS == 3072

  def test_the_module_reads_the_canonical_dimensions(self) -> None:
    """🔴 차원도 중복이었다 — 모델명과 **같은 파일**에서 각자 들고 있었다.

    2026-10-07 실측: `openai_embedding` 과 `scripts/embed_medicine_chunks` 가
    `EMBEDDING_DIMENSIONS = 3072` 를 각자 선언하고 있었다. `QA-07` 은 «모델명 5곳» 만
    세었으므로 **이 넷은 등재에 없었다**(모델명 2 + 차원 2).
    """
    assert openai_embedding.EMBEDDING_DIMENSIONS == EMBEDDING_DIMENSIONS


def _make_mock_client(vectors: list[list[float]]) -> MagicMock:
  """AsyncOpenAI 의 embeddings.create 가 vectors 를 반환하도록 mock."""
  client = MagicMock()
  response = MagicMock()
  response.data = [MagicMock(embedding=v) for v in vectors]
  client.embeddings.create = AsyncMock(return_value=response)
  return client


@pytest.fixture(autouse=True)
def _reset_embedding_singleton(monkeypatch: pytest.MonkeyPatch) -> None:
  """각 테스트 전 _client / _initialised 초기화."""
  monkeypatch.setattr(openai_embedding, "_client", None)
  monkeypatch.setattr(openai_embedding, "_initialised", False)


class TestEncodeQuery:
  """encode_query 단위 테스트."""

  @pytest.mark.asyncio
  async def test_single_query_returns_3072_vector(self, monkeypatch: pytest.MonkeyPatch) -> None:
    """정상 query → 3072 차원 float list."""
    fake_vec = [0.1] * 3072
    client = _make_mock_client([fake_vec])
    monkeypatch.setattr(openai_embedding, "_get_client", lambda: client)

    result = await encode_query("타이레놀 부작용")
    assert isinstance(result, list)
    assert len(result) == 3072

  @pytest.mark.asyncio
  async def test_empty_string(self) -> None:
    """빈 문자열 → API 호출 안하고 영벡터."""
    result = await encode_query("")
    assert len(result) == 3072
    assert all(v == 0.0 for v in result)

  @pytest.mark.asyncio
  async def test_no_api_key_returns_zero_vector(self, monkeypatch: pytest.MonkeyPatch) -> None:
    """API key 없을 때 (_get_client None) → 영벡터."""
    monkeypatch.setattr(openai_embedding, "_get_client", lambda: None)
    result = await encode_query("타이레놀")
    assert len(result) == 3072
    assert all(v == 0.0 for v in result)


class TestEncodeQueriesBatch:
  """encode_queries_batch 단위 테스트."""

  @pytest.mark.asyncio
  async def test_batch_returns_n_vectors(self, monkeypatch: pytest.MonkeyPatch) -> None:
    """N query → N vectors (단일 OpenAI API call)."""
    queries = ["q1", "q2", "q3"]
    fake_vectors = [[0.1] * 3072, [0.2] * 3072, [0.3] * 3072]
    client = _make_mock_client(fake_vectors)
    monkeypatch.setattr(openai_embedding, "_get_client", lambda: client)

    result = await encode_queries_batch(queries)
    assert len(result) == 3
    assert all(len(v) == 3072 for v in result)
    # 단일 API 호출 검증
    assert client.embeddings.create.call_count == 1

  @pytest.mark.asyncio
  async def test_empty_batch(self) -> None:
    """빈 list → 빈 list (API 호출 X)."""
    result = await encode_queries_batch([])
    assert result == []

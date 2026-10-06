"""OpenAI 임베딩 경계의 **HTTP 계약** 테스트 (B-8 3구간 · `QA-07` 전제).

왜 다시 썼나 — `AsyncMock` 은 우리 코드를 건너뛴다
---------------------------------------------------
앞 판은 ``monkeypatch.setattr(openai_embedding, "_get_client", lambda: client)`` 로
**클라이언트 획득 자체를 교체**했다. 그래서 다음이 전부 미검증이었다 —

- 요청에 실리는 ``model`` · ``dimensions`` · ``input`` (= `QA-07` ① 이 모은 정본이
  **실제로 전송되는가**)
- ``_get_client`` 의 싱글톤·API key 분기
- ``@retry_async`` 의 재시도 경로 (5xx · 타임아웃)

🔴 **2구간이 경고한 자리가 이것이다**: *«`log_boundary` 를 OpenAI 경계에 부착해도 래퍼를
`AsyncMock` 으로 바꾸면 한 번도 실행되지 않는다»*. respx 는 **httpx 레벨**에서 가로채므로
우리 코드는 전부 실행된다.

🔑 **선례 = `app/tests/test_drug_recall_http_boundary.py`** (1구간이 data.go.kr 경계에 세운 것).
같은 패턴을 OpenAI 경계로 옮겼다.
"""

import json
import logging
from typing import Any

import httpx
import pytest
import respx

from app.core.config import config
from app.services.rag import openai_embedding
from app.services.rag.config import EMBEDDING_DIMENSIONS, EMBEDDING_MODEL_NAME
from app.services.rag.openai_embedding import (
  encode_queries_batch,
  encode_query,
)

_URL = "https://api.openai.com/v1/embeddings"


class TestConstants:
  """모델/차원 상수가 chunk 임베딩과 일치하는지."""

  def test_model_name(self) -> None:
    assert EMBEDDING_MODEL_NAME == "text-embedding-3-large"

  def test_the_module_reads_the_canonical_name(self) -> None:
    """🔴 중복 선언을 막는다 — 이 모듈은 정본을 **그대로** 써야 한다.

    2026-10-07(`QA-07` ①)까지 `openai_embedding` 과 `scripts/embed_medicine_chunks` 가
    같은 값을 **각자** 들고 있었다. `config.py` 가 docstring 에 *«정본은 이 파일이다»* 를
    적어 두고도 그랬다.
    """
    assert openai_embedding.EMBEDDING_MODEL_NAME is EMBEDDING_MODEL_NAME

  def test_dimensions(self) -> None:
    assert EMBEDDING_DIMENSIONS == 3072

  def test_the_module_reads_the_canonical_dimensions(self) -> None:
    """🔴 차원도 중복이었다 — 모델명과 **같은 파일**에서 각자 들고 있었다."""
    assert openai_embedding.EMBEDDING_DIMENSIONS == EMBEDDING_DIMENSIONS


# ── 공용 헬퍼 ──────────────────────────────────────────────────────────


def _body(vectors: list[list[float]]) -> dict[str, Any]:
  """OpenAI ``/v1/embeddings`` 응답 봉투. SDK 가 이 모양을 파싱한다."""
  return {
    "object": "list",
    "data": [{"object": "embedding", "index": i, "embedding": v} for i, v in enumerate(vectors)],
    "model": EMBEDDING_MODEL_NAME,
    "usage": {"prompt_tokens": 1, "total_tokens": 1},
  }


def _vec(fill: float) -> list[float]:
  """정본 차원만큼 채운 벡터 — 숫자 3072 를 테스트에 박지 않는다."""
  return [fill] * EMBEDDING_DIMENSIONS


def _route(vectors: list[list[float]]) -> respx.Route:
  """임베딩 엔드포인트를 200 으로 세운다."""
  return respx.post(_URL).mock(return_value=httpx.Response(200, json=_body(vectors)))


def _sent(route: respx.Route, call: int = 0) -> dict[str, Any]:
  """실제로 **전송된** 요청 본문. 여기서 `QA-07` ① 의 계약을 잠근다."""
  return json.loads(route.calls[call].request.content)


@pytest.fixture(autouse=True)
def _reset_embedding_singleton(monkeypatch: pytest.MonkeyPatch) -> None:
  """각 테스트 전 싱글톤 초기화 + API key 주입.

  🔑 key 를 넣는 이유: 앞 판은 `_get_client` 를 교체해 **그 함수가 안 돌았다.**
  이제 실제로 돌려서 ``AsyncOpenAI`` 가 만들어지고 httpx 요청까지 간다.
  """
  monkeypatch.setattr(openai_embedding, "_client", None)
  monkeypatch.setattr(openai_embedding, "_initialised", False)
  monkeypatch.setattr(config, "OPENAI_API_KEY", "sk-test-not-a-real-key")


class TestEncodeQuery:
  """`encode_query` — 단일 질의."""

  @pytest.mark.asyncio
  @respx.mock
  async def test_single_query_returns_canonical_dimension_vector(self) -> None:
    """정상 query → 정본 차원의 float list."""
    route = _route([_vec(0.1)])
    result = await encode_query("타이레놀 부작용")
    assert isinstance(result, list)
    assert len(result) == EMBEDDING_DIMENSIONS
    assert route.call_count == 1

  @pytest.mark.asyncio
  @respx.mock
  async def test_request_carries_the_canonical_model_and_dimensions(self) -> None:
    """🔴 `QA-07` ① 의 계약 — **정본이 실제로 전송되는가**.

    모델명을 한 곳으로 모아도 **요청에 실리지 않으면** 아무 의미가 없다.
    앞 판은 `_get_client` 를 교체해 요청이 만들어지지도 않았으므로 이 단언이
    **원리적으로 불가능**했다.
    """
    route = _route([_vec(0.1)])
    await encode_query("타이레놀")
    sent = _sent(route)
    assert sent["model"] == EMBEDDING_MODEL_NAME
    assert sent["dimensions"] == EMBEDDING_DIMENSIONS
    assert sent["input"] == "타이레놀"

  @pytest.mark.asyncio
  @respx.mock
  async def test_empty_string_does_not_call_the_api(self) -> None:
    """빈 문자열 → 호출 없이 영벡터. 🔑 *«호출 안 함»* 을 직접 단언한다."""
    route = _route([_vec(0.1)])
    result = await encode_query("")
    assert len(result) == EMBEDDING_DIMENSIONS
    assert all(v == 0.0 for v in result)
    assert not route.called

  @pytest.mark.asyncio
  @respx.mock
  async def test_no_api_key_returns_zero_vector(self, monkeypatch: pytest.MonkeyPatch) -> None:
    """API key 없음 → 영벡터.

    🔑 이제 `_get_client` 가 **실제로 실행**되어 그 분기를 지난다
    (앞 판은 그 함수를 `lambda: None` 으로 바꿔 분기 자체가 없었다).
    """
    monkeypatch.setattr(config, "OPENAI_API_KEY", None)
    route = _route([_vec(0.1)])
    result = await encode_query("타이레놀")
    assert len(result) == EMBEDDING_DIMENSIONS
    assert all(v == 0.0 for v in result)
    assert not route.called

  @pytest.mark.asyncio
  @respx.mock
  async def test_the_boundary_log_actually_runs(
    self, caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch
  ) -> None:
    """🔴 `QA-07` ④ 의 계약 — **부착이 아니라 «실행» 을 단언한다**.

    2구간이 적어 둔 경고가 이것이다: *«`log_boundary` 를 OpenAI 경계에 부착해도 래퍼를
    `AsyncMock` 으로 바꾸면 한 번도 실행되지 않는다»*. respx 는 **httpx 레벨**에서
    가로채므로 경계를 감싼 코드가 **실제로 지나간다.**

    🔑 이 단언이 없으면 ④ 는 영원히 미지다 — *«붙였다»* 와 *«돈다»* 를 구분할 수 없다.

    🔴 **`caplog` 만으로는 아무것도 안 보인다**(`D49` 가 적어 둔 함정).
    `setup_logger` 가 부모 로거(`app`)에 **`propagate = False`** 를 걸어 중복 출력을
    막는데, pytest 의 `caplog` 은 **root 에** 핸들러를 붙인다 — 레코드가 부모에서 멈춘다.
    ⇒ 그 한 줄을 켜 주어야 **캡처가 실제로 일어난다.** 실제로 켜기 전에는 4건 전부
    Red 였고, 그 Red 가 *«캡처가 되는지»* 를 증명했다.
    """
    monkeypatch.setattr(logging.getLogger("app"), "propagate", True)
    _route([_vec(0.1)])
    with caplog.at_level(logging.INFO, logger="app"):
      await encode_query("타이레놀")
    assert any("[BOUNDARY] openai_embeddings 성공" in r.getMessage() for r in caplog.records), (
      "경계 로그가 없다 — log_boundary 가 실행되지 않았다"
    )


class TestEncodeQueriesBatch:
  """`encode_queries_batch` — 배치 질의."""

  @pytest.mark.asyncio
  @respx.mock
  async def test_batch_returns_n_vectors_in_one_call(self) -> None:
    """N query → N vectors, **단일 호출**."""
    queries = ["q1", "q2", "q3"]
    route = _route([_vec(0.1), _vec(0.2), _vec(0.3)])
    result = await encode_queries_batch(queries)
    assert len(result) == 3
    assert all(len(v) == EMBEDDING_DIMENSIONS for v in result)
    assert route.call_count == 1
    assert _sent(route)["input"] == queries

  @pytest.mark.asyncio
  @respx.mock
  async def test_empty_batch_does_not_call_the_api(self) -> None:
    """빈 list → 빈 list, 호출 없음."""
    route = _route([_vec(0.1)])
    assert await encode_queries_batch([]) == []
    assert not route.called


class TestRetryBoundary:
  """`@retry_async` — 앞 판에서 **한 번도 실행되지 않은** 경로."""

  @pytest.mark.asyncio
  @respx.mock
  async def test_a_transient_failure_is_retried(self) -> None:
    """5xx 한 번 → 재시도해서 성공한다.

    🔴 이 계약은 **지금 동작을 잠그는 것**이고 *«이게 옳다»* 고 말하는 게 아니다
    (`CLAUDE.md` §6-2). 재시도 횟수·백오프는 `retry_async` 의 기본값이 정한다.
    """
    route = respx.post(_URL).mock(
      side_effect=[
        httpx.Response(503, json={"error": {"message": "overloaded"}}),
        httpx.Response(200, json=_body([_vec(0.4)])),
      ]
    )
    result = await encode_query("재시도")
    assert len(result) == EMBEDDING_DIMENSIONS
    assert route.call_count == 2, "5xx 뒤 재시도가 일어나야 한다"

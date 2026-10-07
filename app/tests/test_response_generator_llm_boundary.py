"""RAG 2nd LLM(응답 생성)의 **HTTP 경계** 테스트 (B-8 4구간 · `QA-64` ⓵).

왜 신설인가 — **이 경로는 테스트가 없었다**
--------------------------------------------
🔬 실측 2026-10-07: OpenAI 를 직접 호출하는 **6경로** 중 이것이 테스트 0개인 둘 중 하나였다
(다른 하나는 `session_compact/summarizer`). 그래서 다음이 전부 미검증이었다 —

- 요청에 실리는 ``model`` · ``temperature`` · ``max_tokens``
- `system_prompt` 가 **messages[0] 로 들어가는가**, `None` 일 때 persona-only 로 떨어지는가
- API key 가 없을 때 **호출 없이** fallback 문구를 주는가
- ``usage`` 가 없을 때 `token_usage` 가 `None` 인가
- 🔴 **경계 로그**(`QA-64` ⓵ 의 목표) — 3구간이 네 경로에 붙였고 여기는 **빠져 있었다**

🔑 `get_openai_client()` 를 **내부에서** 부르므로 3구간의 `medicine_matcher` 테스트와
**같은 fixture** 를 쓴다(`guide_generator` 는 client 를 인자로 받아 달랐다).
"""

import json
import logging
from typing import Any

import httpx
import pytest
import respx

from ai_worker.core import openai_client as oc_module
from ai_worker.core.config import config
from ai_worker.domains.rag.response_generator import (
  _FALLBACK_ANSWER,
  _MAX_TOKENS,
  _TEMPERATURE,
  generate_response,
)
from app.core.llm_models import RAG_RESPONSE_MODEL

_URL = "https://api.openai.com/v1/chat/completions"
_MESSAGES = [{"role": "user", "content": "타이레놀 먹어도 돼?"}]


def _completion(answer: str, *, usage: dict[str, int] | None = None) -> dict[str, Any]:
  """OpenAI ``chat.completions`` 응답 봉투."""
  body: dict[str, Any] = {
    "id": "chatcmpl-test",
    "object": "chat.completion",
    "created": 0,
    "model": RAG_RESPONSE_MODEL,
    "choices": [
      {
        "index": 0,
        "message": {"role": "assistant", "content": answer, "refusal": None},
        "finish_reason": "stop",
      }
    ],
  }
  if usage is not None:
    body["usage"] = usage
  return body


def _route(answer: str = "타이레놀은 아세트아미노펜 계열입니다.", **kwargs: Any) -> respx.Route:
  """응답 라우트를 세운다."""
  return respx.post(_URL).mock(return_value=httpx.Response(200, json=_completion(answer, **kwargs)))


def _sent(route: respx.Route, call: int = 0) -> dict[str, Any]:
  """실제로 **전송된** 요청 본문."""
  sent: dict[str, Any] = json.loads(route.calls[call].request.content)
  return sent


@pytest.fixture(autouse=True)
def _client_ready(monkeypatch: pytest.MonkeyPatch) -> None:
  """싱글톤 초기화 + API key 주입 — `get_openai_client` 가 **실제로 돌게** 한다."""
  monkeypatch.setattr(oc_module, "_client", None)
  monkeypatch.setattr(oc_module, "_initialised", False)
  monkeypatch.setattr(config, "OPENAI_API_KEY", "sk-test-not-a-real-key")


class TestRequestContract:
  """무엇이 실제로 전송되는가."""

  @pytest.mark.asyncio
  @respx.mock
  async def test_request_carries_the_canonical_model_and_knobs(self) -> None:
    """🔴 `QA-07` ① 의 계약 + 생성 설정이 **요청에 실린다**."""
    route = _route()
    await generate_response(_MESSAGES)
    sent = _sent(route)
    assert sent["model"] == RAG_RESPONSE_MODEL
    assert sent["temperature"] == _TEMPERATURE
    assert sent["max_tokens"] == _MAX_TOKENS

  @pytest.mark.asyncio
  @respx.mock
  async def test_the_system_prompt_is_prepended(self) -> None:
    """컨텍스트가 담긴 system prompt 가 **첫 메시지**로 들어간다."""
    route = _route()
    await generate_response(_MESSAGES, system_prompt="[검색된 약품 정보]\n타이레놀이알서방정")
    msgs = _sent(route)["messages"]
    assert msgs[0]["role"] == "system"
    assert "[검색된 약품 정보]" in msgs[0]["content"]
    assert msgs[1] == _MESSAGES[0]

  @pytest.mark.asyncio
  @respx.mock
  async def test_without_a_system_prompt_a_persona_only_instruction_is_sent(self) -> None:
    """`system_prompt` 가 `None` 이면 persona-only 로 떨어진다 — **빈 system 이 아니다.**"""
    route = _route()
    await generate_response(_MESSAGES, system_prompt=None)
    msgs = _sent(route)["messages"]
    assert msgs[0]["role"] == "system"
    assert msgs[0]["content"].strip(), "persona-only 지시문이 비어 있다"


class TestResponseMapping:
  """응답 → `ChatCompletion` 변환."""

  @pytest.mark.asyncio
  @respx.mock
  async def test_answer_and_token_usage_are_mapped(self) -> None:
    _route("답변입니다", usage={"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30})
    result = await generate_response(_MESSAGES)
    assert result.answer == "답변입니다"
    assert result.token_usage is not None
    assert result.token_usage.model == RAG_RESPONSE_MODEL
    assert result.token_usage.total_tokens == 30

  @pytest.mark.asyncio
  @respx.mock
  async def test_a_missing_usage_block_yields_none(self) -> None:
    """``usage`` 가 없으면 `token_usage` 는 `None` 이다 — 0 으로 꾸미지 않는다."""
    _route("답변입니다")
    result = await generate_response(_MESSAGES)
    assert result.answer == "답변입니다"
    assert result.token_usage is None


class TestNoClient:
  """API key 가 없을 때."""

  @pytest.mark.asyncio
  @respx.mock
  async def test_no_api_key_returns_fallback_without_calling(self, monkeypatch: pytest.MonkeyPatch) -> None:
    """🔑 `get_openai_client` 분기가 **실제로** 돈다 — 호출 0 을 단언한다."""
    monkeypatch.setattr(config, "OPENAI_API_KEY", None)
    route = _route()
    result = await generate_response(_MESSAGES)
    assert not route.called
    assert result.answer == _FALLBACK_ANSWER
    assert result.token_usage is None


class TestBoundaryLog:
  """🔴 `QA-64` ⓵ 의 목표 — 경계 로그가 **실행**되는가."""

  @pytest.mark.asyncio
  @respx.mock
  async def test_the_boundary_log_actually_runs(
    self, caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch
  ) -> None:
    """**부착이 아니라 «실행» 을 단언한다**(3구간이 네 경로에 세운 계약).

    🔴 `caplog` 만으로는 아무것도 안 보인다(`D49`) — `setup_logger` 가 부모 로거
    (`ai_worker`)에 **`propagate = False`** 를 걸고 pytest 는 **root 에** 핸들러를 붙인다.
    그 한 줄을 켜 주어야 캡처가 일어난다.
    """
    monkeypatch.setattr(logging.getLogger("ai_worker"), "propagate", True)
    _route()
    with caplog.at_level(logging.INFO, logger="ai_worker"):
      await generate_response(_MESSAGES)
    assert any("[BOUNDARY] openai_rag_response 성공" in r.getMessage() for r in caplog.records), (
      "경계 로그가 없다 — log_boundary 가 실행되지 않았다"
    )

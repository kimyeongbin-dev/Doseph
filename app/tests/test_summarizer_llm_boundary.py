"""세션 요약(compact) LLM 의 **HTTP 경계** 테스트 (B-8 4구간 · `QA-64` ⓵).

왜 신설인가 — **이 경로는 테스트가 없었다**
--------------------------------------------
🔬 실측 2026-10-07: OpenAI 직접 호출 **6경로** 중 테스트 0개인 둘 중 하나였다.
그래서 다음이 전부 미검증이었다 —

- 요청에 실리는 ``model`` · ``temperature`` · ``max_tokens`` · system+user 두 메시지
- `prev_summary` 가 프롬프트에 들어가는가(이어 요약의 전제다)
- 메시지가 `_MIN_MESSAGES` 미만일 때 **호출 없이** `EMPTY`
- API key 부재·5xx 일 때 `FALLBACK` — 🟠 `QA-51` 이 부채로 등재한 **넓은 `except`** 가
  무엇을 삼키는가
- 모델이 **코드펜스나 인용으로 감싸 보낼 때** 벗겨지는가(`strip_code_fence`·`strip_quote_wrapping`)
- 🔴 **경계 로그**(`QA-64` ⓵ 의 목표)

🔴 **이 파일은 «지금 동작» 을 잠근다**(`CLAUDE.md` §6-2). `except Exception` 의 넓이를
좁히는 것은 `QA-51` 의 몫이다.
"""

import json
import logging
from typing import Any

import httpx
import pytest
import respx

from ai_worker.core import openai_client as oc_module
from ai_worker.core.config import config
from ai_worker.domains.session_compact.summarizer import (
  _MAX_TOKENS,
  _MIN_MESSAGES,
  _TEMPERATURE,
  summarize_session_messages,
)
from app.core.llm_models import SESSION_SUMMARY_MODEL
from app.dtos.rag import SummaryStatus

_URL = "https://api.openai.com/v1/chat/completions"
_MESSAGES = [
  {"role": "user", "content": "타이레놀 먹어도 돼?"},
  {"role": "assistant", "content": "아세트아미노펜 계열입니다."},
]


def _completion(summary: str, *, usage: dict[str, int] | None = None) -> dict[str, Any]:
  """OpenAI ``chat.completions`` 응답 봉투."""
  body: dict[str, Any] = {
    "id": "chatcmpl-test",
    "object": "chat.completion",
    "created": 0,
    "model": SESSION_SUMMARY_MODEL,
    "choices": [
      {
        "index": 0,
        "message": {"role": "assistant", "content": summary, "refusal": None},
        "finish_reason": "stop",
      }
    ],
  }
  if usage is not None:
    body["usage"] = usage
  return body


def _route(summary: str = "사용자는 타이레놀 복용 가능 여부를 물었다.", **kwargs: Any) -> respx.Route:
  """응답 라우트를 세운다."""
  return respx.post(_URL).mock(return_value=httpx.Response(200, json=_completion(summary, **kwargs)))


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
    """🔴 `QA-07` ① 의 계약 + 요약은 **보수적 설정**(낮은 temperature)이다."""
    route = _route()
    await summarize_session_messages(_MESSAGES)
    sent = _sent(route)
    assert sent["model"] == SESSION_SUMMARY_MODEL
    assert sent["temperature"] == _TEMPERATURE
    assert sent["max_tokens"] == _MAX_TOKENS

  @pytest.mark.asyncio
  @respx.mock
  async def test_system_and_user_messages_are_sent(self) -> None:
    """system(요약 지시) + user(대화 묶음) 두 개가 간다."""
    route = _route()
    await summarize_session_messages(_MESSAGES)
    msgs = _sent(route)["messages"]
    assert [m["role"] for m in msgs] == ["system", "user"]
    assert msgs[0]["content"].strip(), "요약 지시문이 비어 있다"
    assert "타이레놀" in msgs[1]["content"]

  @pytest.mark.asyncio
  @respx.mock
  async def test_a_previous_summary_is_carried_into_the_prompt(self) -> None:
    """🔑 이어 요약의 전제 — `prev_summary` 가 **프롬프트에 들어간다**."""
    route = _route()
    await summarize_session_messages(_MESSAGES, prev_summary="이전 요약: 간질환 병력 언급")
    assert "간질환 병력" in _sent(route)["messages"][1]["content"]


class TestHappyPath:
  """정상 응답."""

  @pytest.mark.asyncio
  @respx.mock
  async def test_a_valid_response_becomes_ok(self) -> None:
    _route(
      "사용자는 타이레놀 복용 가능 여부를 물었다.",
      usage={"prompt_tokens": 5, "completion_tokens": 7, "total_tokens": 12},
    )
    result = await summarize_session_messages(_MESSAGES)
    assert result.status == SummaryStatus.OK
    assert "타이레놀" in result.summary
    assert result.consumed_message_count == len(_MESSAGES)
    assert result.token_usage is not None
    assert result.token_usage.total_tokens == 12

  @pytest.mark.asyncio
  @respx.mock
  async def test_a_code_fenced_answer_is_unwrapped(self) -> None:
    """코드펜스만 감싼 응답은 깨끗하게 벗겨진다 — 그 정리 경로가 **처음 실행된다.**"""
    _route("```\n사용자는 복약 상담을 했다.\n```")
    result = await summarize_session_messages(_MESSAGES)
    assert "```" not in result.summary
    assert result.summary.startswith("사용자는")

  @pytest.mark.asyncio
  @respx.mock
  async def test_a_quoted_answer_is_unwrapped(self) -> None:
    """인용부호만 감싼 응답도 벗겨진다."""
    _route('"사용자는 복약 상담을 했다."')
    result = await summarize_session_messages(_MESSAGES)
    assert result.summary == "사용자는 복약 상담을 했다."

  @pytest.mark.asyncio
  @respx.mock
  async def test_fence_plus_quote_leaves_the_quote_behind(self) -> None:
    """🔴 **지금 동작을 잠근다 — 두 겹이면 한 겹이 남는다**(`QA-65` 로 등재).

    호출 순서가 ``strip_code_fence(strip_quote_wrapping(raw))`` 다. 바깥이 펜스면
    **먼저 도는 quote 벗기기가 아무것도 못 하고**, 펜스를 벗긴 뒤에는 다시 돌지 않는다
    ⇒ 인용부호가 요약 본문에 **그대로 남는다.**

    🔑 이 단언은 *«이게 옳다»* 가 아니라 *«지금 이렇다»* 다(`CLAUDE.md` §6-2).
    순서를 바꾸면 고쳐지지만 **행동 변경**이라 별건으로 보냈다.
    """
    _route('```\n"사용자는 복약 상담을 했다."\n```')
    result = await summarize_session_messages(_MESSAGES)
    assert "```" not in result.summary
    assert result.summary == '"사용자는 복약 상담을 했다."', "두 겹 중 인용부호가 남는 것이 현재 계약이다"


class TestFallbackPaths:
  """호출 없이 떨어지는 경로와 실패 경로."""

  @pytest.mark.asyncio
  @respx.mock
  async def test_too_few_messages_returns_empty_without_calling(self) -> None:
    """`_MIN_MESSAGES` 미만이면 요약할 가치가 없다 — 호출 0."""
    route = _route()
    result = await summarize_session_messages(_MESSAGES[: _MIN_MESSAGES - 1])
    assert not route.called
    assert result.status == SummaryStatus.EMPTY

  @pytest.mark.asyncio
  @respx.mock
  async def test_no_api_key_returns_fallback_without_calling(self, monkeypatch: pytest.MonkeyPatch) -> None:
    """🔑 `get_openai_client` 분기가 **실제로** 돈다."""
    monkeypatch.setattr(config, "OPENAI_API_KEY", None)
    route = _route()
    result = await summarize_session_messages(_MESSAGES)
    assert not route.called
    assert result.status == SummaryStatus.FALLBACK

  @pytest.mark.asyncio
  @respx.mock
  async def test_a_server_error_becomes_fallback(self) -> None:
    """5xx → `FALLBACK`.

    🟠 `QA-51` 이 등재한 **넓은 `except Exception`** 이 삼키는 것이 이것이다.
    🔴 이 테스트는 *지금 동작*을 잠근다 — 좁히는 작업은 그 항목의 몫이다.
    """
    route = respx.post(_URL).mock(return_value=httpx.Response(503, json={"error": {"message": "overloaded"}}))
    result = await summarize_session_messages(_MESSAGES)
    assert route.called
    assert result.status == SummaryStatus.FALLBACK
    assert result.summary == ""


class TestBoundaryLog:
  """🔴 `QA-64` ⓵ 의 목표 — 경계 로그가 **실행**되는가."""

  @pytest.mark.asyncio
  @respx.mock
  async def test_the_boundary_log_actually_runs(
    self, caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch
  ) -> None:
    """**부착이 아니라 «실행» 을 단언한다**.

    🔴 `caplog` 만으로는 안 보인다(`D49`) — 부모 로거(`ai_worker`)의
    `propagate = False` 때문이다.
    """
    monkeypatch.setattr(logging.getLogger("ai_worker"), "propagate", True)
    _route()
    with caplog.at_level(logging.INFO, logger="ai_worker"):
      await summarize_session_messages(_MESSAGES)
    assert any("[BOUNDARY] openai_session_summary 성공" in r.getMessage() for r in caplog.records), (
      "경계 로그가 없다 — log_boundary 가 실행되지 않았다"
    )

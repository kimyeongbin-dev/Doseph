"""1st LLM(Query Rewriter) 의 **HTTP 계약** 테스트 (B-8 3구간 · `QA-07` 전제).

왜 다시 썼나 — `parsed` 를 직접 주입하면 SDK 가 일을 안 한다
-------------------------------------------------------------
앞 판은 ``completion.choices[0].message.parsed`` 에 **이미 만들어진 Pydantic 객체**를
넣어 주었다. 그래서 다음이 전부 미검증이었다 —

- 요청에 실리는 ``model`` (= `QA-07` ① 이 모은 정본이 **실제로 전송되는가**)
- 🔴 요청에 실리는 ``response_format`` — **Structured Output 스키마가 전송되는가**.
  이것이 `QA-07` ② *«`json_object` → `parse(PydanticModel)` 승격»* 의 **계약**이다.
- SDK 의 **실제 파싱** — 모델이 준 JSON 문자열이 `QueryRewriterOutput` 으로 검증되는 경로
- ``refusal`` 응답에서 ``parsed`` 가 `None` 이 되는 **진짜 경로**
  (앞 판은 그 값을 손으로 `None` 으로 두었을 뿐이다)

🔑 **`parsed is None` 의 현실적 원인은 거절(refusal)** 이다. 그래서 그 분기를
*«schema 를 못 맞춘 극단 케이스»* 라는 설명 대신 **refusal 응답으로 재현**한다.
"""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest
import respx

from app.core.config import config
from app.core.llm_models import QUERY_REWRITER_MODEL
from app.dtos.query_rewriter import IntentType
from app.services.intent import query_rewriter as rewriter_module
from app.services.intent.query_rewriter import rewrite_query

_URL = "https://api.openai.com/v1/chat/completions"


# ── 공용 헬퍼 ──────────────────────────────────────────────────────────


def _completion(content: str | None, *, refusal: str | None = None) -> dict[str, Any]:
  """OpenAI ``chat.completions`` 응답 봉투.

  Args:
      content: assistant 가 돌려준 JSON 문자열. 거절이면 `None`.
      refusal: 거절 사유. 주면 SDK 가 ``parsed`` 를 `None` 으로 둔다.

  Returns:
      응답 본문 dict.
  """
  return {
    "id": "chatcmpl-test",
    "object": "chat.completion",
    "created": 0,
    "model": QUERY_REWRITER_MODEL,
    "choices": [
      {
        "index": 0,
        "message": {"role": "assistant", "content": content, "refusal": refusal},
        "finish_reason": "stop",
      }
    ],
    "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
  }


def _route(payload: dict[str, Any]) -> respx.Route:
  """모델이 `payload` 를 JSON 으로 돌려주도록 세운다 — **SDK 가 직접 파싱한다.**"""
  body = _completion(json.dumps(payload, ensure_ascii=False))
  return respx.post(_URL).mock(return_value=httpx.Response(200, json=body))


def _route_refusal(reason: str = "요청을 도울 수 없습니다.") -> respx.Route:
  """거절 응답 — `parsed` 가 `None` 이 되는 **진짜 경로**."""
  body = _completion(None, refusal=reason)
  return respx.post(_URL).mock(return_value=httpx.Response(200, json=body))


def _sent(route: respx.Route, call: int = 0) -> dict[str, Any]:
  """실제로 **전송된** 요청 본문."""
  return json.loads(route.calls[call].request.content)


#: 최소 정상 응답 — intent 별로 필요한 필드만 채운다.
_GREETING = {"intent": "greeting", "direct_answer": "안녕하세요"}


@pytest.fixture(autouse=True)
def _client_ready(monkeypatch: pytest.MonkeyPatch) -> None:
  """싱글톤 초기화 + API key 주입 — `_get_client` 가 **실제로 돌게** 한다."""
  monkeypatch.setattr(rewriter_module, "_client", None)
  monkeypatch.setattr(rewriter_module, "_initialised", False)
  monkeypatch.setattr(config, "OPENAI_API_KEY", "sk-test-not-a-real-key")


class TestRequestContract:
  """🔴 `QA-07` ①② 의 계약 — 무엇이 실제로 전송되는가."""

  @pytest.mark.asyncio
  @respx.mock
  async def test_request_carries_the_canonical_model(self) -> None:
    """모델명을 한 곳으로 모아도 **요청에 실리지 않으면** 의미가 없다."""
    route = _route(_GREETING)
    await rewrite_query(messages=[{"role": "user", "content": "안녕"}])
    assert _sent(route)["model"] == QUERY_REWRITER_MODEL

  @pytest.mark.asyncio
  @respx.mock
  async def test_request_carries_the_structured_output_schema(self) -> None:
    """🔴 **스키마 강제의 계약**: `response_format` 이 JSON Schema 로 전송된다.

    `json_object` 와 `json_schema` 의 차이가 여기서 드러난다 — 전자는 *«JSON 이기만 하면
    된다»* 이고 후자는 **필드까지 모델이 지킨다.** `QA-07` ② 가 승격이라 부른 것이 이것이다.
    """
    route = _route(_GREETING)
    await rewrite_query(messages=[{"role": "user", "content": "안녕"}])
    fmt = _sent(route)["response_format"]
    assert fmt["type"] == "json_schema"
    assert fmt["json_schema"]["name"] == "QueryRewriterOutput"
    assert fmt["json_schema"]["strict"] is True


class TestMessageAssembly:
  """system_prompt + medical_context 합성."""

  @pytest.mark.asyncio
  @respx.mock
  async def test_medical_context_appended_to_system_prompt(self) -> None:
    route = _route({
      "intent": "domain_question",
      "rewritten_query": "간 질환 환자 타이레놀 복용",
      "metadata": {"target_drugs": ["타이레놀"], "target_ingredients": ["아세트아미노펜"]},
    })
    await rewrite_query(
      messages=[{"role": "user", "content": "타이레놀 먹어도 돼?"}],
      medical_context="[사용자 의학 컨텍스트]\n- 기저질환: 간질환",
    )
    msgs = _sent(route)["messages"]
    assert msgs[0]["role"] == "system"
    assert "Query Rewriter" in msgs[0]["content"]
    assert "[사용자 의학 컨텍스트]" in msgs[0]["content"]
    assert "간질환" in msgs[0]["content"]
    assert msgs[1] == {"role": "user", "content": "타이레놀 먹어도 돼?"}

  @pytest.mark.asyncio
  @respx.mock
  async def test_no_medical_context_only_system_prompt(self) -> None:
    route = _route(_GREETING)
    await rewrite_query(messages=[{"role": "user", "content": "안녕"}], medical_context=None)
    assert "[사용자 의학 컨텍스트]" not in _sent(route)["messages"][0]["content"]


class TestFallback:
  """`parsed` 가 없을 때와 client 가 없을 때."""

  @pytest.mark.asyncio
  @respx.mock
  async def test_a_refusal_falls_back_to_ambiguous(self) -> None:
    """🔑 거절 → `parsed` 가 `None` → ambiguous fallback.

    앞 판은 `parsed` 를 손으로 `None` 으로 두었다. 이제 **SDK 가 refusal 을 보고**
    그렇게 만든다 — 같은 결과에 도달하는 **실제 경로**다.
    """
    route = _route_refusal()
    result = await rewrite_query(messages=[{"role": "user", "content": "..."}])
    assert route.called
    assert result.intent == IntentType.AMBIGUOUS
    assert result.direct_answer is not None
    assert "질문을 정확히 이해하지 못했어요" in result.direct_answer

  @pytest.mark.asyncio
  @respx.mock
  async def test_no_api_key_returns_ambiguous_without_calling(self, monkeypatch: pytest.MonkeyPatch) -> None:
    """API key 없음 → 호출 없이 fallback. 🔑 `_get_client` 분기가 **실제로** 돈다."""
    monkeypatch.setattr(config, "OPENAI_API_KEY", None)
    route = _route(_GREETING)
    result = await rewrite_query(messages=[{"role": "user", "content": "안녕"}])
    assert not route.called
    assert result.intent == IntentType.AMBIGUOUS
    assert "AI 응답 설정" in (result.direct_answer or "")


class TestIntentBranches:
  """네 intent 분기 — 🔑 이제 **SDK 가 파싱한 결과**가 흐른다."""

  @pytest.mark.asyncio
  @respx.mock
  async def test_greeting_branch(self) -> None:
    _route(_GREETING)
    result = await rewrite_query(messages=[{"role": "user", "content": "안녕"}])
    assert result.intent == IntentType.GREETING
    assert result.direct_answer == "안녕하세요"
    assert result.rewritten_query is None
    assert result.metadata is None

  @pytest.mark.asyncio
  @respx.mock
  async def test_out_of_scope_branch(self) -> None:
    _route({"intent": "out_of_scope", "direct_answer": "저는 약 챗봇이에요"})
    result = await rewrite_query(messages=[{"role": "user", "content": "오늘 날씨"}])
    assert result.intent == IntentType.OUT_OF_SCOPE
    assert result.rewritten_query is None

  @pytest.mark.asyncio
  @respx.mock
  async def test_domain_question_with_metadata(self) -> None:
    _route({
      "intent": "domain_question",
      "rewritten_query": "간 질환 환자가 와파린 복용 중 아세트아미노펜 병용 시 출혈 위험",
      "metadata": {
        "target_drugs": ["타이레놀"],
        "target_ingredients": ["아세트아미노펜"],
        "target_conditions": ["liver_disease"],
        "target_sections": ["drug_interaction", "adverse_reaction"],
        "interaction_concerns": ["와파린나트륨"],
      },
    })
    result = await rewrite_query(
      messages=[{"role": "user", "content": "타이레놀 먹어도 돼?"}],
      medical_context="[사용자 의학 컨텍스트]\n- 기저질환: 간질환\n- 복용 중인 약: 쿠파린정",
    )
    assert result.intent == IntentType.DOMAIN_QUESTION
    assert result.direct_answer is None
    assert result.rewritten_query is not None
    assert "간 질환" in result.rewritten_query
    assert result.metadata is not None
    assert result.metadata.target_ingredients == ["아세트아미노펜"]
    assert result.metadata.target_conditions == ["liver_disease"]
    assert result.metadata.interaction_concerns == ["와파린나트륨"]
    assert result.metadata.target_sections == ["drug_interaction", "adverse_reaction"]

  @pytest.mark.asyncio
  @respx.mock
  async def test_ambiguous_branch(self) -> None:
    _route({"intent": "ambiguous", "direct_answer": "어느 약?"})
    result = await rewrite_query(messages=[{"role": "user", "content": "그거 먹어도 돼?"}])
    assert result.intent == IntentType.AMBIGUOUS
    assert result.direct_answer == "어느 약?"

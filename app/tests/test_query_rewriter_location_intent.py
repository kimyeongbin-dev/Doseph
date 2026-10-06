"""Query Rewriter 의 location_search 의도 분류 테스트.

IntentType.LOCATION_SEARCH + LocationQuery DTO 가 1st LLM Structured Output 으로
정상 round-trip 되는지 검증한다.

🔤 **2026-10-07 (B-8 3구간 · `QA-07` 전제)** — OpenAI 모킹을 ``_get_client`` 교체에서
**respx(HTTP 레벨)** 로 바꿨다. 앞 판은 ``message.parsed`` 에 **이미 만들어진 Pydantic
객체**를 넣어 주었으므로 *«LLM 이 돌려준 JSON 이 DTO 로 파싱되는가»* 가 **미검증**이었다 —
round-trip 을 검증한다면서 **round-trip 의 절반(파싱)을 건너뛴 것**이다.

⚪ 이 파일의 DTO·enum·프롬프트 테스트는 OpenAI 와 무관하므로 그대로 둔다.
"""

import json
from typing import Any

import httpx
import pytest
import respx

from app.core.config import config
from app.core.llm_models import QUERY_REWRITER_MODEL
from app.dtos.query_rewriter import (
  IntentType,
  LocationCategory,
  LocationMode,
  LocationQuery,
)
from app.services.intent import query_rewriter

_URL = "https://api.openai.com/v1/chat/completions"


def _route(payload: dict[str, Any]) -> respx.Route:
  """모델이 `payload` 를 JSON 으로 돌려주도록 세운다 — **SDK 가 직접 파싱한다.**"""
  body = {
    "id": "chatcmpl-test",
    "object": "chat.completion",
    "created": 0,
    "model": QUERY_REWRITER_MODEL,
    "choices": [
      {
        "index": 0,
        "message": {
          "role": "assistant",
          "content": json.dumps(payload, ensure_ascii=False),
          "refusal": None,
        },
        "finish_reason": "stop",
      }
    ],
    "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
  }
  return respx.post(_URL).mock(return_value=httpx.Response(200, json=body))


@pytest.fixture(autouse=True)
def _client_ready(monkeypatch: pytest.MonkeyPatch) -> None:
  """싱글톤 초기화 + API key 주입 — `_get_client` 가 **실제로 돌게** 한다."""
  monkeypatch.setattr(query_rewriter, "_client", None)
  monkeypatch.setattr(query_rewriter, "_initialised", False)
  monkeypatch.setattr(config, "OPENAI_API_KEY", "sk-test-not-a-real-key")


# ── DTO round-trip ─────────────────────────────────────────────


class TestLocationQueryDto:
  def test_gps_mode_with_pharmacy_category(self) -> None:
    q = LocationQuery(mode=LocationMode.GPS, category=LocationCategory.PHARMACY, radius_m=1500)
    assert q.mode == LocationMode.GPS
    assert q.category == LocationCategory.PHARMACY
    assert q.radius_m == 1500
    assert q.query is None

  def test_keyword_mode_with_query(self) -> None:
    q = LocationQuery(mode=LocationMode.KEYWORD, query="강남역 약국")
    assert q.mode == LocationMode.KEYWORD
    assert q.query == "강남역 약국"
    assert q.category is None
    assert q.radius_m == 1000  # 기본값


# ── IntentType.LOCATION_SEARCH 가 enum 에 추가되었는지 ───────────


class TestIntentEnum:
  def test_location_search_member_exists(self) -> None:
    assert IntentType.LOCATION_SEARCH.value == "location_search"

  def test_intent_count_is_at_least_five(self) -> None:
    assert len(list(IntentType)) >= 5


# ── 1st LLM 분류 결과 round-trip ────────────────────────────────


class TestRewriteQueryLocationIntent:
  """🔑 이제 **LLM 이 준 JSON 이 DTO 로 파싱되는 경로**가 실제로 돈다."""

  @pytest.mark.asyncio
  @respx.mock
  async def test_gps_intent_pharmacy(self) -> None:
    _route({
      "intent": "location_search",
      "location_query": {
        "mode": LocationMode.GPS.value,
        "category": LocationCategory.PHARMACY.value,
        "radius_m": 1000,
      },
    })
    out = await query_rewriter.rewrite_query(
      messages=[{"role": "user", "content": "내 주변 약국 찾아줘"}],
    )
    assert out.intent == IntentType.LOCATION_SEARCH
    assert out.location_query is not None
    assert out.location_query.mode == LocationMode.GPS
    assert out.location_query.category == LocationCategory.PHARMACY

  @pytest.mark.asyncio
  @respx.mock
  async def test_keyword_intent_landmark(self) -> None:
    _route({
      "intent": "location_search",
      "location_query": {"mode": LocationMode.KEYWORD.value, "query": "강남역 약국"},
    })
    out = await query_rewriter.rewrite_query(
      messages=[{"role": "user", "content": "강남역 약국 찾아줘"}],
    )
    assert out.intent == IntentType.LOCATION_SEARCH
    assert out.location_query is not None
    assert out.location_query.mode == LocationMode.KEYWORD
    assert out.location_query.query == "강남역 약국"

  @pytest.mark.asyncio
  @respx.mock
  async def test_domain_question_unaffected(self) -> None:
    """회귀 보호 — 위치 검색 무관한 의학 질문은 domain_question 으로 분류."""
    _route({
      "intent": "domain_question",
      "rewritten_query": "타이레놀(아세트아미노펜) 부작용",
      "metadata": {"target_ingredients": ["아세트아미노펜"]},
    })
    out = await query_rewriter.rewrite_query(
      messages=[{"role": "user", "content": "타이레놀 부작용"}],
    )
    assert out.intent == IntentType.DOMAIN_QUESTION
    assert out.location_query is None
    assert out.rewritten_query == "타이레놀(아세트아미노펜) 부작용"

  @pytest.mark.asyncio
  @respx.mock
  async def test_the_location_schema_is_sent_to_the_model(self) -> None:
    """🔴 `QA-07` ② 의 계약 — `location_query` 가 **전송되는 스키마에 들어 있다**.

    DTO 에 필드를 추가해도 **스키마가 모델에게 가지 않으면** 모델은 그 필드를 채울 수 없다.
    앞 판은 요청을 만들지 않았으므로 이 단언이 **원리적으로 불가능**했다.
    """
    route = _route({"intent": "greeting", "direct_answer": "안녕"})
    await query_rewriter.rewrite_query(messages=[{"role": "user", "content": "안녕"}])
    sent = json.loads(route.calls[0].request.content)
    schema = sent["response_format"]["json_schema"]["schema"]
    assert "location_query" in schema["properties"]


# ── system_prompt 에 location_search 분류 규칙 포함 검증 ──────


class TestSystemPromptHasLocationRule:
  def test_prompt_mentions_location_search(self) -> None:
    prompt: Any = query_rewriter.SYSTEM_PROMPT
    assert "location_search" in prompt
    # gps 모드 표현 (내 주변 · 근처 · 가까운) 안내
    assert any(kw in prompt for kw in ("내 주변", "근처", "가까운"))
    # keyword 모드 표현 (지명 · 랜드마크) 안내
    assert any(kw in prompt for kw in ("지명", "강남역", "랜드마크"))

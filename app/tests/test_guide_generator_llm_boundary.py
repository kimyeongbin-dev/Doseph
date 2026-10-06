"""생활습관 가이드 LLM 의 **HTTP 경계** 테스트 (B-8 3구간 · `QA-07` ②).

왜 신설인가 — **이 경로는 테스트가 없었다**
--------------------------------------------
🔬 실측 2026-10-07: OpenAI 를 직접 호출하는 경로 **6곳** 중 `ai_worker` 의 4곳은 테스트가
0개였고 `generate_guide_payload` 가 그중 하나다. 그래서 다음이 전부 미검증이었다 —

- 요청에 실리는 ``model`` · ``response_format`` · ``temperature`` · ``seed``
- 🔴 **재시도 루프** — LLM 이 `recommended_challenges` **15개 룰**을 위반하면
  `ValidationError` 가 나고 **seed 를 +1 해서 다시 부른다.** 이 동작이 코드 주석으로만
  설명돼 있었고 **한 번도 실행되지 않았다.**
- 모든 재시도 실패 시 마지막 에러 전파 · `OpenAIError` → `ValueError` 정규화

🔑 **`client` 를 인자로 받는 함수라** respx 만으로 충분하다 — 싱글톤·API key 주입이 필요 없다.

🔴 **이 파일은 «지금 동작» 을 잠근다**(`CLAUDE.md` §6-2). `response_format` 단언은
**승격 전 상태**이고, `QA-07` ② 로 올리면 Red 가 되어야 정상이다.
"""

import json
from typing import Any

import httpx
from openai import AsyncOpenAI
import pytest
import respx

from ai_worker.domains.lifestyle.guide_generator import (
  _MAX_GENERATE_RETRIES,
  generate_guide_payload,
)
from app.core.llm_models import LIFESTYLE_GUIDE_MODEL

_URL = "https://api.openai.com/v1/chat/completions"

#: 프롬프트 빌더가 요구하는 카테고리 다섯 — 가이드 본문 필드와 짝이다.
_GUIDE_TEXT = {
  "diet": "식단 안내",
  "sleep": "수면 안내",
  "exercise": "운동 안내",
  "symptom": "증상 관찰 안내",
  "interaction": "약물-생활 상호작용 안내",
}

_MEDS = [{"medicine_name": "타이레놀정", "dose_per_intake": "1정"}]
_PROFILE = {"나이": 30, "성별": "여성"}


def _challenges(count: int) -> list[dict[str, Any]]:
  """`count` 개의 추천 챌린지. 🔑 **정확히 15개**가 DTO 계약이다."""
  return [
    {
      "category": "diet",
      "title": f"챌린지-{i}",
      "description": "설명",
      "target_days": 7,
      "difficulty": "easy",
    }
    for i in range(count)
  ]


def _completion(payload: dict[str, Any]) -> dict[str, Any]:
  """OpenAI ``chat.completions`` 응답 봉투."""
  return {
    "id": "chatcmpl-test",
    "object": "chat.completion",
    "created": 0,
    "model": LIFESTYLE_GUIDE_MODEL,
    "system_fingerprint": "fp_test",
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


def _ok(count: int = 15) -> dict[str, Any]:
  """스키마를 만족하는 응답 본문."""
  return _completion({**_GUIDE_TEXT, "recommended_challenges": _challenges(count)})


def _client() -> AsyncOpenAI:
  """respx 가 가로채므로 키는 형식만 맞으면 된다."""
  return AsyncOpenAI(api_key="sk-test-not-a-real-key")


def _sent(route: respx.Route, call: int = 0) -> dict[str, Any]:
  """실제로 **전송된** 요청 본문."""
  return json.loads(route.calls[call].request.content)


class TestRequestContract:
  """무엇이 실제로 전송되는가."""

  @pytest.mark.asyncio
  @respx.mock
  async def test_request_carries_the_canonical_model_and_determinism_knobs(self) -> None:
    """🔴 `QA-07` ① 의 계약 + **결정성 설정**(`temperature` · `seed`).

    가이드는 *같은 입력이면 같은 출력*이어야 하므로 `temperature=0` 과 `seed` 를 보낸다.
    그 둘이 실제로 요청에 실리는지는 지금까지 **아무도 보지 않았다.**
    """
    route = respx.post(_URL).mock(return_value=httpx.Response(200, json=_ok()))
    await generate_guide_payload(_MEDS, _PROFILE, _client())
    sent = _sent(route)
    assert sent["model"] == LIFESTYLE_GUIDE_MODEL
    assert sent["temperature"] == 0.0
    assert isinstance(sent["seed"], int)

  @pytest.mark.asyncio
  @respx.mock
  async def test_request_carries_the_structured_output_schema(self) -> None:
    """🔴 `QA-07` ② 의 계약 — **스키마가 전송된다**(`json_object` 에서 승격했다).

    ✅ **이 테스트가 승격의 증거다** — 승격 전에는 같은 자리에서
    `{"type": "json_object"}` 를 단언하고 있었고, 승격이 그 단언을 Red 로 만들었다.
    """
    route = respx.post(_URL).mock(return_value=httpx.Response(200, json=_ok()))
    await generate_guide_payload(_MEDS, _PROFILE, _client())
    fmt = _sent(route)["response_format"]
    assert fmt["type"] == "json_schema"
    assert fmt["json_schema"]["name"] == "LlmGuideResponse"
    assert fmt["json_schema"]["strict"] is True

  @pytest.mark.asyncio
  @respx.mock
  async def test_the_schema_does_not_carry_min_items(self) -> None:
    """🔴 **strict 모드는 `minItems` 를 지원하지 않는다** — 보내면 거부될 수 있다.

    그래서 챌린지 15개 룰을 `Field(min_length=...)` 에서 **`field_validator` 로 옮겼다**.
    검증은 그대로 돌고(바로 아래 재시도 테스트가 증명한다) **스키마에는 안 나타난다.**
    🔑 이 단언이 없으면 누군가 제약을 `Field` 로 되돌려도 아무 신호가 없다.
    """
    route = respx.post(_URL).mock(return_value=httpx.Response(200, json=_ok()))
    await generate_guide_payload(_MEDS, _PROFILE, _client())
    schema = json.dumps(_sent(route)["response_format"]["json_schema"]["schema"])
    assert "minItems" not in schema
    assert "maxItems" not in schema


class TestHappyPath:
  """정상 응답."""

  @pytest.mark.asyncio
  @respx.mock
  async def test_a_valid_response_is_parsed(self) -> None:
    """다섯 카테고리 + 챌린지 15개 → 검증된 DTO."""
    respx.post(_URL).mock(return_value=httpx.Response(200, json=_ok()))
    result = await generate_guide_payload(_MEDS, _PROFILE, _client())
    assert result.diet == "식단 안내"
    assert result.interaction == "약물-생활 상호작용 안내"
    assert len(result.recommended_challenges) == 15

  @pytest.mark.asyncio
  @respx.mock
  async def test_the_same_input_gets_the_same_seed(self) -> None:
    """🔑 결정성 — 같은 입력이면 **같은 seed** 로 부른다."""
    route = respx.post(_URL).mock(return_value=httpx.Response(200, json=_ok()))
    await generate_guide_payload(_MEDS, _PROFILE, _client())
    first = _sent(route)["seed"]
    await generate_guide_payload(_MEDS, _PROFILE, _client())
    assert _sent(route, 1)["seed"] == first


class TestRetryLoop:
  """🔴 재시도 루프 — 코드 주석으로만 설명돼 있던 동작."""

  @pytest.mark.asyncio
  @respx.mock
  async def test_a_challenge_count_violation_is_retried_with_a_new_seed(self) -> None:
    """챌린지가 15개가 아니면 **seed 를 바꿔 다시** 부른다.

    `min_length=max_length=15` 를 Pydantic 이 잡고, 루프가 `seed+1` 로 재시도한다.
    """
    route = respx.post(_URL).mock(
      side_effect=[
        httpx.Response(200, json=_ok(5)),  # 룰 위반 — 5개만
        httpx.Response(200, json=_ok(15)),  # 재시도에서 충족
      ]
    )
    result = await generate_guide_payload(_MEDS, _PROFILE, _client())
    assert len(result.recommended_challenges) == 15
    assert route.call_count == 2, "위반 뒤 재시도가 일어나야 한다"
    assert _sent(route, 1)["seed"] != _sent(route, 0)["seed"], "seed 가 변해야 다른 sample 이 나온다"

  @pytest.mark.asyncio
  @respx.mock
  async def test_every_attempt_failing_raises(self) -> None:
    """모든 재시도가 룰을 위반하면 마지막 에러를 올린다 — 호출자가 fail 처리한다."""
    route = respx.post(_URL).mock(return_value=httpx.Response(200, json=_ok(3)))
    with pytest.raises(ValueError, match="파싱 오류"):
      await generate_guide_payload(_MEDS, _PROFILE, _client())
    assert route.call_count == _MAX_GENERATE_RETRIES


class TestErrorNormalisation:
  """OpenAI 예외가 `ValueError` 로 정규화되는가."""

  @pytest.mark.asyncio
  @respx.mock
  async def test_a_server_error_becomes_a_value_error(self) -> None:
    """🔴 5xx → `ValueError`.

    `OpenAIError` 를 그대로 올리면 호출자(`jobs`)가 OpenAI 타입을 알아야 한다.
    경계에서 정규화하는 것이 지금 계약이다.
    """
    respx.post(_URL).mock(return_value=httpx.Response(503, json={"error": {"message": "overloaded"}}))
    with pytest.raises(ValueError, match="LLM 호출 오류"):
      await generate_guide_payload(_MEDS, _PROFILE, _client())

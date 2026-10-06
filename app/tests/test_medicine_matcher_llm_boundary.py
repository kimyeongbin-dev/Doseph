"""OCR 약품 추출 LLM 의 **HTTP 경계** 테스트 (B-8 3구간 · `QA-07` ②).

왜 신설인가 — **이 경로는 테스트가 없었다**
--------------------------------------------
🔬 실측 2026-10-07: OpenAI 를 직접 호출하는 경로 **6곳** 중 `ai_worker` 의 **4곳은
테스트가 0개**였다. `_extract_medicines_with_llm` 이 그중 하나다. 그래서 다음이 전부
미검증이었다 —

- 요청에 실리는 ``model`` (= `QA-07` ① 이 모은 정본)
- 요청에 실리는 ``response_format``
- ``items`` 키가 없을 때 · API key 가 없을 때 · 5xx 일 때의 **빈 리스트 반환**
- 🟠 `QA-51` 이 *«부채»* 로 등재한 **넓은 `except Exception`** 이 실제로 무엇을 삼키는가

🔴 **이 파일은 «지금 동작» 을 잠그는 것**이고 *«이게 옳다»* 고 말하는 게 아니다
(`CLAUDE.md` §6-2). 특히 `response_format` 단언은 **승격 전 상태**를 잠근다 —
`QA-07` ② 로 `parse(PydanticModel)` 로 올리면 **이 단언이 Red 가 되어야 정상**이고,
그 Red 가 *«승격이 실제로 일어났다»* 는 증거다.
"""

import json
from typing import Any

import httpx
import pytest
import respx

from ai_worker.core import openai_client as oc_module
from ai_worker.core.config import config
from ai_worker.domains.ocr.medicine_matcher import _extract_medicines_with_llm
from app.core.llm_models import MEDICINE_MATCHER_MODEL

_URL = "https://api.openai.com/v1/chat/completions"

#: 프롬프트가 요구하는 항목 모양 — 이름/용량/유형 + 복용 3종 + 지시
_ITEM = {
  "name": "타이레놀정",
  "strength": "500mg",
  "type": "의약품",
  "dose": 1,
  "daily_count": 3,
  "total_days": 5,
  "instruction": "식후 30분",
}


def _completion(content: str) -> dict[str, Any]:
  """OpenAI ``chat.completions`` 응답 봉투."""
  return {
    "id": "chatcmpl-test",
    "object": "chat.completion",
    "created": 0,
    "model": MEDICINE_MATCHER_MODEL,
    "choices": [
      {
        "index": 0,
        "message": {"role": "assistant", "content": content, "refusal": None},
        "finish_reason": "stop",
      }
    ],
    "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
  }


def _route(payload: dict[str, Any]) -> respx.Route:
  """모델이 `payload` 를 JSON 으로 돌려주도록 세운다."""
  body = _completion(json.dumps(payload, ensure_ascii=False))
  return respx.post(_URL).mock(return_value=httpx.Response(200, json=body))


def _sent(route: respx.Route, call: int = 0) -> dict[str, Any]:
  """실제로 **전송된** 요청 본문."""
  return json.loads(route.calls[call].request.content)


@pytest.fixture(autouse=True)
def _client_ready(monkeypatch: pytest.MonkeyPatch) -> None:
  """싱글톤 초기화 + API key 주입 — `get_openai_client` 가 **실제로 돌게** 한다.

  🔑 `ai_worker` 는 자기 `config` 를 쓴다(`ai_worker.core.config`) — `app` 쪽과 다른 객체다.
  """
  monkeypatch.setattr(oc_module, "_client", None)
  monkeypatch.setattr(oc_module, "_initialised", False)
  monkeypatch.setattr(config, "OPENAI_API_KEY", "sk-test-not-a-real-key")


class TestRequestContract:
  """무엇이 실제로 전송되는가."""

  @pytest.mark.asyncio
  @respx.mock
  async def test_request_carries_the_canonical_model(self) -> None:
    """🔴 `QA-07` ① 의 계약 — 모아 둔 정본이 **요청에 실린다**."""
    route = _route({"items": [_ITEM]})
    await _extract_medicines_with_llm("타이레놀정 500mg")
    assert _sent(route)["model"] == MEDICINE_MATCHER_MODEL

  @pytest.mark.asyncio
  @respx.mock
  async def test_request_carries_the_structured_output_schema(self) -> None:
    """🔴 `QA-07` ② 의 계약 — **스키마가 전송된다**(`json_object` 에서 승격했다).

    🔑 **차이**: `json_object` 는 *«JSON 이기만 하면 된다»* 라 필드 이름·타입을 모델이
    지킬 의무가 없었다. `json_schema` + `strict` 는 **모델이 지킨다.**

    ✅ **이 테스트가 승격의 증거다** — 승격 전에는 같은 자리에서
    `{"type": "json_object"}` 를 단언하고 있었고, 승격이 그 단언을 Red 로 만들었다.
    """
    route = _route({"items": [_ITEM]})
    await _extract_medicines_with_llm("타이레놀정 500mg")
    fmt = _sent(route)["response_format"]
    assert fmt["type"] == "json_schema"
    assert fmt["json_schema"]["name"] == "OcrLlmExtraction"
    assert fmt["json_schema"]["strict"] is True
    # 🔑 항목 필드가 스키마에 실제로 들어 있어야 모델이 그 모양을 지킨다.
    item_schema = fmt["json_schema"]["schema"]["$defs"]["OcrLlmExtractedItem"]
    assert set(item_schema["required"]) == {
      "name",
      "strength",
      "type",
      "dose",
      "daily_count",
      "total_days",
      "instruction",
    }

  @pytest.mark.asyncio
  @respx.mock
  async def test_the_ocr_text_is_in_the_prompt(self) -> None:
    """OCR 원문이 프롬프트에 들어간다 — 그래야 모델이 문맥을 본다."""
    route = _route({"items": [_ITEM]})
    await _extract_medicines_with_llm("쿠파린정 2mg 1일 3회")
    assert "쿠파린정 2mg 1일 3회" in _sent(route)["messages"][0]["content"]


class TestExtraction:
  """정상 추출."""

  @pytest.mark.asyncio
  @respx.mock
  async def test_items_are_returned_as_dicts(self) -> None:
    """반환은 `list[dict]` 다 — 사용처가 `item.get(...)` 으로 읽는다."""
    _route({"items": [_ITEM]})
    result = await _extract_medicines_with_llm("타이레놀정 500mg")
    assert len(result) == 1
    assert result[0]["name"] == "타이레놀정"
    assert result[0]["strength"] == "500mg"
    assert result[0]["dose"] == 1

  @pytest.mark.asyncio
  @respx.mock
  async def test_a_null_dose_survives_as_none(self) -> None:
    """프롬프트가 *«없으면 null»* 이라 지시한다 — 그 값이 그대로 흐른다.

    🔑 사용처가 `item.get("dose")` 로 받아 `None` 을 그대로 쓴다(`or ""` 를 안 붙인다).
    """
    _route({"items": [{**_ITEM, "dose": None, "total_days": None}]})
    result = await _extract_medicines_with_llm("용량 미기재 약")
    assert result[0]["dose"] is None
    assert result[0]["total_days"] is None


class TestEmptyPaths:
  """빈 리스트로 떨어지는 세 경로 — 🔴 전부 미검증이었다."""

  @pytest.mark.asyncio
  @respx.mock
  async def test_no_items_key_returns_empty(self) -> None:
    """`items` 키가 없으면 빈 리스트. `result.get("items", [])` 의 기본값 경로."""
    _route({"unexpected": "shape"})
    assert await _extract_medicines_with_llm("아무 텍스트") == []

  @pytest.mark.asyncio
  @respx.mock
  async def test_no_api_key_returns_empty_without_calling(self, monkeypatch: pytest.MonkeyPatch) -> None:
    """API key 없음 → 호출 없이 빈 리스트. `get_openai_client` 분기가 실제로 돈다."""
    monkeypatch.setattr(config, "OPENAI_API_KEY", None)
    route = _route({"items": [_ITEM]})
    assert await _extract_medicines_with_llm("타이레놀") == []
    assert not route.called

  @pytest.mark.asyncio
  @respx.mock
  async def test_a_server_error_is_swallowed_into_empty(self) -> None:
    """5xx → 빈 리스트.

    🟠 `QA-51` 이 등재한 **넓은 `except Exception`** 이 삼키는 것이 이것이다.
    🔴 그 넓이는 **부채로 등재된 상태**이고 이 테스트는 *지금 동작*을 잠근다 —
    좁히는 작업(`openai` 예외 + `json.JSONDecodeError`)은 `QA-51` 의 몫이다.
    """
    route = respx.post(_URL).mock(return_value=httpx.Response(503, json={"error": {"message": "overloaded"}}))
    assert await _extract_medicines_with_llm("타이레놀") == []
    assert route.called

  @pytest.mark.asyncio
  @respx.mock
  async def test_malformed_json_is_swallowed_into_empty(self) -> None:
    """🔴 `json_object` 의 한계가 드러나는 자리 — 모델이 JSON 이 아닌 것을 주면.

    승격(`QA-07` ②)의 근거가 여기 있다: 스키마가 없으면 **파싱 실패가 런타임까지 온다.**
    """
    respx.post(_URL).mock(return_value=httpx.Response(200, json=_completion("이건 JSON 이 아니다")))
    assert await _extract_medicines_with_llm("타이레놀") == []

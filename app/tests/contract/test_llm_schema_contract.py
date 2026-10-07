"""모델이 **우리 스키마를 실제로 지키는가** — 실제 OpenAI 호출 (`QA-64` ⓶).

왜 이 파일이 필요한가 — respx 가 못 보는 것
-------------------------------------------
B-8 3구간이 OpenAI 경계 6곳을 `respx` 로 덮었다. 그런데 respx 는 **우리가 만든 응답**을
돌려주므로 다음은 **원리적으로 미검증**이다:

- 모델이 ``response_format`` 스키마를 **실제로 지키는가**
- OpenAI 가 우리 ``strict`` 스키마를 **받아들이는가**(거부하면 400 이고 respx 는 못 본다)
- 🔴 **챌린지 15개** — 3구간이 `minItems` 를 스키마에서 **뺐다**(strict 모드 미지원).
  그래서 그 개수는 **프롬프트와 재시도에만** 의존하고 **아무도 검증하지 않는다.**

🔑 **각 경로의 «실제 모델» 로 부른다.** *«무료 모델»* 이나 더 싼 모델로 바꾸면
**검증 대상이 아닌 모델**을 재는 것이고, 그 초록은 거짓이다
(`QA-07` ③ 이 *«무료 모델»* 이라 적었던 전제를 그래서 버렸다 — 경위 = `QA-64`).

운용 (`QA-64` ⓶ 판정, 2026-10-07)
---------------------------------
- **언제**: DTO·프롬프트가 바뀐 PR 에서만(CI 가 경로로 판정)
- **어떻게**: 🔴 **막지 않고 보고** — 외부 장애가 우리 PR 을 막지 않게
- **비용**: 호출 **3회**. 가장 큰 것이 가이드(`gpt-4o` · `max_tokens=800`)다
- **평소**: 🔴 수집조차 되지 않는다(`conftest.py` — skip 이 아니다, `D16`)
"""

import pytest

from ai_worker.domains.lifestyle.guide_generator import generate_guide_payload
from ai_worker.domains.ocr.medicine_matcher import _extract_medicines_with_llm
from app.core.config import config
from app.dtos.lifestyle_guide import _CHALLENGE_COUNT
from app.dtos.query_rewriter import IntentType
from app.services.intent.query_rewriter import rewrite_query

pytestmark = pytest.mark.contract


@pytest.fixture(autouse=True)
def _require_api_key() -> None:
  """🔴 키가 없으면 **실패**한다 — skip 하지 않는다.

  이 디렉터리가 수집됐다는 것은 *«돌리기로 했다»* 는 뜻이고, 그때 키가 없는 것은
  **환경 문제이지 «검증 불필요» 가 아니다**(`pyproject.toml` 의 `db` marker 주석과 같은 결).
  """
  assert config.OPENAI_API_KEY, "OPENAI_API_KEY 가 없다 — 계약 테스트를 돌리기로 했으면 키가 있어야 한다"


class TestOcrExtractionContract:
  """OCR 약품 추출 — `OcrLlmExtraction` (`gpt-4o-mini`)."""

  @pytest.mark.asyncio
  async def test_the_model_returns_items_matching_our_schema(self) -> None:
    """`strict` 스키마가 **수락되고** 모델이 필드를 채운다.

    🔑 실패하면 둘 중 하나다 — ①API 가 우리 스키마를 거부했다(400)
    ②모델이 필드를 못 채웠다. 둘 다 respx 로는 안 보인다.
    """
    items = await _extract_medicines_with_llm("타이레놀정 500mg 1일 3회 5일분 식후 30분")
    assert items, "모델이 빈 목록을 돌려줬다 — 스키마 거부이거나 추출 실패다"
    first = items[0]
    assert "타이레놀" in first["name"]
    # 🔴 키 존재가 계약이다 — 값이 null 인 것은 프롬프트가 허용한다
    for key in ("name", "strength", "type", "dose", "daily_count", "total_days", "instruction"):
      assert key in first, f"스키마 필드 {key} 가 응답에 없다"


class TestGuideContract:
  """생활습관 가이드 — `LlmGuideResponse` (`gpt-4o`)."""

  @pytest.mark.asyncio
  async def test_the_model_returns_exactly_the_required_challenge_count(self) -> None:
    """🔴 **이 구간의 가장 중요한 단언이다.**

    3구간이 `Field(min_length=15)` 를 `field_validator` 로 옮겨 **스키마에서 뺐다**
    (strict 모드가 `minItems` 를 미지원이라 그대로 두면 요청이 거부될 수 있다).
    ⇒ 그 뒤로 개수는 **프롬프트 + 재시도 루프**에만 의존한다.
    **모델이 실제로 지키는지는 이 테스트만 알 수 있다.**

    ⚠️ 재시도 루프가 최대 3회 돌 수 있으므로 호출이 1~3회다(개수를 못 맞추면 늘어난다).
    """
    from openai import AsyncOpenAI

    client = AsyncOpenAI(api_key=config.OPENAI_API_KEY)
    result = await generate_guide_payload(
      [{"medicine_name": "타이레놀정", "dose_per_intake": "1정", "daily_intake_count": 3}],
      {"나이": 30, "성별": "여성", "기저질환": "없음"},
      client,
    )
    assert len(result.recommended_challenges) == _CHALLENGE_COUNT
    # 다섯 카테고리 본문이 비지 않는다 — 스키마가 required 로 보냈다
    for field in ("diet", "sleep", "exercise", "symptom", "interaction"):
      assert getattr(result, field).strip(), f"가이드 본문 {field} 가 비었다"


class TestQueryRewriterContract:
  """1st LLM 의도 분류 — `QueryRewriterOutput` (`gpt-4o-mini`)."""

  @pytest.mark.asyncio
  async def test_the_model_classifies_a_medical_question_as_domain(self) -> None:
    """의학 질문이 `domain_question` 으로 오고 재작성 질의가 채워진다.

    🔑 `parsed` 가 `None` 이면 **거절이나 스키마 미충족**이고, 그러면 운영에서
    ambiguous fallback 이 뜬다 — 그 경로가 상시로 뜨는지 여기서 알 수 있다.
    """
    result = await rewrite_query(
      messages=[{"role": "user", "content": "타이레놀 먹어도 되나요?"}],
      medical_context=None,
    )
    assert result.intent == IntentType.DOMAIN_QUESTION, f"의도가 {result.intent} 로 왔다"
    assert result.rewritten_query, "domain_question 인데 재작성 질의가 비었다"

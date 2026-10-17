"""Lifestyle guide LLM generator — pure prompt build + GPT call + parse.

Pulled out of ``app.services.lifestyle_guide_service`` so the heavy LLM call
runs in ai-worker (not the FastAPI request loop). Imports of ``app.*`` are
type/data only — no FastAPI / HTTPException dependencies live here.

«같은 (처방전 + 건강정보) → 같은 가이드» 는 여기가 아니라 서비스의 **입력 fingerprint
재사용**이 맡는다(같으면 LLM 을 다시 부르지 않는다). 2026-10-16 Gemini 전환 때 seed 와
temperature 0 을 뺐다 — 호환 엔드포인트가 seed 를 거부하고, Gemini 3 은 기본 temperature 를 권한다.
"""

from openai import AsyncOpenAI, OpenAIError
from pydantic import ValidationError

from ai_worker.core.logger import get_logger
from app.core.llm_models import LIFESTYLE_GUIDE_MODEL
from app.core.logger import log_boundary
from app.dtos.lifestyle_guide import LlmGuideResponse
from app.services.lifestyle_guide_prompt_builder import build_guide_prompt

logger = get_logger(__name__)

# 🔑 temperature 는 보내지 않는다 — Gemini 3 공식 권장은 기본값(1.0) 유지다
#    (낮추면 루프·성능 저하, 2026-10-16 확인 · v2.0 재배포 PLAN S1 · 대장 D86).

# LLM 응답이 recommended_challenges len != 15 인 경우 자동 재시도 횟수.
# Pydantic schema 가 min/max=15 강제 -> ValidationError 시 본 retry 가 동작.
_MAX_GENERATE_RETRIES = 3


# ── 라이프스타일 가이드 LLM 호출 ──────────────────────────────────────────
# 흐름: (활성 약물 + 건강정보) -> 프롬프트 빌드
#       -> LLM 호출 (Structured Output) -> 스키마 검증 (위반 시 재호출)
#       -> LlmGuideResponse 반환
async def generate_guide_payload(
  medication_dicts: list[dict],
  health_profile: dict | None,
  client: AsyncOpenAI,
) -> LlmGuideResponse:
  """Build prompt, call GPT, validate JSON.

  Args:
      medication_dicts: Snapshot-safe dict list of active medications.
      health_profile: ``Profile.health_survey`` JSONField 의 dict 값 또는 None.
          나이/성별/알레르기/운동/흡연/키/몸무게/기저질환 키. 누락 키는
          prompt 빌더가 "미입력" 으로 정규화.
      client: Pre-instantiated ``AsyncOpenAI`` client (caller owns lifecycle).

  Returns:
      Parsed + validated ``LlmGuideResponse``.

  Raises:
      ValueError: LLM call or JSON parse failure (caller decides terminal status).
  """
  prompt = build_guide_prompt(medication_dicts, health_profile)

  # ── retry loop — LLM 이 recommended_challenges 15개 룰을 위반하면 (5개만
  #    또는 12개 등) Pydantic schema (min/max=15) 가 ValidationError 발생.
  #    다시 부르면 기본 temperature 라 다른 표본이 나온다. 최대 _MAX_GENERATE_RETRIES 회.
  last_error: ValueError | None = None
  for attempt in range(_MAX_GENERATE_RETRIES):
    # 🔑 재시도 대상은 **스키마 위반(ValidationError)** 만이다.
    #    `OpenAIError` 는 `_call_llm` 이 `ValueError` 로 정규화해 **즉시 전파**한다 —
    #    호출 자체가 실패한 것을 다시 불러도 같다(승격 전 동작 보존).
    try:
      parsed = await _call_llm(prompt, client)
    except ValidationError as exc:
      last_error = ValueError(f"가이드 생성 실패: LLM 응답 파싱 오류 — {exc}")
      logger.warning(
        "[GUIDE] attempt %d/%d 실패 — %s. 재시도.",
        attempt + 1,
        _MAX_GENERATE_RETRIES,
        last_error,
      )
      continue
    if attempt > 0:
      logger.info("[GUIDE] retry 성공 attempt=%d/%d", attempt + 1, _MAX_GENERATE_RETRIES)
    return parsed
  # 모든 재시도 실패 — 마지막 에러를 그대로 raise (caller 가 fail 처리).
  assert last_error is not None
  raise last_error


async def _call_llm(prompt: str, client: AsyncOpenAI) -> LlmGuideResponse:
  """``chat.completions`` **Structured Output** 호출.

  🔑 `json_object` 에서 승격했다(`QA-07` ②, 2026-10-07) — 전자는 *«JSON 이기만 하면
  된다»* 라 필드 이름·타입을 모델이 지킬 의무가 없었다. 이제 스키마를 보내므로 모델이
  지키고, SDK 가 `LlmGuideResponse` 로 검증까지 한다.

  🔴 **챌린지 15개 룰은 스키마로 보내지 않는다** — strict 모드가 `minItems` 를 미지원이라
  DTO 의 `field_validator` 가 맡고, 위반은 호출자의 **재시도 루프**가 받는다.

  Args:
      prompt: 빌드된 프롬프트.
      client: 호출자가 소유하는 AsyncOpenAI 클라이언트.

  Returns:
      검증된 ``LlmGuideResponse``.

  Raises:
      ValueError: OpenAI 호출 실패 — 재시도 대상이 **아니다**.
      ValidationError: 응답이 스키마를 어김 — 호출자가 다시 부른다.
  """
  try:
    async with log_boundary(logger, "openai_lifestyle_guide", model=LIFESTYLE_GUIDE_MODEL):
      response = await client.beta.chat.completions.parse(
        model=LIFESTYLE_GUIDE_MODEL,
        messages=[{"role": "user", "content": prompt}],
        response_format=LlmGuideResponse,
      )
    parsed = response.choices[0].message.parsed
    if parsed is None:
      # 거절(refusal) — 스키마 위반과 같은 취급으로 재시도에 맡긴다.
      msg = "LLM 이 가이드 스키마를 돌려주지 않았다 (거절 가능)"
      raise ValueError(msg)
    return parsed
  except OpenAIError as e:
    logger.exception("[GUIDE] GPT 호출 실패")
    raise ValueError(f"가이드 생성 실패: LLM 호출 오류 — {e}") from e

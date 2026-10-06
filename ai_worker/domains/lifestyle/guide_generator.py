"""Lifestyle guide LLM generator — pure prompt build + GPT call + parse.

Pulled out of ``app.services.lifestyle_guide_service`` so the heavy LLM call
runs in ai-worker (not the FastAPI request loop). Imports of ``app.*`` are
type/data only — no FastAPI / HTTPException dependencies live here.

v3 시점부터 약물 + 사용자 건강정보 조합으로 prompt 와 seed 를 함께 산출 →
같은 (처방전 + 건강정보) 입력엔 거의 동일한 LLM 출력 (deterministic decoding).
"""

import hashlib
import json

from openai import AsyncOpenAI, OpenAIError
from pydantic import ValidationError

from ai_worker.core.logger import get_logger
from app.core.llm_models import LIFESTYLE_GUIDE_MODEL
from app.dtos.lifestyle_guide import LlmGuideResponse
from app.services.lifestyle_guide_prompt_builder import build_guide_prompt

logger = get_logger(__name__)

# 일관성 우선 — 같은 처방전+건강정보 조합엔 거의 동일 출력.
_LLM_TEMPERATURE = 0.0

# LLM 응답이 recommended_challenges len != 15 인 경우 자동 재시도 횟수.
# Pydantic schema 가 min/max=15 강제 -> ValidationError 시 본 retry 가 동작.
_MAX_GENERATE_RETRIES = 3


def _seed_for(medication_dicts: list[dict], health_profile: dict | None) -> int:
  """약물 + 건강정보 조합 기반 OpenAI seed 계산.

  같은 (약물 set + 건강정보) 면 항상 같은 정수 seed. OpenAI 의 ``seed`` 는
  best-effort deterministic decoding — 동일 (model, prompt, temperature,
  seed, system_fingerprint) 에서 거의 동일한 출력. 캐싱이 아니므로 매 호출
  비용은 그대로 발생, dedupe 는 fingerprint (FastAPI 측) 가 담당.

  Args:
      medication_dicts: 활성 약물 dict 목록.
      health_profile: ``Profile.health_survey`` 의 dict 또는 None.

  Returns:
      2^31-1 이하의 양의 정수 (OpenAI 권장 범위).
  """
  names = sorted((m.get("medicine_name") or "") for m in medication_dicts)
  payload = json.dumps(
    {"medications": names, "health": health_profile or {}},
    ensure_ascii=False,
    sort_keys=True,
  )
  digest = hashlib.sha256(payload.encode("utf-8")).digest()
  return int.from_bytes(digest[:4], "big") & 0x7FFFFFFF


# ── 라이프스타일 가이드 LLM 호출 ──────────────────────────────────────────
# 흐름: (활성 약물 + 건강정보) -> seed 계산 -> 프롬프트 빌드
#       -> GPT 호출 (json_object, temperature=0, seed) -> JSON 검증
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
  base_seed = _seed_for(medication_dicts, health_profile)

  # ── retry loop — LLM 이 recommended_challenges 15개 룰을 위반하면 (5개만
  #    또는 12개 등) Pydantic schema (min/max=15) 가 ValidationError 발생.
  #    seed 를 +1 씩 변동해 다른 sample 유도. 최대 _MAX_GENERATE_RETRIES 회.
  last_error: ValueError | None = None
  for attempt in range(_MAX_GENERATE_RETRIES):
    seed = (base_seed + attempt) & 0x7FFFFFFF
    # 🔑 재시도 대상은 **스키마 위반(ValidationError)** 만이다.
    #    `OpenAIError` 는 `_call_llm` 이 `ValueError` 로 정규화해 **즉시 전파**한다 —
    #    호출 자체가 실패한 것을 seed 를 바꿔 다시 불러도 같다(승격 전 동작 보존).
    try:
      parsed = await _call_llm(prompt, client, seed=seed)
    except ValidationError as exc:
      last_error = ValueError(f"가이드 생성 실패: LLM 응답 파싱 오류 — {exc}")
      logger.warning(
        "[GUIDE] attempt %d/%d 실패 — %s. 재시도 (seed=%d).",
        attempt + 1,
        _MAX_GENERATE_RETRIES,
        last_error,
        seed,
      )
      continue
    if attempt > 0:
      logger.info("[GUIDE] retry 성공 attempt=%d/%d", attempt + 1, _MAX_GENERATE_RETRIES)
    return parsed
  # 모든 재시도 실패 — 마지막 에러를 그대로 raise (caller 가 fail 처리).
  assert last_error is not None
  raise last_error


async def _call_llm(prompt: str, client: AsyncOpenAI, *, seed: int) -> LlmGuideResponse:
  """OpenAI ``chat.completions`` **Structured Output** 호출 (deterministic 강화).

  🔑 `json_object` 에서 승격했다(`QA-07` ②, 2026-10-07) — 전자는 *«JSON 이기만 하면
  된다»* 라 필드 이름·타입을 모델이 지킬 의무가 없었다. 이제 스키마를 보내므로 모델이
  지키고, SDK 가 `LlmGuideResponse` 로 검증까지 한다.

  🔴 **챌린지 15개 룰은 스키마로 보내지 않는다** — strict 모드가 `minItems` 를 미지원이라
  DTO 의 `field_validator` 가 맡고, 위반은 호출자의 **재시도 루프**가 받는다.

  Args:
      prompt: 빌드된 프롬프트.
      client: 호출자가 소유하는 AsyncOpenAI 클라이언트.
      seed: 결정성 seed.

  Returns:
      검증된 ``LlmGuideResponse``.

  Raises:
      ValueError: OpenAI 호출 실패 — 재시도 대상이 **아니다**.
      ValidationError: 응답이 스키마를 어김 — 호출자가 seed 를 바꿔 재시도한다.
  """
  try:
    response = await client.beta.chat.completions.parse(
      model=LIFESTYLE_GUIDE_MODEL,
      messages=[{"role": "user", "content": prompt}],
      response_format=LlmGuideResponse,
      temperature=_LLM_TEMPERATURE,
      seed=seed,
    )
    if response.system_fingerprint:
      logger.info(
        "[GUIDE] LLM 호출 seed=%d fingerprint=%s",
        seed,
        response.system_fingerprint,
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

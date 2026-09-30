"""Unit tests for lifestyle guide prompt builder.

Tests verify that the prompt builder:
- Produces a prompt containing medication names and instructions.
- Requests exactly the 5 expected lifestyle categories.
- Handles medications with missing optional fields gracefully.
- Raises ValueError when no medications are provided.
- Returns a JSON schema instruction in the prompt.

All tests are intentionally RED until the module is implemented.
"""

import pytest

from app.services.lifestyle_guide_prompt_builder import build_guide_prompt

FIVE_CATEGORIES = {"diet", "sleep", "exercise", "symptom", "interaction"}


def _make_med(
  name: str,
  category: str | None = None,
  instruction: str | None = None,
  dose: str | None = None,
) -> dict:
  return {
    "medicine_name": name,
    "category": category,
    "intake_instruction": instruction,
    "dose_per_intake": dose,
  }


# ── 정상 케이스 ────────────────────────────────────────────────────────────


def test_build_prompt_returns_string() -> None:
  """build_guide_prompt는 문자열을 반환해야 한다."""
  meds = [_make_med("타이레놀", "해열진통제", "식후 30분", "1정")]
  result = build_guide_prompt(meds)
  assert isinstance(result, str)


def test_build_prompt_includes_medicine_names() -> None:
  """처방된 약품명이 프롬프트에 포함되어야 한다."""
  meds = [
    _make_med("타이레놀", "해열진통제", "식후 30분", "1정"),
    _make_med("암로디핀", "혈압약", "아침 식전", "1정"),
  ]
  result = build_guide_prompt(meds)
  assert "타이레놀" in result
  assert "암로디핀" in result


def test_build_prompt_requests_five_categories() -> None:
  """프롬프트는 5개 카테고리(diet, sleep, exercise, symptom, interaction)를 모두 요구해야 한다."""
  meds = [_make_med("타이레놀")]
  result = build_guide_prompt(meds)
  for category in FIVE_CATEGORIES:
    assert category in result


def test_build_prompt_requests_json_output() -> None:
  """프롬프트는 JSON 형식 응답을 요청해야 한다."""
  meds = [_make_med("타이레놀")]
  result = build_guide_prompt(meds)
  assert "json" in result.lower()


def test_build_prompt_includes_intake_instruction() -> None:
  """복용 지시사항이 프롬프트에 포함되어야 한다."""
  meds = [_make_med("암로디핀", instruction="아침 식전")]
  result = build_guide_prompt(meds)
  assert "아침 식전" in result


def test_build_prompt_handles_none_fields() -> None:
  """optional 필드가 None이어도 오류 없이 프롬프트를 생성해야 한다."""
  meds = [_make_med("타이레놀")]  # category, instruction, dose 모두 None
  result = build_guide_prompt(meds)
  assert isinstance(result, str)
  assert "타이레놀" in result


def test_build_prompt_includes_recommended_challenges_key() -> None:
  """프롬프트는 recommended_challenges 키를 JSON 응답에 포함하도록 요청해야 한다."""
  meds = [_make_med("타이레놀")]
  result = build_guide_prompt(meds)
  assert "recommended_challenges" in result


# ── 예외 케이스 ────────────────────────────────────────────────────────────


def test_build_prompt_raises_on_empty_list() -> None:
  """약물 목록이 비어있으면 ValueError를 발생시켜야 한다."""
  with pytest.raises(ValueError, match="활성 약물"):
    build_guide_prompt([])


def test_build_prompt_med_count_not_names() -> None:
  """로깅 보안: 프롬프트 내부에 약품명 개수(count)가 아닌 이름이 노출되는지 확인.
  프롬프트 자체는 GPT에게 전달되므로 약품명 포함은 허용된다.
  단, 빌더 함수는 약품 수를 반환 값에 포함하지 않는다 (로깅은 호출자 책임).
  """
  meds = [_make_med("타이레놀"), _make_med("암로디핀")]
  result = build_guide_prompt(meds)
  # 반환 타입은 str (tuple/dict 금지)
  assert isinstance(result, str)

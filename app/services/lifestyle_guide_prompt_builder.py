"""Lifestyle guide prompt builder module.

Builds a structured GPT prompt for generating personalized lifestyle guides
based on a user's active medication list AND their health-survey profile
(age / gender / allergies / exercise / smoking / height / weight /
chronic conditions).

v3 시점부터 처방전 그룹의 약물 + 사용자 건강정보를 함께 prompt 에 합산해
fingerprint dedupe 와 LLM 결정성을 함께 강화한다.
"""

from datetime import date, datetime
import logging

from app.core import config

logger = logging.getLogger(__name__)

_SYSTEM_TEMPLATE = """\
당신은 약학 및 건강 생활습관 전문가입니다.
아래에 나열된 처방전 약물 정보와 사용자 건강정보를 함께 고려해, 환자가
일상에서 실천할 수 있는 맞춤형 생활습관 가이드를 작성해 주세요.

## 활성 약물 목록
{medication_lines}

## 사용자 건강정보
{health_lines}

## 일관성 원칙 (매우 중요)
- 같은 (약물 조합 + 건강정보) 입력에는 항상 같은 카테고리 분포와 같은 챌린지 set 을 우선시하세요.
- 약물 이름과 건강정보가 같으면 가이드 텍스트의 톤·스타일·핵심 주의사항도 일관되게 유지하세요.
- 새로운 사실을 매번 다르게 추가하지 말고, 표준화된 권장사항을 그대로 사용하세요.
- 같은 입력에 대해서는 결정론적이고 재현 가능한 응답을 반환하세요.

## 요청 사항
다음 5가지 카테고리 각각에 대해 구체적인 조언을 제공하세요:
- diet (식이요법 / 수분)
- sleep (수면 / 생체 리듬)
- exercise (운동)
- symptom (이 처방전과 사용자 건강상태에서 발생할 수 있는 예상 증상 + 모니터링 포인트.
  사용자가 실제로 겪고 있는 증상을 묻는 게 아니라, 약물·건강정보 조합 상 *주의해야 할*
  증상 예시를 안내. 이상 신호가 나타날 때의 대응 가이드를 함께 포함.)
- interaction (약물 상호작용 / 음식·생활 상호작용 주의사항)

## 응답 형식
반드시 아래 JSON 스키마에 맞게 응답하세요. 다른 텍스트 없이 JSON만 반환하세요.

{{
  "diet": "<식이요법 조언>",
  "sleep": "<수면 조언>",
  "exercise": "<운동 조언>",
  "symptom": "<예상 증상 / 모니터링 안내>",
  "interaction": "<약물 상호작용 주의사항>",
  "recommended_challenges": [
    {{
      "category": "<diet|sleep|exercise|symptom|interaction 중 하나>",
      "title": "<챌린지 제목>",
      "description": "<챌린지 설명>",
      "target_days": <목표 일수 정수>,
      "difficulty": "<쉬움|보통|어려움>"
    }}
  ]
}}

## 챌린지 생성 규칙 (반드시 준수)
- 정확히 15개의 챌린지를 생성하세요. (사용자에게는 5개씩 점진 노출)
- 5개의 카테고리(diet, sleep, exercise, symptom, interaction)에 각 3개씩 배정하세요.
- target_days 분포는 다음 규제를 *세 번 반복* 합니다 (5개 set x 3 = 15개):
  * 각 set 당 1일 1개(쉬움), 7일 1개(쉬움), 14일 2개(보통), 21일 1개(어려움).
  * 즉 전체적으로 1일 3개, 7일 3개, 14일 6개, 21일 3개.
- 한 set 안에서 카테고리 1개씩 배정해 5개 카테고리가 균등하게 채워지도록 하세요.
- 15개 챌린지의 ``title`` 과 행동은 *서로 모두 다르게* 작성하세요. 같은 행동을
  표현만 바꿔 반복하지 말고, 구체적 실천 행동을 다양화 하세요.
- 챌린지 제목은 구체적이고 실천 가능한 행동으로 작성하세요. (최대 30자)
- 1일 챌린지의 title 은 "오늘" 으로 시작해 단일 행동임을 명확히 하세요.

"""


def _format_medication_line(med: dict) -> str:
  """Format a single medication dict into a human-readable line.

  Args:
      med: Medication dict with keys medicine_name, category,
           intake_instruction, dose_per_intake (all optional except name).

  Returns:
      Formatted string describing the medication.
  """
  name = med.get("medicine_name", "")
  parts = [f"- {name}"]

  category = med.get("category")
  if category:
    parts.append(f"[{category}]")

  instruction = med.get("intake_instruction")
  if instruction:
    parts.append(f"복용법: {instruction}")

  dose = med.get("dose_per_intake")
  if dose:
    parts.append(f"용량: {dose}")

  return " / ".join(parts) if len(parts) > 1 else parts[0]


def _calc_age_from_birth(birth: object) -> int | None:
  """birth_date (date / ISO 문자열) 에서 만 나이 추출. 실패 시 None.

  health_survey JSONField 가 ISO 문자열로 들어오는 케이스 + Profile 에서
  직접 date 로 들어오는 케이스 둘 다 수용.
  """
  if not birth:
    return None
  if isinstance(birth, str):
    try:
      birth = date.fromisoformat(birth[:10])
    except ValueError:
      return None
  if not isinstance(birth, date):
    return None
  today = datetime.now(tz=config.TIMEZONE).date()
  age = today.year - birth.year
  if (today.month, today.day) < (birth.month, birth.day):
    age -= 1
  return max(age, 0)


def _format_list_field(value: object) -> str:
  """List / 문자열 / None 을 사람이 읽기 쉬운 한 줄로 정규화."""
  if not value:
    return "없음"
  if isinstance(value, list):
    items = [str(v).strip() for v in value if str(v).strip()]
    return ", ".join(items) if items else "없음"
  return str(value).strip() or "없음"


def _format_bool_field(value: object) -> str:
  """Boolean / 'yes'·'no' 류를 한국어 라벨로."""
  if value is None:
    return "미입력"
  if isinstance(value, bool):
    return "예" if value else "아니오"
  text = str(value).strip().lower()
  if text in {"true", "yes", "y", "1", "예", "있음"}:
    return "예"
  if text in {"false", "no", "n", "0", "아니오", "없음"}:
    return "아니오"
  return text


def _format_health_lines(health: dict | None) -> str:
  """``Profile.health_survey`` dict → prompt 의 건강정보 섹션 라인.

  누락 필드는 "미입력" 으로 표기 — fingerprint 가 같은 입력엔 같은 텍스트가
  렌더되도록 결정성 보장.

  FE ↔ BE 키 이름 호환:
  - 성별: 'MALE'/'FEMALE' (FE 저장) + 'M'/'F' (legacy) 모두 매핑.
  - 흡연: 'is_smoking' (FE) + 'smoking' (legacy) 둘 다 읽음.
  - 음주: 'is_drinking' (FE) — 신규 라인 추가.
  - 기저질환: 'conditions' (FE) + 'chronic_conditions' (legacy) 둘 다 읽음.
  """
  if not health:
    return "- 건강 설문이 등록되어 있지 않습니다."

  age = health.get("age")
  if age is None:
    age = _calc_age_from_birth(health.get("birth_date"))
  age_text = f"{age}세" if age is not None else "미입력"

  gender_raw = str(health.get("gender") or "").upper()
  gender_label = {
    "M": "남",
    "MALE": "남",
    "F": "여",
    "FEMALE": "여",
  }.get(gender_raw, gender_raw or "미입력")

  height = health.get("height_cm") or health.get("height")
  weight = health.get("weight_kg") or health.get("weight")
  height_text = f"{height}cm" if height else "미입력"
  weight_text = f"{weight}kg" if weight else "미입력"

  smoking = health.get("is_smoking")
  if smoking is None:
    smoking = health.get("smoking")
  drinking = health.get("is_drinking")
  if drinking is None:
    drinking = health.get("drinking")

  conditions = health.get("conditions") or health.get("chronic_conditions")

  lines = [
    f"- 나이: {age_text}",
    f"- 성별: {gender_label}",
    f"- 알레르기: {_format_list_field(health.get('allergies'))}",
    f"- 운동 빈도: {health.get('exercise_frequency') or '미입력'}",
    f"- 흡연: {_format_bool_field(smoking)}",
    f"- 음주: {_format_bool_field(drinking)}",
    f"- 키 / 몸무게: {height_text} / {weight_text}",
    f"- 기저질환: {_format_list_field(conditions)}",
  ]
  return "\n".join(lines)


def build_guide_prompt(meds: list[dict], health_profile: dict | None = None) -> str:
  """Build a GPT prompt for generating a personalized lifestyle guide.

  Args:
      meds: List of active medication dicts. Each dict must contain
            'medicine_name' and optionally 'category', 'intake_instruction',
            'dose_per_intake'.
      health_profile: ``Profile.health_survey`` JSONField 의 dict (또는 None).
          나이/성별/알레르기/운동/흡연/키/몸무게/기저질환 키를 사용. 키가
          없으면 "미입력" 으로 fallback — fingerprint 결정성과 동일.

  Returns:
      A formatted prompt string requesting a JSON lifestyle guide.

  Raises:
      ValueError: If meds is empty (활성 약물 없음).
  """
  if not meds:
    raise ValueError("활성 약물 목록이 비어 있습니다. 가이드를 생성하려면 최소 1개의 활성 약물이 필요합니다.")

  medication_lines = "\n".join(_format_medication_line(med) for med in meds)
  health_lines = _format_health_lines(health_profile)
  return _SYSTEM_TEMPLATE.format(
    medication_lines=medication_lines,
    health_lines=health_lines,
  )

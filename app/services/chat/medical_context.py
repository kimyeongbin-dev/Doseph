"""사용자 의학 컨텍스트 빌더 — medication + Profile.health_survey → system prompt 섹션.

PLAN.md (feature/RAG) §2/§3 Step 0:
- medication 테이블에서 사용자 복용약 list 조회
- profiles.health_survey JSONField 에서 conditions/allergies/is_smoking 등 조회
- markdown 한국어 섹션으로 조립 → 2nd LLM 의 system prompt 의 [사용자 의학 컨텍스트]

음성응답 (is_smoking=False, is_drinking=False, conditions=[], allergies=[])
은 IntentClassifier 의 fan-out 시 query 안 만들도록 명시. 본 모듈은 raw fact 만.

흐름: profile_id → DB 조회 (medication + profiles) → markdown 섹션
"""

from typing import Any
from uuid import UUID

from app.models.medication import Medication
from app.models.profiles import Profile

_HEADER = "[사용자 의학 컨텍스트]"


async def build_medical_context(profile_id: UUID) -> str:
    """profile_id 로 사용자 의학 컨텍스트 markdown 섹션 작성.

    Args:
        profile_id: 대상 profile UUID. chat_session.profile_id 에서 추출.

    Returns:
        markdown 형식 한국어 컨텍스트. medication 0 + health_survey None
        이면 빈 문자열 (섹션 자체 생략).
    """
    medications, profile = await _load(profile_id)
    section_lines = _build_lines(medications, profile)
    if not section_lines:
        return ""
    return _HEADER + "\n" + "\n".join(section_lines)


async def _load(profile_id: UUID) -> tuple[list[str], Profile | None]:
    """medication.medicine_name list + profile 단건 조회."""
    profile = await Profile.filter(id=profile_id).first()
    medications = (
        await Medication
        .filter(profile_id=profile_id, is_active=True)
        .order_by("created_at")
        .values_list("medicine_name", flat=True)
    )
    return list(medications), profile


def _build_lines(medications: list[str], profile: Profile | None) -> list[str]:
    """Raw fact 들을 markdown 줄 list 로. 음성응답 (False) 도 그대로 노출."""
    lines: list[str] = []

    if medications:
        lines.append(f"- 복용 중인 약: {', '.join(medications)}")

    survey: dict[str, Any] = (profile.health_survey if profile and profile.health_survey else {}) or {}

    conditions = survey.get("conditions") or []
    if conditions:
        lines.append(f"- 기저질환: {', '.join(conditions)}")

    allergies = survey.get("allergies") or []
    if allergies:
        lines.append(f"- 알레르기: {', '.join(allergies)}")

    is_smoking = survey.get("is_smoking")
    if is_smoking is not None:
        lines.append(f"- 흡연: {'흡연' if is_smoking else '비흡연'}")

    is_drinking = survey.get("is_drinking")
    if is_drinking is not None:
        lines.append(f"- 음주: {'음주' if is_drinking else '비음주'}")

    return lines

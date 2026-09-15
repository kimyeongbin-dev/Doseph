"""Step 0 + 1st LLM 통합 오케스트레이터.

PLAN.md (RAG 재설계 PR-D) - ask_with_tools 의 1st LLM 진입 직선화.

흐름:
  profile_id -> build_medical_context (medication + survey)
            -> map_brands_to_ingredients (사용자 medication brand -> 활성성분)
            -> rewrite_query (gpt-4o-mini Structured Output 단일 호출)
            -> (medical_context, ingredient_mapping_section, QueryRewriterOutput)

호출자 (message_service) 가 medical_context + ingredient_mapping_section 을
2nd LLM 의 system_prompt 에도 prepend (사용자 brand 와 검색 결과 성분명 사이
단절 방지 - 안전장치).
"""

import logging
from uuid import UUID

from app.dtos.query_rewriter import QueryRewriterOutput
from app.models.medication import Medication
from app.services.chat.ingredient_mapper import (
    format_ingredient_mapping_section,
    map_brands_to_ingredients,
)
from app.services.chat.medical_context import build_medical_context
from app.services.intent.query_rewriter import rewrite_query

logger = logging.getLogger(__name__)


async def classify_user_turn(
    profile_id: UUID,
    messages: list[dict[str, str]],
) -> tuple[str, str, QueryRewriterOutput]:
    """profile_id + history -> (medical_context, ingredient_mapping_section, output).

    Args:
        profile_id: chat_session.profile_id 에서 추출.
        messages: 시간순 history + 마지막 user 메시지. system role 제외.

    Returns:
        ``(medical_context, ingredient_mapping_section, QueryRewriterOutput)``:
        - medical_context: ``[사용자 의학 컨텍스트]`` markdown (또는 빈 문자열)
        - ingredient_mapping_section: ``[용어 매핑]`` markdown (또는 빈 문자열)
        - output: QueryRewriterOutput - intent + direct_answer 또는
          rewritten_query + metadata + referent_resolution

        2nd LLM system_prompt 에 두 markdown 섹션 모두 prepend - 안전장치.
    """
    medical_context = await build_medical_context(profile_id)
    if medical_context:
        logger.info(
            "[Chat] medical_context loaded profile=%s len=%dchars",
            str(profile_id)[:8],
            len(medical_context),
        )

    user_medication_names = await _load_medication_names(profile_id)
    mapping = await map_brands_to_ingredients(user_medication_names)
    ingredient_mapping_section = format_ingredient_mapping_section(mapping)
    if ingredient_mapping_section:
        logger.info(
            "[Chat] ingredient_mapping built profile=%s brands=%d mapped=%d",
            str(profile_id)[:8],
            len(mapping),
            sum(1 for v in mapping.values() if v),
        )

    rewriter_input = "\n\n".join(s for s in (medical_context, ingredient_mapping_section) if s)
    output = await rewrite_query(messages, medical_context=rewriter_input or None)
    logger.info(
        "[Chat] intent=%s direct_answer=%s rewritten=%s metadata=%s",
        output.intent.value,
        "yes" if output.direct_answer else "no",
        "yes" if output.rewritten_query else "no",
        output.metadata.model_dump() if output.metadata else None,
    )
    return medical_context, ingredient_mapping_section, output


async def _load_medication_names(profile_id: UUID) -> list[str]:
    """사용자의 활성 medication brand 이름 list."""
    rows = (
        await Medication
        .filter(profile_id=profile_id, is_active=True)
        .order_by("created_at")
        .values_list("medicine_name", flat=True)
    )
    return list(rows)

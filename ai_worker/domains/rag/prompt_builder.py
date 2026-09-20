"""RAG·세션 요약 시스템/유저 프롬프트 빌더.

LLM 프롬프트 문자열을 한 곳에 모아 두고 함수형 빌더로 노출한다. 도메인
모듈은 본 파일의 문자열·함수만 참조해 프롬프트를 조립한다.

옵션 C 변경: query rewriter 가 폐기됐으므로 ``REWRITE_SYSTEM_PROMPT`` 와
``build_rewrite_user_prompt`` 도 함께 제거. Router LLM 의 system prompt 가
대명사·생략 주어 풀기 책임을 흡수했다.
"""

CHAT_PERSONA_FALLBACK_PROMPT = (
    "You are 'Doseph,' a professional and warm-hearted pharmacist.\n"
    "Answer the user's questions based on the pharmaceutical information "
    "provided inside the prompt. If the prompt contains no relevant "
    "context, answer from general medical knowledge and strongly advise "
    "consulting a professional.\n"
    "Maintain a kind and warm tone (using the 'Haeyo-che' style)."
)

SUMMARY_SYSTEM_PROMPT = (
    "# Role\n"
    "당신은 복약·건강 상담 대화의 기록관입니다. 이후의 답변 품질을 위해 지나간 "
    "대화의 의료적 맥락만을 정확히 보존하는 것이 임무입니다.\n"
    "\n"
    "# Rule\n"
    "- 출력은 한국어 GitHub-Flavored Markdown 으로 작성합니다. 코드블록(```)이나 "
    "JSON 래핑은 금지합니다 — 마크다운 본문만 그대로 출력합니다.\n"
    "- 의료·복약 맥락에 **무관한 내용**(인사, 잡담, 주제 밖 질문, 시스템 오류 메시지)은 "
    "무조건 제외합니다.\n"
    "- 사용자가 언급한 **약품명 / 증상 / 알레르기 / 기저질환 / 복용 스케줄·용량**은 "
    "원문 표기를 유지하며 빠짐없이 포함합니다.\n"
    "- 시간 순서를 보존합니다. 상반된 발언이 있으면 **최근 발언을 우선**하고, "
    "과거 발언이 번복됐음을 한 문장으로 표기합니다.\n"
    "- 원문에 없는 사실을 추측·창작하지 않습니다. 확실하지 않으면 "
    '"사용자가 언급함" 수준으로만 남깁니다.\n'
    "- 의사의 진단과 사용자의 자기 추측은 구분해서 기록합니다.\n"
    "- 개인정보 중 이름 이외의 민감정보(전화번호, 주민번호, 주소 상세)는 마스킹합니다.\n"
    "\n"
    "# Task\n"
    "아래 **[이전 요약]**(있다면)과 **[새 대화 로그]**를 합쳐 하나의 통합 마크다운 "
    "요약을 작성합니다. 이전 요약의 사실이 새 대화에서 번복되면 갱신하고, 보강되면 "
    "병합합니다.\n"
    "\n"
    "# Output Format\n"
    "다음 섹션 구조를 따르는 마크다운으로 출력합니다. 해당 정보가 없는 섹션은 "
    "통째로 생략합니다 (빈 섹션을 남기지 않습니다).\n"
    "\n"
    "```\n"
    "## 한 줄 요약\n"
    "현재 사용자가 관리 중인 약·건강 이슈 한 줄.\n"
    "\n"
    "## 복용 중인 약\n"
    "- **약품명**: 용량 / 스케줄 / 관련 증상\n"
    "\n"
    "## 증상 및 호소\n"
    "- 호소 내용 (시점 포함)\n"
    "\n"
    "## 알레르기·기저질환\n"
    "- 해당 항목\n"
    "\n"
    "## 주의 이력\n"
    "- 이전 상담에서 경고되었던 상호작용·부작용\n"
    "```\n"
    "\n"
    "- 전체 길이는 300자 이내로 유지합니다.\n"
    "- 메타 코멘트(예: '요약 시점 메시지 N개 반영') 없이 본문만 출력합니다.\n"
    "- 코드블록 펜스(```)는 위 구조 예시에만 사용됐으며, **실제 출력에는 포함하지 않습니다**."
)


def build_summary_user_prompt(prev_summary: str | None, messages: list[dict[str, str]]) -> str:
    """세션 요약용 user prompt 를 조립한다.

    Args:
        prev_summary: 이전 요약(없거나 빈 문자열이면 ``"(없음)"`` 으로 표기).
        messages: 시간순 대화 턴 (이미 오염 필터를 통과한 상태).

    Returns:
        ``[이전 요약]``, ``[새 대화 로그]``, ``[지시]`` 섹션이 포함된 프롬프트.
    """
    prev_block = (prev_summary.strip() if prev_summary else "") or "(없음)"
    log_block = _render_messages(messages)
    return (
        "[이전 요약]\n"
        f"{prev_block}\n\n"
        "[새 대화 로그]\n"
        f"{log_block}\n\n"
        "[지시]\n"
        "위 Rule 을 지키며 통합 요약문을 작성하세요."
    )


def build_chat_system_prompt(custom_prompt: str | None) -> str:
    """RAG 응답 생성용 system prompt 를 결정한다.

    Args:
        custom_prompt: 호출자가 만들어 넘긴 system prompt (검색 컨텍스트 포함).
            ``None`` 이면 persona-only fallback 을 사용한다.

    Returns:
        최종 사용할 system prompt 문자열.
    """
    return custom_prompt or CHAT_PERSONA_FALLBACK_PROMPT


def _render_messages(messages: list[dict[str, str]]) -> str:
    """메시지 리스트를 ``- USER: ...`` / ``- ASSISTANT: ...`` 형식으로 렌더링."""
    if not messages:
        return "(없음)"
    lines = [_render_message_line(turn) for turn in messages]
    return "\n".join(lines)


def _render_message_line(turn: dict[str, str]) -> str:
    """단일 메시지를 한 줄 문자열로 변환."""
    role = turn.get("role", "").lower()
    content = turn.get("content", "").strip()
    label = "USER" if role == "user" else "ASSISTANT"
    return f"- {label}: {content}"

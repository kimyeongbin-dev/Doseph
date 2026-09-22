"""세션 메시지 요약 — Phase Z.

채팅 세션이 일정 길이를 넘으면 의료적 컨텍스트만 보존하는 마크다운 요약으로
압축한다. 호출자(FastAPI 측 ``SessionCompactService``)가 오염 메시지
(out_of_scope / general_chat) 를 사전에 걸러서 넘긴다고 가정한다.
"""

import logging
import time

from openai import AsyncOpenAI
from openai.types.chat import ChatCompletion as OpenAIChatCompletion

from ai_worker.core.openai_client import get_openai_client
from ai_worker.core.text_helpers import (
    format_token_usage,
    sanitize_error_message,
    strip_code_fence,
    strip_quote_wrapping,
)
from ai_worker.domains.rag.prompt_builder import (
    SUMMARY_SYSTEM_PROMPT,
    build_summary_user_prompt,
)
from app.dtos.rag import SummaryResult, SummaryStatus, TokenUsage

logger = logging.getLogger(__name__)

_MODEL = "gpt-4o"
_TEMPERATURE = 0.2
_MAX_TOKENS = 400
_MIN_MESSAGES = 2


async def summarize_session_messages(
    messages: list[dict[str, str]],
    prev_summary: str | None = None,
) -> SummaryResult:
    """세션 메시지 묶음을 의료 컨텍스트 중심 요약으로 압축한다.

    Args:
        messages: 시간순(오래된 것 먼저) 메시지 리스트. FastAPI 측에서 오염
            필터를 이미 통과한 상태여야 한다.
        prev_summary: 기존 세션 요약. 첫 compact 이거나 이전 요약이 없으면 ``None``.

    Returns:
        ``SummaryResult`` — status (OK/EMPTY/FALLBACK), 요약 본문, 소비된 메시지 수,
        토큰 사용량.
    """
    if len(messages) < _MIN_MESSAGES:
        return _empty_result()

    client = get_openai_client()
    if client is None:
        logger.error("[COMPACT] api_error type=NoClient; fallback to prior summary")
        return _fallback_result(token_usage=None)

    user_prompt = build_summary_user_prompt(prev_summary=prev_summary, messages=messages)
    response, elapsed_ms = await _call_llm(client, user_prompt)
    if response is None:
        return _fallback_result(token_usage=None)

    return _parse_response(response, elapsed_ms, len(messages))


async def _call_llm(client: AsyncOpenAI, user_prompt: str) -> tuple[OpenAIChatCompletion | None, int]:
    """OpenAI API 호출. 실패 시 ``(None, elapsed_ms)``."""
    start = time.perf_counter()
    try:
        response = await client.chat.completions.create(
            model=_MODEL,
            messages=[
                {"role": "system", "content": SUMMARY_SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            temperature=_TEMPERATURE,
            max_tokens=_MAX_TOKENS,
        )
    # 🟠 QA-51: BLE001 은 부채다 — openai 예외로 좁힐 수 있으나 행동 변경이라 미뤘다.
    except Exception as exc:  # noqa: BLE001
        elapsed_ms = int((time.perf_counter() - start) * 1000)
        # 🔒 TRY400 억제는 «정당한 예외» 다 — logger.exception 으로 바꾸면 원본 메시지와
        #    스택이 그대로 나가 sanitize_error_message 의 마스킹을 우회한다(§9.4 위반).
        logger.error(  # noqa: TRY400
            "[COMPACT] api_error type=%s msg=%s after %dms; fallback to prior summary",
            type(exc).__name__,
            sanitize_error_message(str(exc)),
            elapsed_ms,
        )
        return None, elapsed_ms
    return response, int((time.perf_counter() - start) * 1000)


def _parse_response(response: OpenAIChatCompletion, elapsed_ms: int, message_count: int) -> SummaryResult:
    """LLM 응답을 파싱해 SummaryResult 로 변환."""
    raw = response.choices[0].message.content or ""
    cleaned = strip_code_fence(strip_quote_wrapping(raw))
    token_usage = _extract_token_usage(response)

    if not cleaned:
        logger.warning("[COMPACT] empty response after %dms; fallback to prior summary", elapsed_ms)
        return _fallback_result(token_usage=token_usage)

    logger.info(
        "[COMPACT] ok chars=%d msgs=%d tokens=%s took=%dms",
        len(cleaned),
        message_count,
        format_token_usage(token_usage),
        elapsed_ms,
    )
    return SummaryResult(
        status=SummaryStatus.OK,
        summary=cleaned,
        consumed_message_count=message_count,
        token_usage=token_usage,
    )


def _extract_token_usage(response: OpenAIChatCompletion) -> TokenUsage | None:
    """response.usage → TokenUsage DTO."""
    if response.usage is None:
        return None
    return TokenUsage(
        model=_MODEL,
        prompt_tokens=response.usage.prompt_tokens,
        completion_tokens=response.usage.completion_tokens,
        total_tokens=response.usage.total_tokens,
    )


def _empty_result() -> SummaryResult:
    """요약할 가치가 없는 짧은 세션의 결과."""
    return SummaryResult(
        status=SummaryStatus.EMPTY,
        summary="",
        consumed_message_count=0,
        token_usage=None,
    )


def _fallback_result(token_usage: TokenUsage | None) -> SummaryResult:
    """API 실패/빈 응답 시 호출자가 이전 요약을 유지하도록 신호."""
    return SummaryResult(
        status=SummaryStatus.FALLBACK,
        summary="",
        consumed_message_count=0,
        token_usage=token_usage,
    )

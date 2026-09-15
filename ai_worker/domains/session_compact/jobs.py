"""Session-compact RQ jobs — Phase Z + 옵션 D.

옵션 D 추가: ``compact_and_save_session_job(session_id)`` — FastAPI 가
세션 ID 만 넘기면 ai-worker 가 messages 로드 → 오염 필터 → LLM 요약 →
DB UPDATE 까지 한 번의 Tortoise lifecycle 안에서 처리. fire-and-forget
이라 사용자 응답에 영향 없음.

job 함수 안의 lazy import 는 ``ai_worker/domains/rag/jobs.py`` 와 동일한
의도 — worker cold start 단축 (CLAUDE.md §8.5 의 lazy 금지 정책 예외).
"""

import logging

logger = logging.getLogger(__name__)


async def compact_messages_job(
    messages: list[dict[str, str]],
    prev_summary: str | None = None,
) -> dict:
    """[RQ Task] 세션 메시지 묶음을 의료 컨텍스트 요약으로 압축.

    Args:
        messages: 시간순 메시지 리스트 (오염 필터 통과 후).
        prev_summary: 이전 요약. 첫 호출이면 ``None``.

    Returns:
        ``{"status", "summary", "consumed_message_count", "token_usage"}``.
        ``status`` 는 ``"ok" | "empty" | "fallback"``.
    """
    from ai_worker.domains.session_compact.summarizer import summarize_session_messages

    result = await summarize_session_messages(messages=messages, prev_summary=prev_summary)
    return {
        "status": result.status.value,
        "summary": result.summary,
        "consumed_message_count": result.consumed_message_count,
        "token_usage": result.token_usage.model_dump() if result.token_usage is not None else None,
    }


# ── 세션 자동 요약 (옵션 D) ────────────────────────────────────────
# 흐름: Tortoise.init -> messages + prev_summary 로드 -> 오염 필터
#       -> LLM 요약 -> chat_sessions.summary UPDATE -> Tortoise.close
async def compact_and_save_session_job(session_id: str) -> dict:
    """[RQ Task] 세션 ID 만 받아 messages 로드 + 요약 + DB UPDATE 까지.

    옵션 D 의 fire-and-forget 진입점. MessageService 가 한 turn 끝날 때
    enqueue 하면 본 job 이 ai-worker 안에서 모든 처리를 마친다.

    Args:
        session_id: 요약 대상 chat_session UUID 문자열.

    Returns:
        ``{"status", "summary_chars", "consumed_message_count"}`` —
        모니터링/로그용. ``status`` 는 ``"ok" | "empty" | "fallback" | "no_session"``.
    """
    from tortoise import Tortoise

    from ai_worker.domains.session_compact.summarizer import summarize_session_messages
    from app.db.databases import TORTOISE_ORM
    from app.dtos.rag import SummaryResult, SummaryStatus
    from app.models.chat_sessions import ChatSession
    from app.models.messages import ChatMessage
    from app.repositories.chat_session_repository import ChatSessionRepository
    from app.services.chat.session_compact_service import CompactMessage, SessionCompactService

    logger.info("[COMPACT] start session=%s", session_id[:8])
    await Tortoise.init(config=TORTOISE_ORM)
    try:
        session = await ChatSession.filter(id=session_id).first()
        if session is None:
            logger.warning("[COMPACT] session=%s not found, skip", session_id[:8])
            return {"status": "no_session", "summary_chars": 0, "consumed_message_count": 0}

        chat_messages = await ChatMessage.filter(session_id=session_id).order_by("created_at").all()
        compact_messages = [
            CompactMessage(
                role="user" if m.sender_type == "USER" else "assistant",
                content=m.content,
                intent=(m.metadata or {}).get("intent"),
            )
            for m in chat_messages
        ]

        # SessionCompactService 의 filter_noise + summarize 흐름을 그대로 사용하되,
        # generator 자리에는 본 함수 안의 직접 호출자 (lambda) 를 주입한다.
        # 본 job 자체가 ai-worker 안이라 RQ 어댑터를 우회할 수 있음.
        class _DirectGenerator:
            async def summarize_messages(
                self,
                *,
                messages: list[dict[str, str]],
                prev_summary: str | None,
            ) -> SummaryResult:
                return await summarize_session_messages(messages=messages, prev_summary=prev_summary)

        service = SessionCompactService(rag_generator=_DirectGenerator())
        from app.services.chat.session_compact_service import CompactInput

        result = await service.summarize(CompactInput(prev_summary=session.summary, messages=compact_messages))

        if result.status == SummaryStatus.OK:
            updated = await ChatSessionRepository().update_summary(session.id, result.summary)
            logger.info(
                "[COMPACT] session=%s ok chars=%d msgs=%d updated=%d",
                session_id[:8],
                len(result.summary),
                result.consumed_message_count,
                updated,
            )
        else:
            logger.info("[COMPACT] session=%s status=%s skip DB update", session_id[:8], result.status.value)

        return {
            "status": result.status.value,
            "summary_chars": len(result.summary),
            "consumed_message_count": result.consumed_message_count,
        }
    finally:
        await Tortoise.close_connections()

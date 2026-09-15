"""Message service module.

This module provides business logic for chat message management operations
including creation, AI response generation, and ownership verification.
"""

from datetime import UTC, datetime
import json
import logging
import math
from typing import Any
import uuid
from uuid import UUID

from fastapi import HTTPException, status

from app.dtos.query_rewriter import IntentType, LocationMode, LocationQuery, RecallMode, RecallQuery
from app.dtos.tools import AskPending, AskResult, PendingTurn, ToolCall
from app.models.messages import ChatMessage
from app.repositories.chat_session_repository import ChatSessionRepository
from app.repositories.message_repository import MessageRepository
from app.services.chat.intent_orchestrator import classify_user_turn
from app.services.chat.rag_context_assembler import assemble_rag_section
from app.services.rag.openai_embedding import encode_query
from app.services.rag.retrievers.hybrid_metadata import retrieve_with_metadata
from app.services.tools.pending import DEFAULT_TTL_SEC, PendingTurnStore
from app.services.tools.rq_adapters import (
    generate_chat_response_via_rq,
    run_tool_calls_via_rq,
)

logger = logging.getLogger(__name__)


def uuid_token() -> str:
    """짧은 tool_call_id 생성용 — uuid4 hex 앞 8자리."""
    return uuid.uuid4().hex[:8]


# PLAN.md (feature/RAG) §0 결정 — recent history = 6 messages (3 user + 3 assistant).
# 6 turn 마다 chat_sessions.summary 갱신 (옵션 D) 와 정확히 일치 → token 절감.
_HISTORY_LIMIT = 6
_STATUS_OK = "ok"
_STATUS_DENIED = "denied"
_GEOLOCATION_DENIED_MESSAGE = "Permission denied: user rejected geolocation"

# HTTP status codes referenced inside ``resolve_pending_turn`` — the
# ``status`` parameter shadows ``fastapi.status`` in that method, so the
# symbolic aliases are imported up-front to avoid an inline alias.
_HTTP_400_BAD_REQUEST = 400
_HTTP_403_FORBIDDEN = 403
_HTTP_410_GONE = 410

_LOG_PREVIEW_LIMIT = 80

# ── 옵션 D: 세션 요약 자동화 ───────────────────────────────────────
# 매 N turn 마다 background 로 SessionCompactService 호출.
# turn = (user, assistant) 페어 1쌍 ≈ assistant 메시지 1건 기준.
_COMPACT_TRIGGER_EVERY = 6
_COMPACT_TRIGGER_MIN = 6
_COMPACT_JOB_REF = "ai_worker.domains.session_compact.jobs.compact_and_save_session_job"


def _preview(text: str, limit: int = _LOG_PREVIEW_LIMIT) -> str:
    """단일 줄 preview — 로그에서 user/assistant content 를 짧게 보여준다."""
    collapsed = " ".join(text.split())
    return collapsed if len(collapsed) <= limit else collapsed[:limit] + "..."


def _is_valid_coords(lat: float | None, lng: float | None) -> bool:
    """``lat``/``lng`` 가 유한한 숫자값인지 검증.

    None / NaN / Infinity / 비숫자 모두 거부 — 잘못된 좌표가 ai-worker 까지
    내려가 Kakao API 호출에서 ValueError 로 터지는 것을 callback 진입 단계에서
    명확한 400 으로 끊는다.
    """
    if not isinstance(lat, (int, float)) or not isinstance(lng, (int, float)):
        return False
    if isinstance(lat, bool) or isinstance(lng, bool):  # bool 은 int 의 서브클래스
        return False
    return math.isfinite(lat) and math.isfinite(lng)


def _chat_messages_to_history(messages: list[ChatMessage]) -> list[dict[str, str]]:
    """Map stored ChatMessages (newest-first) to chronological LLM history."""
    chronological = list(reversed(messages))
    return [{"role": "user" if m.sender_type == "USER" else "assistant", "content": m.content} for m in chronological]


def _tool_call_to_worker_dict(
    call: ToolCall,
    *,
    geolocation: dict[str, float] | None = None,
    profile_id: str | None = None,
) -> dict[str, Any]:
    """Render a ``ToolCall`` DTO into the pickle-safe dict the worker expects.

    Args:
        call: ToolCall DTO.
        geolocation: 위치 검색 tool 의 사용자 좌표 (top-level 주입).
        profile_id: 회수 조회 tool 의 사용자 식별자 (top-level 주입).
    """
    payload: dict[str, Any] = {
        "tool_call_id": call.tool_call_id,
        "name": call.name,
        "arguments": call.arguments,
    }
    if geolocation is not None:
        payload["geolocation"] = geolocation
    if profile_id is not None:
        payload["profile_id"] = profile_id
    return payload


def _tool_result_message(tool_call_id: str, result: dict[str, Any]) -> dict[str, Any]:
    """Wrap one tool result as the ``role="tool"`` message the LLM expects."""
    return {
        "role": "tool",
        "tool_call_id": tool_call_id,
        "content": json.dumps(result, ensure_ascii=False),
    }


class MessageService:
    """Message business logic service for chat conversation management."""

    def __init__(
        self,
        *,
        pending_store: PendingTurnStore | None = None,
        queue: Any = None,
    ) -> None:
        self.repository = MessageRepository()
        self.session_repository = ChatSessionRepository()
        self._pending_store = pending_store
        self._queue = queue

    def _get_queue(self) -> Any:
        """Lazy-init the RQ ``"ai"`` queue shared with the RAG pipeline.

        Kept as an instance method (not a singleton) so tests can inject
        a stub queue via ``MessageService(queue=...)``.
        """
        if self._queue is None:
            from rq import Queue

            from app.core.config import config
            from app.core.redis_client import make_sync_redis

            redis_conn = make_sync_redis(config.REDIS_URL)
            self._queue = Queue("ai", connection=redis_conn)
        return self._queue

    def _get_pending_store(self) -> PendingTurnStore:
        """Lazy-init the Redis-backed pending-turn store."""
        if self._pending_store is None:
            from app.core.config import config
            from app.core.redis_client import make_async_redis
            from app.services.tools.pending import RedisPendingTurnStore

            self._pending_store = RedisPendingTurnStore(redis=make_async_redis(config.REDIS_URL))
        return self._pending_store

    async def _verify_session_ownership(self, session_id: UUID, account_id: UUID) -> None:
        """Verify chat session ownership.

        Args:
            session_id: Session UUID to verify.
            account_id: Account UUID that should own the session.

        Raises:
            HTTPException: If session not found or access denied.
        """
        session = await self.session_repository.get_by_id(session_id)
        if not session:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Chat session not found.",
            )
        if session.account_id != account_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied to this chat session.",
            )

    async def _verify_message_ownership(self, message: ChatMessage, account_id: UUID) -> None:
        """Verify message ownership through session.

        Args:
            message: Message to verify ownership for.
            account_id: Account UUID that should own the message.

        Raises:
            HTTPException: If access denied to message.
        """
        await message.fetch_related("session")
        if message.session.account_id != account_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied to this message.",
            )

    async def get_message(self, message_id: UUID) -> ChatMessage:
        """Get message by ID.

        Args:
            message_id: Message UUID.

        Returns:
            ChatMessage: Message object.

        Raises:
            HTTPException: If message not found.
        """
        message = await self.repository.get_by_id(message_id)
        if not message:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Message not found.",
            )
        return message

    async def get_message_with_owner_check(self, message_id: UUID, account_id: UUID) -> ChatMessage:
        """Get message with ownership verification.

        Args:
            message_id: Message UUID.
            account_id: Account UUID for ownership check.

        Returns:
            ChatMessage: Message if owned by account.
        """
        message = await self.get_message(message_id)
        await self._verify_message_ownership(message, account_id)
        return message

    async def get_messages_by_session(self, session_id: UUID, limit: int | None = None) -> list[ChatMessage]:
        """Get all messages in a session.

        Args:
            session_id: Session UUID.
            limit: Optional limit on number of messages.

        Returns:
            list[ChatMessage]: List of messages in the session.
        """
        return await self.repository.get_by_session(session_id, limit)

    async def get_messages_by_session_with_owner_check(
        self, session_id: UUID, account_id: UUID, limit: int | None = None
    ) -> list[ChatMessage]:
        """Get all messages in a session with ownership verification.

        Args:
            session_id: Session UUID.
            account_id: Account UUID for ownership check.
            limit: Optional limit on number of messages.

        Returns:
            list[ChatMessage]: List of messages if session is owned by account.
        """
        await self._verify_session_ownership(session_id, account_id)
        return await self.repository.get_by_session(session_id, limit)

    async def get_recent_messages(self, session_id: UUID, limit: int = 10) -> list[ChatMessage]:
        """Get recent messages in a session.

        Args:
            session_id: Session UUID.
            limit: Maximum number of messages to retrieve.

        Returns:
            list[ChatMessage]: List of recent messages.
        """
        return await self.repository.get_recent_by_session(session_id, limit)

    async def create_user_message(self, session_id: UUID, content: str) -> ChatMessage:
        """Create user message.

        Args:
            session_id: Session UUID.
            content: Message content.

        Returns:
            ChatMessage: Created user message.
        """
        return await self.repository.create_user_message(session_id, content)

    async def create_user_message_with_owner_check(
        self, session_id: UUID, account_id: UUID, content: str
    ) -> ChatMessage:
        """Create user message with ownership verification.

        Args:
            session_id: Session UUID.
            account_id: Account UUID for ownership check.
            content: Message content.

        Returns:
            ChatMessage: Created user message if session is owned by account.
        """
        await self._verify_session_ownership(session_id, account_id)
        return await self.repository.create_user_message(session_id, content)

    async def create_assistant_message(self, session_id: UUID, content: str) -> ChatMessage:
        """Create assistant message.

        Args:
            session_id: Session UUID.
            content: Message content.

        Returns:
            ChatMessage: Created assistant message.
        """
        return await self.repository.create_assistant_message(session_id, content)

    # ── 채팅 턴 진입점 (RAG 4단 + 위치 검색 + 회수 조회) ────────────────
    # 흐름: ownership -> history+summary -> Query Rewriter (4o-mini)
    #       -> intent 분기:
    #          (1) direct_answer (greeting/out_of_scope/ambiguous) 즉시 응답
    #          (2) location_search -> _handle_location_search (카카오 + 4o)
    #          (3) recall_check -> _handle_recall_check (식약처 회수 + 4o)
    #          (4) domain_question -> _finalize_rag_turn (RAG 4단 retrieval + 4o)
    async def ask_with_tools(
        self,
        *,
        session_id: UUID,
        account_id: UUID,
        content: str,
    ) -> AskResult:
        """Route one user turn through the chat pipeline.

        Intent 분기 (Query Rewriter 의 단일 호출 결과 기반):
        - **greeting / out_of_scope / ambiguous** — ``direct_answer`` 를 그대로
          응답으로 영속화 후 종료.
        - **domain_question** — ``_finalize_rag_turn`` 으로 hybrid metadata
          retrieval + 2nd LLM (4o) 답변 생성.
        - **location_search** — (예정) 카카오 Local API + 2nd LLM 답변. 핫픽스
          PR 의 Step 3 에서 분기 추가.

        Args:
            session_id: Chat session UUID.
            account_id: Caller account UUID (for ownership check).
            content: User message content.

        Returns:
            ``AskResult`` — direct/RAG 분기에 따라 다름.

        Raises:
            HTTPException: Session ownership violations.
        """
        sid = str(session_id)[:8]
        logger.info("[Chat] session=%s account=%s q=%r", sid, str(account_id)[:8], _preview(content))

        await self._verify_session_ownership(session_id, account_id)

        # Step 0: history (6 msgs) + summary
        recent = await self.repository.get_recent_by_session(session_id, limit=_HISTORY_LIMIT)
        history = _chat_messages_to_history(recent)
        session_summary = await self._fetch_session_summary(session_id)

        # session.profile_id (Step 0 의 medical_context 입력)
        session_obj = await self.session_repository.get_by_id(session_id)
        if session_obj is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Chat session not found.")
        profile_id = session_obj.profile_id

        # ★ user 메시지 영속화 - 실패 시 그 행을 삭제해 rollback
        user_msg = await self.repository.create_user_message(session_id, content)
        try:
            # Step 1: medical_context + ingredient_mapping + Query Rewriter (4o-mini)
            classify_messages = [*history, {"role": "user", "content": content}]
            medical_context, ingredient_mapping_section, rewriter_output = await classify_user_turn(
                profile_id,
                classify_messages,
            )

            # 분기 1: direct_answer (greeting / out_of_scope / ambiguous)
            if rewriter_output.direct_answer:
                logger.info(
                    "[Chat] session=%s intent=%s direct_answer (no RAG)",
                    sid,
                    rewriter_output.intent.value,
                )
                return await self._persist_direct_answer_turn(session_id, user_msg, rewriter_output.direct_answer)

            # 분기 2: location_search (카카오 Local API — keyword 즉시 / gps PendingTurn)
            if rewriter_output.intent == IntentType.LOCATION_SEARCH:
                if rewriter_output.location_query is None:
                    logger.warning(
                        "[Chat] session=%s location_search but location_query 누락 - fallback",
                        sid,
                    )
                    fallback = "검색하실 약국 또는 병원 위치를 더 구체적으로 알려주세요."
                    return await self._persist_direct_answer_turn(session_id, user_msg, fallback)
                return await self._handle_location_search(
                    session_id=session_id,
                    account_id=account_id,
                    user_msg=user_msg,
                    history=history,
                    content=content,
                    location_query=rewriter_output.location_query,
                )

            # 분기 3: recall_check (식약처 회수·판매중지 조회)
            if rewriter_output.intent == IntentType.RECALL_CHECK:
                if rewriter_output.recall_query is None:
                    logger.warning(
                        "[Chat] session=%s recall_check but recall_query 누락 - fallback",
                        sid,
                    )
                    fallback = "어느 약 또는 어느 제조사의 회수 이력을 알려드릴까요?"
                    return await self._persist_direct_answer_turn(session_id, user_msg, fallback)
                return await self._handle_recall_check(
                    session_id=session_id,
                    profile_id=profile_id,
                    user_msg=user_msg,
                    history=history,
                    content=content,
                    recall_query=rewriter_output.recall_query,
                )

            # 분기 4: domain_question (RAG 4단 retrieval + 4o)
            if (
                rewriter_output.intent != IntentType.DOMAIN_QUESTION
                or not rewriter_output.rewritten_query
                or rewriter_output.metadata is None
            ):
                logger.warning(
                    "[Chat] session=%s domain_question but rewritten_query/metadata 누락 - fallback",
                    sid,
                )
                fallback = "어떤 약이나 증상에 대해 알려드릴까요? 좀 더 구체적으로 말씀해주세요."
                return await self._persist_direct_answer_turn(session_id, user_msg, fallback)

            return await self._finalize_rag_turn(
                session_id=session_id,
                user_msg=user_msg,
                history=history,
                session_summary=session_summary,
                content=content,
                rewriter_output=rewriter_output,
                medical_context=medical_context,
                ingredient_mapping_section=ingredient_mapping_section,
            )
        except Exception:
            await self.repository.soft_delete(user_msg)
            logger.exception("[Chat] session=%s server error - rolled back user msg", sid)
            raise

    async def _fetch_session_summary(self, session_id: UUID) -> str | None:
        """chat_sessions.summary 조회 — 옵션 D 의 history prepend 입력."""
        session = await self.session_repository.get_by_id(session_id)
        return session.summary if session is not None else None

    def _maybe_enqueue_compact(self, session_id: UUID, total_messages_after: int) -> None:
        """N turn 마다 compact RQ job 을 fire-and-forget enqueue.

        - assistant 메시지 1건 = 1 turn 기준이라 보고, total_messages_after 가
          (user+assistant) 짝수일 때만 trigger 검토.
        - 최소 _COMPACT_TRIGGER_MIN 이상 + _COMPACT_TRIGGER_EVERY 의 배수일 때 실행.
        """
        if total_messages_after < _COMPACT_TRIGGER_MIN:
            return
        if total_messages_after % _COMPACT_TRIGGER_EVERY != 0:
            return
        try:
            self._get_queue().enqueue(_COMPACT_JOB_REF, str(session_id))
            logger.info(
                "[Chat] session=%s compact enqueued (msgs=%d)",
                str(session_id)[:8],
                total_messages_after,
            )
        except Exception:
            # fire-and-forget — enqueue 실패는 사용자 응답을 막지 않는다.
            logger.exception("[Chat] session=%s compact enqueue failed", str(session_id)[:8])

    async def _persist_direct_answer_turn(
        self,
        session_id: UUID,
        user_msg: ChatMessage,
        text: str,
    ) -> AskResult:
        """IntentClassifier 가 직접 답변한 turn — assistant 만 persist."""
        logger.info(
            "[Chat] session=%s direct_answer reply=%r len=%d",
            str(session_id)[:8],
            _preview(text),
            len(text),
        )
        assistant_msg = await self.repository.create_assistant_message(session_id, text)
        total = await self.repository.count_by_session(session_id)
        self._maybe_enqueue_compact(session_id, total)
        return AskResult(user_message=user_msg, assistant_message=assistant_msg, pending=None)

    async def _finalize_rag_turn(
        self,
        *,
        session_id: UUID,
        user_msg: ChatMessage,
        history: list[dict[str, str]],
        session_summary: str | None,
        content: str,
        rewriter_output: Any,
        medical_context: str = "",
        ingredient_mapping_section: str = "",
    ) -> AskResult:
        """rewritten_query + metadata 로 retrieval -> 2nd LLM 호출.

        흐름:
          1. metadata.target_ingredients + interaction_concerns 산출 (ingredient 필터)
          2. encode_query(rewritten_query) - 1회 임베딩
          3. retrieve_with_metadata - hybrid SQL (메타필터 + cosine top-K)
          4. assemble_rag_section - chunk dict list 평탄화/dedup
          5. _compose_system_prompt - persona + medical_context + 용어 매핑 +
             세션요약 + 명확화 + RAG 검색 결과
          6. generate_chat_response_via_rq - 2nd LLM (4o)
        """
        meta = rewriter_output.metadata
        ingredient_filter = list({*meta.target_ingredients, *meta.interaction_concerns})

        embedding = await encode_query(rewriter_output.rewritten_query)
        chunks = await retrieve_with_metadata(
            query_embedding=embedding,
            target_ingredients=ingredient_filter,
            target_sections=meta.target_sections or None,
            target_conditions=meta.target_conditions or None,
            limit=15,
        )
        chunk_dicts = [c.to_dict() for c in chunks]
        rag_section = assemble_rag_section({"_": {"chunks": chunk_dicts}})

        system_prompt = _compose_system_prompt(
            session_summary=session_summary,
            referent_resolution=rewriter_output.referent_resolution,
            rag_section=rag_section,
            medical_context=medical_context,
            ingredient_mapping_section=ingredient_mapping_section,
        )
        second_messages = [
            *history,
            {"role": "user", "content": content},
        ]
        sid = str(session_id)[:8]
        logger.info(
            "[Chat] session=%s rewritten=%r chunks=%d rag_section=%dchars",
            sid,
            rewriter_output.rewritten_query,
            len(chunks),
            len(rag_section),
        )
        # ── retrieval 품질 디버깅용 chunk 상세 로깅 ───────────────────
        # 흐름: top-N 한 줄 summary (medicine#section@distance) -> 각 chunk content preview
        # INFO 레벨 — 운영에서 retrieval 회귀 / 0건 / 무관한 약 잡힘 등 즉시 확인.
        if chunks:
            summary = " | ".join(
                f"[{i:02d}] {c.medicine_name}#{c.section}@{c.distance:.3f}" for i, c in enumerate(chunks)
            )
            logger.info("[Chat] session=%s chunks_detail=%s", sid, summary)
            for i, c in enumerate(chunks):
                logger.info(
                    "[Chat] session=%s chunk[%02d] med=%r section=%s distance=%.4f preview=%r",
                    sid,
                    i,
                    c.medicine_name,
                    c.section,
                    c.distance,
                    c.content[:120].replace("\n", " "),
                )
        completion = await generate_chat_response_via_rq(
            messages=second_messages,
            system_prompt=system_prompt,
            queue=self._get_queue(),
        )
        answer = completion.get("answer", "")
        logger.info(
            "[Chat] session=%s reply=%r len=%d",
            str(session_id)[:8],
            _preview(answer),
            len(answer),
        )

        assistant_msg = await self.repository.create_assistant_message(session_id, answer)
        total = await self.repository.count_by_session(session_id)
        self._maybe_enqueue_compact(session_id, total)
        return AskResult(user_message=user_msg, assistant_message=assistant_msg, pending=None)

    # ── 위치 검색 분기 (카카오 Local API + 2nd LLM) ─────────────────────
    # 흐름: mode 분기
    #       (keyword) ToolCall 생성 -> run_tool_calls_via_rq 즉시 호출
    #                 -> tool 결과를 messages 에 prepend -> 2nd LLM (4o)
    #                 -> assistant message persist
    #       (gps)     ToolCall 생성 (needs_geolocation=True) -> PendingTurn 저장
    #                 -> AskPending(turn_id, ttl_sec) 반환 -> FE 좌표 콜백 대기
    async def _handle_location_search(
        self,
        *,
        session_id: UUID,
        account_id: UUID,
        user_msg: ChatMessage,
        history: list[dict[str, str]],
        content: str,
        location_query: LocationQuery,
    ) -> AskResult:
        """카카오 Local API 호출 분기 (keyword 즉시 / gps PendingTurn).

        Args:
            session_id: Chat session UUID.
            account_id: Caller account UUID — PendingTurn 소유 검증용.
            user_msg: 이미 영속화된 user 메시지.
            history: 시간순 대화 history (system role 제외).
            content: 사용자 raw 질의.
            location_query: Query Rewriter 가 채운 검색 파라미터.

        Returns:
            ``AskResult`` — keyword 면 ``assistant_message`` 채움, gps 면
            ``pending`` 채움.
        """
        sid = str(session_id)[:8]

        if location_query.mode == LocationMode.KEYWORD:
            return await self._run_keyword_location_turn(
                session_id=session_id,
                user_msg=user_msg,
                history=history,
                content=content,
                location_query=location_query,
            )

        # mode == LocationMode.GPS — PendingTurn 으로 좌표 콜백 대기
        if location_query.category is None:
            logger.warning("[Chat] session=%s gps location_search but category 누락 - fallback", sid)
            fallback = "약국 또는 병원 중 어느 쪽을 찾아드릴까요?"
            return await self._persist_direct_answer_turn(session_id, user_msg, fallback)

        return await self._enqueue_gps_pending_turn(
            session_id=session_id,
            account_id=account_id,
            user_msg=user_msg,
            history=history,
            content=content,
            location_query=location_query,
        )

    async def _run_keyword_location_turn(
        self,
        *,
        session_id: UUID,
        user_msg: ChatMessage,
        history: list[dict[str, str]],
        content: str,
        location_query: LocationQuery,
    ) -> AskResult:
        """mode=keyword — 즉시 카카오 호출 + 2nd LLM 응답."""
        sid = str(session_id)[:8]
        if not location_query.query or not location_query.query.strip():
            logger.warning("[Chat] session=%s keyword location_search but query 누락 - fallback", sid)
            fallback = "어느 지역의 약국 또는 병원을 찾아드릴까요?"
            return await self._persist_direct_answer_turn(session_id, user_msg, fallback)

        tool_call = ToolCall(
            tool_call_id=f"loc_kw_{uuid_token()}",
            name="search_hospitals_by_keyword",
            arguments={"query": location_query.query.strip()},
            needs_geolocation=False,
        )
        worker_calls = [_tool_call_to_worker_dict(tool_call)]
        logger.info("[Chat] session=%s location_search keyword=%r", sid, location_query.query)
        results = await run_tool_calls_via_rq(calls=worker_calls, queue=self._get_queue())

        assistant_with_tool = {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": tool_call.tool_call_id,
                    "type": "function",
                    "function": {
                        "name": tool_call.name,
                        "arguments": json.dumps(tool_call.arguments, ensure_ascii=False),
                    },
                }
            ],
        }
        tool_message = _tool_result_message(
            tool_call.tool_call_id,
            results.get(tool_call.tool_call_id, {"error": "no result"}),
        )
        second_messages = [
            *history,
            {"role": "user", "content": content},
            assistant_with_tool,
            tool_message,
        ]
        completion = await generate_chat_response_via_rq(
            messages=second_messages,
            queue=self._get_queue(),
        )
        answer = completion.get("answer", "")
        logger.info("[Chat] session=%s location keyword reply=%r len=%d", sid, _preview(answer), len(answer))

        assistant_msg = await self.repository.create_assistant_message(session_id, answer)
        total = await self.repository.count_by_session(session_id)
        self._maybe_enqueue_compact(session_id, total)
        return AskResult(user_message=user_msg, assistant_message=assistant_msg, pending=None)

    async def _enqueue_gps_pending_turn(
        self,
        *,
        session_id: UUID,
        account_id: UUID,
        user_msg: ChatMessage,
        history: list[dict[str, str]],
        content: str,
        location_query: LocationQuery,
    ) -> AskResult:
        """mode=gps — PendingTurn 저장 후 AskPending 핸드오프 반환."""
        sid = str(session_id)[:8]
        category_value = location_query.category.value if location_query.category else "약국"
        arguments: dict[str, Any] = {
            "category": category_value,
            "radius_m": location_query.radius_m,
        }
        tool_call = ToolCall(
            tool_call_id=f"loc_gps_{uuid_token()}",
            name="search_hospitals_by_location",
            arguments=arguments,
            needs_geolocation=True,
        )

        assistant_with_tool = {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": tool_call.tool_call_id,
                    "type": "function",
                    "function": {
                        "name": tool_call.name,
                        "arguments": json.dumps(tool_call.arguments, ensure_ascii=False),
                    },
                }
            ],
        }
        messages_snapshot: list[dict[str, Any]] = [
            *history,
            {"role": "user", "content": content},
            assistant_with_tool,
        ]

        pending = PendingTurn(
            turn_id="",
            session_id=str(session_id),
            account_id=str(account_id),
            messages_snapshot=messages_snapshot,
            tool_calls=[tool_call],
            eager_results={},
            created_at=datetime.now(UTC),
        )
        store = self._get_pending_store()
        turn_id = await store.create(pending)
        logger.info(
            "[Chat] session=%s location_search gps category=%s radius=%dm pending=%s",
            sid,
            category_value,
            location_query.radius_m,
            turn_id,
        )
        return AskResult(
            user_message=user_msg,
            assistant_message=None,
            pending=AskPending(turn_id=turn_id, ttl_sec=DEFAULT_TTL_SEC),
        )

    # ── 회수 조회 분기 (식약처 회수 매칭 + 2nd LLM) ─────────────────────
    # 흐름: mode 분기
    #       (user)         ToolCall(check_user_medications_recall) +
    #                      profile_id top-level 주입 -> run_tool_calls_via_rq
    #                      -> 결과를 messages 에 prepend -> 2nd LLM (4o)
    #       (manufacturer) ToolCall(check_manufacturer_recalls) + profile_id +
    #                      arguments.manufacturer (선택) -> 동일 흐름
    async def _handle_recall_check(
        self,
        *,
        session_id: UUID,
        profile_id: UUID,
        user_msg: ChatMessage,
        history: list[dict[str, str]],
        content: str,
        recall_query: RecallQuery,
    ) -> AskResult:
        """식약처 회수·판매중지 매칭 분기 (mode=user / mode=manufacturer)."""
        sid = str(session_id)[:8]

        if recall_query.mode == RecallMode.USER:
            tool_call = ToolCall(
                tool_call_id=f"recall_user_{uuid_token()}",
                name="check_user_medications_recall",
                arguments={},
                needs_geolocation=False,
            )
        else:  # MANUFACTURER
            arguments: dict[str, Any] = {}
            if recall_query.manufacturer:
                arguments["manufacturer"] = recall_query.manufacturer
            tool_call = ToolCall(
                tool_call_id=f"recall_mfr_{uuid_token()}",
                name="check_manufacturer_recalls",
                arguments=arguments,
                needs_geolocation=False,
            )

        worker_calls = [_tool_call_to_worker_dict(tool_call, profile_id=str(profile_id))]
        logger.info(
            "[Chat] session=%s recall_check mode=%s manufacturer=%r",
            sid,
            recall_query.mode.value,
            recall_query.manufacturer,
        )
        results = await run_tool_calls_via_rq(calls=worker_calls, queue=self._get_queue())

        assistant_with_tool = {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": tool_call.tool_call_id,
                    "type": "function",
                    "function": {
                        "name": tool_call.name,
                        "arguments": json.dumps(tool_call.arguments, ensure_ascii=False),
                    },
                }
            ],
        }
        tool_message = _tool_result_message(
            tool_call.tool_call_id,
            results.get(tool_call.tool_call_id, {"error": "no result"}),
        )
        second_messages = [
            *history,
            {"role": "user", "content": content},
            assistant_with_tool,
            tool_message,
        ]
        completion = await generate_chat_response_via_rq(
            messages=second_messages,
            queue=self._get_queue(),
        )
        answer = completion.get("answer", "")
        logger.info("[Chat] session=%s recall reply=%r len=%d", sid, _preview(answer), len(answer))

        assistant_msg = await self.repository.create_assistant_message(session_id, answer)
        total = await self.repository.count_by_session(session_id)
        self._maybe_enqueue_compact(session_id, total)
        return AskResult(user_message=user_msg, assistant_message=assistant_msg, pending=None)

    # ── pending GPS 턴 마무리 (오케스트레이션) ───────────────────────────
    # 흐름: 입력 검증 -> claim+ownership -> geo 결과 수집
    #       -> 2nd LLM 호출 -> assistant message persist
    async def resolve_pending_turn(
        self,
        *,
        turn_id: str,
        account_id: UUID | str,
        status: str,
        lat: float | None,
        lng: float | None,
    ) -> AskResult:
        """Complete a turn that was waiting on a GPS callback.

        Args:
            turn_id: Id returned to the client as ``AskPending.turn_id``.
            account_id: Caller account id (string compare against pending owner).
            status: ``"ok"`` (user allowed GPS) or ``"denied"``.
            lat: Latitude (WGS84) when ``status="ok"``.
            lng: Longitude (WGS84) when ``status="ok"``.

        Returns:
            ``AskResult`` with only ``assistant_message`` set — user turn 은
            pending 생성 시점에 이미 저장됨.

        Raises:
            HTTPException: 400 / 403 / 410 (helper 들이 던짐).
        """
        self._validate_resolve_payload(status, lat, lng)
        pending = await self._claim_and_authorize(turn_id, account_id)
        results = await self._collect_tool_results(pending, status=status, lat=lat, lng=lng)

        completion = await generate_chat_response_via_rq(
            messages=[
                *pending.messages_snapshot,
                *(_tool_result_message(cid, res) for cid, res in results.items()),
            ],
            system_prompt=None,
            queue=self._get_queue(),
        )
        answer = completion.get("answer", "")

        session_uuid = UUID(pending.session_id)
        assistant_msg = await self.repository.create_assistant_message(session_uuid, answer)
        total = await self.repository.count_by_session(session_uuid)
        self._maybe_enqueue_compact(session_uuid, total)
        logger.info(
            "[Chat] resolved turn=%s session=%s status=%s tools=%d reply=%r len=%d",
            turn_id,
            str(session_uuid)[:8],
            status,
            len(results),
            _preview(answer),
            len(answer),
        )
        return AskResult(user_message=None, assistant_message=assistant_msg, pending=None)

    @staticmethod
    def _validate_resolve_payload(status: str, lat: float | None, lng: float | None) -> None:
        """status='ok' 인데 lat/lng 가 유효하지 않으면 즉시 400 — claim 낭비 방지."""
        if status == _STATUS_OK and not _is_valid_coords(lat, lng):
            raise HTTPException(
                status_code=_HTTP_400_BAD_REQUEST,
                detail="lat and lng must be finite numbers when status='ok'",
            )

    async def _claim_and_authorize(self, turn_id: str, account_id: UUID | str) -> PendingTurn:
        """Pending 을 atomic 하게 claim + ownership 검증 — 각각 410/403."""
        store = self._get_pending_store()
        pending = await store.claim(turn_id)
        if pending is None:
            raise HTTPException(
                status_code=_HTTP_410_GONE,
                detail="Pending turn not found or expired.",
            )
        if pending.account_id != str(account_id):
            raise HTTPException(
                status_code=_HTTP_403_FORBIDDEN,
                detail="Access denied to this pending turn.",
            )
        return pending

    async def _collect_tool_results(
        self,
        pending: PendingTurn,
        *,
        status: str,
        lat: float | None,
        lng: float | None,
    ) -> dict[str, Any]:
        """Eager 결과 위에 geo 결과 (or denied) 를 합쳐 최종 results dict 를 만든다."""
        results = dict(pending.eager_results)
        remaining_geo_calls = [
            tc for tc in pending.tool_calls if tc.needs_geolocation and tc.tool_call_id not in results
        ]
        if status == _STATUS_OK:
            if remaining_geo_calls:
                geolocation = {"lat": lat, "lng": lng}
                call_payload = [_tool_call_to_worker_dict(tc, geolocation=geolocation) for tc in remaining_geo_calls]
                geo_results = await run_tool_calls_via_rq(calls=call_payload, queue=self._get_queue())
                results.update(geo_results)
        else:
            for tc in remaining_geo_calls:
                results[tc.tool_call_id] = {"error": _GEOLOCATION_DENIED_MESSAGE}
        return results

    async def delete_message(self, message_id: UUID) -> None:
        """Delete message (행을 물리 삭제한다).

        Args:
            message_id: Message UUID to delete.
        """
        message = await self.get_message(message_id)
        await self.repository.soft_delete(message)

    async def delete_message_with_owner_check(self, message_id: UUID, account_id: UUID) -> None:
        """Delete message with ownership verification (행을 물리 삭제한다).

        Args:
            message_id: Message UUID to delete.
            account_id: Account UUID for ownership check.
        """
        message = await self.get_message_with_owner_check(message_id, account_id)
        await self.repository.soft_delete(message)


# ── 2nd LLM system prompt 조립 ──────────────────────────────────────
# PLAN.md (RAG 재설계 PR-D) - 사용자 brand <-> 검색결과 성분명 단절 방지를
# 위한 안전장치 섹션 순서:
#   1. persona + output rule (성분 grounded 강화)
#   2. [사용자 의학 컨텍스트] (사용자 복용약/기저질환/알레르기 brand 표기)
#   3. [용어 매핑] (brand -> 활성성분 변환표)
#   4. [세션 요약] (옵션)
#   5. [명확화] (referent_resolution 있을 때)
#   6. [검색된 약품 정보] (성분 단위 RAG 결과)
_PERSONA_AND_RULES = (
    "당신은 'Dayak' 약사 챗봇입니다. 약 복용에 대해 걱정 많은 사용자에게\n"
    "동네 단골 약사처럼 따뜻하고 안심되는 어조 (해요체) 로 응답합니다.\n"
    "\n"
    "## 말투와 톤 (사용자 친화 + 전문 용어 병기)\n"
    "- 첫 문장은 **사용자의 걱정에 공감하거나 안심시키는 한마디** 로 시작.\n"
    "  예) '걱정되시는 마음 충분히 이해돼요.', '같이 한 번 살펴볼게요.',\n"
    "      '결론부터 말씀드리면 …'.\n"
    "- **두 번째 문장 (또는 첫 문장 안)** 에 [사용자 의학 컨텍스트] 의\n"
    "  기저질환 + 복용약을 **명시적으로 인지하고 있음을 표시**. 사용자가\n"
    "  '내 정보를 챗봇이 알고 답하고 있다' 를 즉시 느끼게 하는 역할.\n"
    "  예) '간질환이 있으시고 쿠파린정을 복용 중이신 점 확인했어요.',\n"
    "      '고혈압 + 와파린 복용 중이신 컨텍스트로 답변 드릴게요.',\n"
    "      '아스피린 알레르기 + 천식 정보까지 확인했어요.'\n"
    "  -> medical_context 가 비어있거나 관련 정보가 없으면 생략.\n"
    "  -> 단순 인사 (greeting) 답변엔 표시하지 않아도 됨.\n"
    "- 의학 전문 용어는 **반드시 쉬운 일상 비유로 먼저 풀어 쓰고, 괄호 ()\n"
    "  안에 한국어+영문 전문 용어를 함께** 적습니다 (의무 — 누락 시 결격).\n"
    "  사용자가 그 키워드로 추가 검색 / 약사·의사에게 다시 물어볼 수 있도록.\n"
    "  예) '몸에서 약을 분해하는 효소의 일을 늦춰요 (**CYP3A4 효소 억제, "
    "CYP3A4 inhibition**)',\n"
    "      '간에 부담이 갈 수 있어요 (**간독성, hepatotoxicity**)',\n"
    "      '피가 더 묽어질 수 있어요 (**INR 상승, prothrombin time prolongation**)',\n"
    "      '약효가 너무 강해질 수 있어요 (**혈중 농도 상승, elevated plasma level**)'.\n"
    "  -> 비유 → 괄호 (한국어, 영문) 순서, 굵게 강조.\n"
    "  -> 사용자가 직접 입력한 약 이름·증상 같은 일상어에는 괄호 병기 불필요.\n"
    "  -> '출혈 위험', '간 손상' 같은 일반 의학어가 답변에 등장하면 그 직후에\n"
    "     반드시 괄호 병기 (한국어+영문).\n"
    "- 단정적 명령 ('하세요', '금지') 보다 **부드러운 권유** 사용.\n"
    "  예) '~ 하시는 게 좋아요', '가능하면 ~ 권해드려요', '~ 은 피하시면 좋아요'.\n"
    "- 답변 끝은 사용자가 다음에 할 행동을 가볍게 안내.\n"
    "  예) '추가로 궁금한 점 있으시면 언제든 물어보세요', '복약 중 불편하면\n"
    "      바로 약사·의사에게 말씀해주세요'.\n"
    "- 차갑거나 사무적인 표현 회피 — '본 답변은 …', '귀하의 ~' 같은 딱딱한\n"
    "  공문체는 쓰지 않습니다.\n"
    "\n"
    "## 출력 형식 (한국어 GFM Markdown 적극 활용)\n"
    "- 답변 길이: 평균 400~800자 권장. 검색 결과의 핵심 정보를 충분히 활용.\n"
    "  너무 짧은 답변 (200자 미만) 회피 — 사용자가 구체적 정보 받도록.\n"
    "- 답변에 적합한 곳에 다음 Markdown 적극 사용:\n"
    "  * `## 소제목` — 답변에 2개 이상의 토픽 (예: 상호작용 / 주의사항) 이\n"
    "    있을 때 섹션 구분.\n"
    "  * `**굵게**` — 약품명, 위험 키워드 (출혈 위험, 간 손상 등), 핵심 수치 (1일 4g).\n"
    "  * `- 글머리 기호 리스트` — 항목이 2개 이상일 때 (주의사항, 부작용 list).\n"
    "  * `1. 번호 리스트` — 단계/순서가 있을 때 (복용 순서 등).\n"
    "  * `> 인용` — 결론/요약 강조.\n"
    "- 코드 블록 (```) 만 금지. 인라인 `code` 도 사용 자제.\n"
    "\n"
    "## 출처 표기 (사용자 친화 footer)\n"
    "- 답변 본문에 `[약: 약품명] [drug_interaction]` 같은 메타/디버그식 표기\n"
    "  **절대 금지**.\n"
    "- 검색 결과 chunk 의 content 헤더 (`[약: …] [성분: …] [drug_interaction]`)\n"
    "  는 시스템 메타데이터 — 답변에 그대로 흉내내거나 인용하지 말 것.\n"
    "- 출처는 답변 마지막 한 줄 footer 로 자연어:\n"
    "  `> 식약처 의약품 안전성 정보 기준 (타이레놀, 쿠파린정 등).`\n"
    "- 본문 내 인용은 자연 문장:\n"
    "  '와파린의 약물 정보에 따르면 …', '아세트아미노펜의 약물 정보를 보면 …'.\n"
    "\n"
    "## 의료 안전 룰 (검색 결과 적극 반영 의무)\n"
    "- 의학적 진단/처방 변경 제안 금지. 의사·약사 상담 권고는 부드럽게.\n"
    "- 검색 결과에 약물 상호작용·부작용·금기 정보가 있으면 **반드시 본문에\n"
    "  명시**. 일반화 회피.\n"
    "\n"
    "### ⛔ 절대 금지 표현 (사용자 안전성 직접 손상)\n"
    "다음 표현은 **어떤 상황에서도 사용 금지**. 검색 결과의 위험 정보를\n"
    "희석시키거나 사용자가 위험을 과소평가하게 만들 수 있음:\n"
    "  - '일반적으로 안전한 …' / '비교적 안전' / '대체로 안전'\n"
    "  - '비교적 안전한 진통제' / '비교적 안전하다고 알려져 있어요'\n"
    "    (검색 결과 데이터를 우회해 약을 안전하다고 판정하는 어떤 변형도 금지 —\n"
    "     '비교적/대체로/일반적으로/대부분 + 안전' 어떤 조합도 사용 금지)\n"
    "  - '대부분의 경우 괜찮다' / '큰 문제 없다고 알려져 있다'\n"
    "  - '일반적으로 사용되는 진통제' / '흔히 쓰이는 약'\n"
    "    (사용자가 묻는 맥락엔 그 사람의 복용약·기저질환이 있어 '일반적'\n"
    "     이 적용되지 않음 — 이 한 단어로 컨텍스트 무시 위험)\n"
    "  - '~에 대해 걱정할 필요 없다' / '~ 정도는 무방하다'\n"
    "특히 **사용자가 복용약·기저질환을 갖고 있는 상황** 에서는 위 표현이\n"
    "구체 위험을 가릴 수 있어 절대 금지.\n"
    "\n"
    "### 🚨 임신·수유·소아 컨텍스트 강제 가드\n"
    "target_conditions 또는 medical_context 에 'pregnancy', 'breastfeeding',\n"
    "'pediatric' 이 포함되거나 사용자 질문에 '임산부', '임신', '수유', '아기',\n"
    "'어린이', '유아' 가 등장하면 **다음을 절대 준수**:\n"
    "  - '안전' 단어 자체 사용 금지 (어떤 수식어와도 결합 불가).\n"
    "    BAD: '비교적 안전' / '안전한 약' / '안전하게 복용' / '안전성 있음'\n"
    "    OK:  '복용 전 의사 상담이 필요한 약', '주의 깊은 처방이 필요'\n"
    "  - '안전성에 대해 알려져 있어요' / '여러 연구에 따르면 안전' 류의 간접\n"
    "    안전 평가도 금지 — 위험 판단은 사용자·의사 결정 영역.\n"
    "  - 첫 단락은 반드시 '복용 전 산부인과·소아과·주치의 상담 필요' 로 시작.\n"
    "  - 검색 결과의 '임부' / '임산부' / 'pregnancy category' / '수유부' 표기를\n"
    "    그대로 인용. 일반화 금지.\n"
    "\n"
    "### 응답 자체 검증 (출력 직전 필수 체크)\n"
    "응답 본문을 출력하기 전에 다음 패턴이 본문에 있는지 자체 점검하고,\n"
    "있으면 **반드시 재작성**:\n"
    "  1. '비교적 안전' / '대체로 안전' / '일반적으로 안전' / '대부분 안전'\n"
    "  2. 임신·수유·소아 컨텍스트 + '안전' 단어 결합\n"
    "  3. '걱정할 필요 없' / '문제 없' / '괜찮다고 알려' 류\n"
    "위 패턴 발견 시 해당 문장을 '주의가 필요해요' / '신중한 복용이 권장돼요' /\n"
    "'의사 상담이 필요해요' 류로 교체.\n"
    "\n"
    "### ✅ 권장 표현 (명료 + 부드러움)\n"
    "  - '~ 위험이 늘 수 있어요 (**전문 용어**)'\n"
    "  - '~ 가능성이 보고됐어요'\n"
    "  - '신중히 복용해야 해요'\n"
    "  - '간 기능에 부담을 줄 수 있어요 (**간독성, hepatotoxicity**)'\n"
    "  - '함께 복용 시 ~가 강해질 수 있어요'\n"
    "\n"
    "### 우선순위·톤\n"
    "- 위험은 **명확하게** 알리되, 부드러운 톤 유지 (공포감 X, 명료함 ✓).\n"
    "- 사용자의 기저질환 / 복용약과 결과 chunk 가 직접 매칭되는 위험은 우선\n"
    "  순위로 본문 상단부에 배치. 예) 사용자가 와파린 복용 중인데 검색 결과에\n"
    "  '아세트아미노펜+와파린 INR 상승' 정보가 있으면 그 부분이 답변 핵심.\n"
    "- 답변 첫 단락에 '주성분 X 는 안전한 약' 같은 식의 약 자체에 대한\n"
    "  안전 평가 문장으로 시작하지 말 것 — 사용자 컨텍스트 (기저질환, 복용약)\n"
    "  을 고려한 구체 위험·주의사항부터 시작.\n"
    "\n"
    "## brand <-> 성분 매핑 (단절 방지)\n"
    "- 사용자가 사용한 약 이름은 brand, 검색 결과는 성분명 단위입니다.\n"
    "- 답변 시 사용자의 brand 이름을 그대로 쓰면서, [용어 매핑] 의 brand -> 성분\n"
    "  변환표를 활용해 검색 결과의 성분 정보를 정확히 반영하세요.\n"
    "- 일반론적인 '의사 상담' 답변 대신, 사용자 복용약/기저질환과의 구체적\n"
    "  상호작용을 검색 결과 기반으로 제시하세요."
)


def _compose_system_prompt(
    *,
    session_summary: str | None,
    referent_resolution: dict[str, str] | None,
    rag_section: str,
    medical_context: str = "",
    ingredient_mapping_section: str = "",
) -> str:
    """2nd LLM (4o) 의 system prompt 를 안전장치 포함 섹션 순서로 조립."""
    parts: list[str] = [_PERSONA_AND_RULES]

    if medical_context:
        parts.append(medical_context)  # [사용자 의학 컨텍스트] 헤더 포함

    if ingredient_mapping_section:
        parts.append(ingredient_mapping_section)  # [용어 매핑] 헤더 포함

    if session_summary:
        parts.append(f"[세션 요약]\n{session_summary}")

    if referent_resolution:
        clarif_lines = "\n".join(f"- '{k}' → '{v}'" for k, v in referent_resolution.items())
        parts.append(f"[명확화]\n{clarif_lines}")

    if rag_section:
        parts.append(rag_section)  # [검색된 약품 정보] 헤더 포함

    return "\n\n".join(parts)

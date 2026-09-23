"""Session compaction service (Phase Z-A: summary-engine only).

Responsibilities (this phase):
1. Take a chronological message list plus each user turn's classified intent
   (read from ``messages.metadata`` by the caller).
2. Drop USER/ASSISTANT turn pairs classified as OUT_OF_SCOPE / GENERAL_CHAT
   so the summarising LLM never sees non-medical noise (사라진 계획 «세션 컴팩트 Z-5»).
   🔑 규칙의 정본은 이 모듈과 `app/tests/` 다 — 계획은 사라졌다.
3. Delegate to the injected RAG generator (worker LLM) to produce the
   merged summary and surface the structured SummaryResult.

이 모듈의 책임은 **요약 생성까지**다. 나머지는 아래가 맡는다(2026-09-21 실측):
- ``chat_sessions.summary`` / ``summary_updated_at`` 읽고 쓰기
  -> ``MessageService._fetch_session_summary`` + ``compact_and_save_session_job``
- 트리거 -> ``MessageService._maybe_enqueue_compact``
  (``_COMPACT_TRIGGER_MIN=6`` 이상 + ``_COMPACT_TRIGGER_EVERY=6`` 배수일 때 RQ enqueue)

.. warning::
   여기엔 원래 *"Out of scope (deferred to Phase Z-B): 컬럼 읽고쓰기 / 스케줄링 /
   MessageService 트리거"* 라고 적혀 있었다. **그 셋은 그 뒤 전부 구현됐는데 이 글이
   따라오지 않았다.** 2026-09-21 정독에서 이 문장을 *"아직 없다"* 로 읽고 로드맵에
   **거짓 미구현 항목을 등재**했다(``ROADMAP`` C-8, 같은 날 철회 · 대장 **D55**).

   > **단계의 범위 선언은 그 단계의 사실이지 오늘의 사실이 아니다.**
   > 단계가 끝나면 그 문장은 남겨 두지 말고 **지금의 분담**으로 다시 쓴다.
"""

from dataclasses import dataclass
import logging

from app.dtos.rag import SummaryResult, SummaryStatus

logger = logging.getLogger(__name__)

# Intents whose USER turn (and its paired ASSISTANT turn) pollute the
# medical-context summary and must be removed before the LLM sees them.
# 옵션 C 에서 IntentType enum 이 폐기된 이후, 본 sentinel 들은 두 갈래로 채워질 수
# 있다: (a) 옵션 C 이전에 저장된 messages.metadata.intent (legacy 기록 호환),
# (b) 추후 기능에서 Router 결과를 인지해 다시 채우게 될 경우. 둘 다 lowercase
# StrEnum value 와 동일한 string 으로 통일된다.
_NOISE_INTENTS: frozenset[str] = frozenset({"out_of_scope", "general_chat"})

# Minimum usable messages after filtering; below this we skip the LLM call
# entirely and return an EMPTY result so the caller keeps the prior summary.
_MIN_MESSAGES_FOR_SUMMARY: int = 2


@dataclass(frozen=True)
class CompactMessage:
    """Minimal message projection needed for compaction.

    Deliberately decoupled from ``ChatMessage`` ORM objects so the service
    is pure-Python testable without a DB. Callers map rows to this shape.
    """

    role: str  # "user" | "assistant"
    content: str
    intent: str | None  # classifier output stored on user-turn metadata


@dataclass(frozen=True)
class CompactInput:
    """Input payload for a single compaction run."""

    prev_summary: str | None
    messages: list[CompactMessage]


class SessionCompactService:
    """Orchestrates pollution filtering + LLM summarisation.

    The RAG generator is injected so tests can exercise filter + contract
    logic without a live OpenAI client. In production, FastAPI wires in
    the ``RQRAGGenerator`` adapter which enqueues ``compact_messages_job``.
    """

    def __init__(self, rag_generator: object) -> None:
        """Store the LLM generator dependency.

        Args:
            rag_generator: Any object exposing an awaitable
                ``summarize_messages(messages, prev_summary)`` returning
                a ``SummaryResult``.
        """
        self.rag_generator = rag_generator

    def filter_noise(self, messages: list[CompactMessage]) -> list[CompactMessage]:
        """Drop USER turns classified as noise along with their paired ASSISTANT turn.

        Rules (사라진 계획 «세션 컴팩트 Z-5»):
        - If a USER turn's ``intent`` is in :data:`_NOISE_INTENTS`, remove it
          and the immediately following ASSISTANT turn (if any).
        - Missing/None intent is kept — losing medical context is worse than
          retaining a little noise.
        - Order is preserved; no interleaving is introduced.
        """
        kept: list[CompactMessage] = []
        skip_next_assistant = False

        for msg in messages:
            if skip_next_assistant:
                skip_next_assistant = False
                if msg.role == "assistant":
                    continue
                # Unexpected role ordering — fall through and keep the message.

            if msg.role == "user" and msg.intent in _NOISE_INTENTS:
                skip_next_assistant = True
                continue

            kept.append(msg)

        return kept

    async def summarize(self, payload: CompactInput) -> SummaryResult:
        """Filter noise, then delegate to the LLM generator.

        Returns ``SummaryStatus.EMPTY`` without calling the LLM when too
        few messages remain after filtering. Technical failures surface as
        ``FALLBACK`` so the caller keeps the previously stored summary.
        """
        filtered = self.filter_noise(payload.messages)

        if len(filtered) < _MIN_MESSAGES_FOR_SUMMARY:
            logger.info(
                "[COMPACT] skip: filtered=%d min=%d (nothing worth summarising)",
                len(filtered),
                _MIN_MESSAGES_FOR_SUMMARY,
            )
            return SummaryResult(
                status=SummaryStatus.EMPTY,
                summary="",
                consumed_message_count=0,
                token_usage=None,
            )

        forwarded = [{"role": m.role, "content": m.content} for m in filtered]

        try:
            result = await self.rag_generator.summarize_messages(
                messages=forwarded,
                prev_summary=payload.prev_summary,
            )
        except Exception:
            # logger.exception automatically attaches the stack trace; the
            # exception does not bubble because compaction is best-effort.
            logger.exception("[COMPACT] generator failed; fallback to prior summary")
            return SummaryResult(
                status=SummaryStatus.FALLBACK,
                summary="",
                consumed_message_count=0,
                token_usage=None,
            )

        return result

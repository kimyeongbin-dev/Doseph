"""Unit tests for SessionCompactService (pollution filter + LLM call).

Phase Z-A scope: the service orchestrates pollution filtering + LLM call
and returns a SummaryResult. It does not yet write to the DB or schedule
RQ jobs — those belong to Phase Z-B.
"""

from unittest.mock import AsyncMock

import pytest

from app.dtos.rag import SummaryResult, SummaryStatus
from app.services.chat.session_compact_service import (
  CompactInput,
  CompactMessage,
  SessionCompactService,
)

# 옵션 C 에서 IntentType enum 폐기 — legacy intent string 으로 직접 표기.
_INTENT_MEDICATION_INFO = "medication_info"
_INTENT_OUT_OF_SCOPE = "out_of_scope"
_INTENT_GENERAL_CHAT = "general_chat"
_INTENT_SUPPLEMENT_INFO = "supplement_info"


def _user(content: str, intent: str | None = _INTENT_MEDICATION_INFO) -> CompactMessage:
  return CompactMessage(role="user", content=content, intent=intent)


def _asst(content: str) -> CompactMessage:
  return CompactMessage(role="assistant", content=content, intent=None)


class TestCompactFilter:
  """Pollution-filter rules (Z-5)."""

  def test_filter_drops_out_of_scope_pair(self) -> None:
    service = SessionCompactService(rag_generator=AsyncMock())
    messages = [
      _user("타이레놀 복용 중인데 두통이 있어요"),
      _asst("타이레놀은 하루 최대 4g..."),
      _user("주식 추천해줘", intent=_INTENT_OUT_OF_SCOPE),
      _asst("복약 및 건강 관련 질문만..."),
      _user("아스피린이랑 같이 먹어도 되나요?"),
      _asst("두 약은 둘 다 NSAID 계열..."),
    ]

    kept = service.filter_noise(messages)

    contents = [m.content for m in kept]
    assert "주식 추천해줘" not in contents
    assert "복약 및 건강 관련 질문만..." not in contents
    assert "타이레놀 복용 중인데 두통이 있어요" in contents
    assert "아스피린이랑 같이 먹어도 되나요?" in contents

  def test_filter_drops_general_chat_pair(self) -> None:
    service = SessionCompactService(rag_generator=AsyncMock())
    messages = [
      _user("안녕", intent=_INTENT_GENERAL_CHAT),
      _asst("안녕하세요!"),
      _user("비타민D 하루 권장량 얼마예요?", intent=_INTENT_SUPPLEMENT_INFO),
      _asst("성인은 하루 400~800 IU..."),
    ]

    kept = service.filter_noise(messages)

    contents = [m.content for m in kept]
    assert "안녕" not in contents
    assert "안녕하세요!" not in contents
    assert "비타민D 하루 권장량 얼마예요?" in contents

  def test_filter_keeps_when_intent_metadata_missing(self) -> None:
    """Defensive: unclassified turns are kept (medical-context loss is worse than noise)."""
    service = SessionCompactService(rag_generator=AsyncMock())
    messages = [
      _user("알 수 없는 질문", intent=None),
      _asst("알 수 없는 답변"),
    ]

    kept = service.filter_noise(messages)

    assert len(kept) == 2

  def test_filter_drops_orphan_out_of_scope_user_turn(self) -> None:
    """Out-of-scope USER without a following ASSISTANT turn is also dropped."""
    service = SessionCompactService(rag_generator=AsyncMock())
    messages = [
      _user("타이레놀 부작용", intent=_INTENT_MEDICATION_INFO),
      _asst("타이레놀 부작용은..."),
      _user("주식 추천해줘", intent=_INTENT_OUT_OF_SCOPE),
    ]

    kept = service.filter_noise(messages)

    assert [m.content for m in kept] == ["타이레놀 부작용", "타이레놀 부작용은..."]


class TestCompactServiceSummarize:
  """SessionCompactService.summarize contract with the LLM generator."""

  @pytest.mark.asyncio
  async def test_summarize_returns_empty_when_filter_leaves_too_few_messages(self) -> None:
    """< 2 messages after filtering -> skip LLM, return EMPTY."""
    rag_generator = AsyncMock()
    service = SessionCompactService(rag_generator=rag_generator)

    result = await service.summarize(
      CompactInput(
        prev_summary=None,
        messages=[
          _user("안녕", intent=_INTENT_GENERAL_CHAT),
          _asst("안녕하세요"),
        ],
      )
    )

    assert result.status == SummaryStatus.EMPTY
    assert result.summary == ""
    assert result.consumed_message_count == 0
    rag_generator.summarize_messages.assert_not_called()

  @pytest.mark.asyncio
  async def test_summarize_calls_generator_with_filtered_messages(self) -> None:
    """Filtered messages + prev_summary must be forwarded verbatim to the generator."""
    rag_generator = AsyncMock()
    rag_generator.summarize_messages.return_value = SummaryResult(
      status=SummaryStatus.OK,
      summary="사용자는 타이레놀과 아스피린 병용 관련 문의 중.",
      consumed_message_count=4,
      token_usage=None,
    )
    service = SessionCompactService(rag_generator=rag_generator)

    result = await service.summarize(
      CompactInput(
        prev_summary="이전 요약",
        messages=[
          _user("타이레놀 복용 중"),
          _asst("타이레놀 안내..."),
          _user("주식 추천", intent=_INTENT_OUT_OF_SCOPE),
          _asst("복약만 도와드려요"),
          _user("아스피린도 같이?"),
          _asst("두 약 모두..."),
        ],
      )
    )

    assert result.status == SummaryStatus.OK
    assert "타이레놀" in result.summary
    rag_generator.summarize_messages.assert_awaited_once()
    call_kwargs = rag_generator.summarize_messages.await_args.kwargs
    assert call_kwargs["prev_summary"] == "이전 요약"
    forwarded = call_kwargs["messages"]
    assert [m["role"] for m in forwarded] == ["user", "assistant", "user", "assistant"]
    assert "주식 추천" not in [m["content"] for m in forwarded]

  @pytest.mark.asyncio
  async def test_summarize_returns_fallback_when_generator_fails(self) -> None:
    """Generator exceptions surface as FALLBACK — caller keeps previous summary."""
    rag_generator = AsyncMock()
    rag_generator.summarize_messages.side_effect = RuntimeError("LLM down")
    service = SessionCompactService(rag_generator=rag_generator)

    result = await service.summarize(
      CompactInput(
        prev_summary=None,
        messages=[
          _user("타이레놀 복용 중"),
          _asst("타이레놀 안내..."),
        ],
      )
    )

    assert result.status == SummaryStatus.FALLBACK
    assert result.summary == ""

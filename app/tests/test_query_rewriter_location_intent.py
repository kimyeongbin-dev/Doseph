"""Query Rewriter 의 location_search 의도 분류 테스트 (Step 2 Red).

위치 검색 회귀 핫픽스 — IntentType.LOCATION_SEARCH + LocationQuery DTO 가
1st LLM Structured Output 으로 정상 round-trip 되는지 검증.

OpenAI 호출은 ``_get_client`` 에 fake AsyncOpenAI 를 주입해 차단.
"""

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.dtos.query_rewriter import (
  IntentType,
  LocationCategory,
  LocationMode,
  LocationQuery,
  QueryRewriterOutput,
)
from app.services.intent import query_rewriter


def _fake_client_returning(parsed: QueryRewriterOutput) -> MagicMock:
  """``_get_client`` 가 반환할 fake AsyncOpenAI - parsed 를 그대로 echo."""
  completion = MagicMock()
  completion.choices = [MagicMock(message=MagicMock(parsed=parsed))]

  client = MagicMock()
  client.beta.chat.completions.parse = AsyncMock(return_value=completion)
  return client


@pytest.fixture(autouse=True)
def _reset_client_singleton(monkeypatch: pytest.MonkeyPatch) -> None:
  """싱글톤 cache 를 매 테스트마다 초기화."""
  monkeypatch.setattr(query_rewriter, "_client", None)
  monkeypatch.setattr(query_rewriter, "_initialised", False)


# ── DTO round-trip ─────────────────────────────────────────────


class TestLocationQueryDto:
  def test_gps_mode_with_pharmacy_category(self) -> None:
    q = LocationQuery(mode=LocationMode.GPS, category=LocationCategory.PHARMACY, radius_m=1500)
    assert q.mode == LocationMode.GPS
    assert q.category == LocationCategory.PHARMACY
    assert q.radius_m == 1500
    assert q.query is None

  def test_keyword_mode_with_query(self) -> None:
    q = LocationQuery(mode=LocationMode.KEYWORD, query="강남역 약국")
    assert q.mode == LocationMode.KEYWORD
    assert q.query == "강남역 약국"
    assert q.category is None
    assert q.radius_m == 1000  # 기본값


# ── IntentType.LOCATION_SEARCH 가 enum 에 추가되었는지 ───────────


class TestIntentEnum:
  def test_location_search_member_exists(self) -> None:
    assert IntentType.LOCATION_SEARCH.value == "location_search"

  def test_intent_count_is_at_least_five(self) -> None:
    assert len(list(IntentType)) >= 5


# ── 1st LLM 분류 결과 round-trip ────────────────────────────────


class TestRewriteQueryLocationIntent:
  @pytest.mark.asyncio
  async def test_gps_intent_pharmacy(self, monkeypatch: pytest.MonkeyPatch) -> None:
    parsed = QueryRewriterOutput(
      intent=IntentType.LOCATION_SEARCH,
      location_query=LocationQuery(
        mode=LocationMode.GPS,
        category=LocationCategory.PHARMACY,
        radius_m=1000,
      ),
    )
    monkeypatch.setattr(query_rewriter, "_get_client", lambda: _fake_client_returning(parsed))

    out = await query_rewriter.rewrite_query(
      messages=[{"role": "user", "content": "내 주변 약국 찾아줘"}],
    )
    assert out.intent == IntentType.LOCATION_SEARCH
    assert out.location_query is not None
    assert out.location_query.mode == LocationMode.GPS
    assert out.location_query.category == LocationCategory.PHARMACY

  @pytest.mark.asyncio
  async def test_keyword_intent_landmark(self, monkeypatch: pytest.MonkeyPatch) -> None:
    parsed = QueryRewriterOutput(
      intent=IntentType.LOCATION_SEARCH,
      location_query=LocationQuery(
        mode=LocationMode.KEYWORD,
        query="강남역 약국",
      ),
    )
    monkeypatch.setattr(query_rewriter, "_get_client", lambda: _fake_client_returning(parsed))

    out = await query_rewriter.rewrite_query(
      messages=[{"role": "user", "content": "강남역 약국 찾아줘"}],
    )
    assert out.intent == IntentType.LOCATION_SEARCH
    assert out.location_query is not None
    assert out.location_query.mode == LocationMode.KEYWORD
    assert out.location_query.query == "강남역 약국"

  @pytest.mark.asyncio
  async def test_domain_question_unaffected(self, monkeypatch: pytest.MonkeyPatch) -> None:
    """회귀 보호 — 위치 검색 무관한 의학 질문은 domain_question 으로 분류."""
    from app.dtos.query_rewriter import QueryMetadata

    parsed = QueryRewriterOutput(
      intent=IntentType.DOMAIN_QUESTION,
      rewritten_query="타이레놀(아세트아미노펜) 부작용",
      metadata=QueryMetadata(target_ingredients=["아세트아미노펜"]),
    )
    monkeypatch.setattr(query_rewriter, "_get_client", lambda: _fake_client_returning(parsed))

    out = await query_rewriter.rewrite_query(
      messages=[{"role": "user", "content": "타이레놀 부작용"}],
    )
    assert out.intent == IntentType.DOMAIN_QUESTION
    assert out.location_query is None
    assert out.rewritten_query == "타이레놀(아세트아미노펜) 부작용"


# ── system_prompt 에 location_search 분류 규칙 포함 검증 ──────


class TestSystemPromptHasLocationRule:
  def test_prompt_mentions_location_search(self) -> None:
    prompt: Any = query_rewriter.SYSTEM_PROMPT
    assert "location_search" in prompt
    # gps 모드 표현 ('내 주변', '근처', '가까운') 안내
    assert any(kw in prompt for kw in ("내 주변", "근처", "가까운"))
    # keyword 모드 표현 (지명, 랜드마크) 안내
    assert any(kw in prompt for kw in ("지명", "강남역", "랜드마크"))

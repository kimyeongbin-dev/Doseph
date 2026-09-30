"""Unit tests for app.services.chat.intent_orchestrator (PR-D)."""

from __future__ import annotations

from uuid import UUID, uuid4

import pytest

from app.dtos.query_rewriter import IntentType, QueryMetadata, QueryRewriterOutput
from app.services.chat import intent_orchestrator as orch_module
from app.services.chat.intent_orchestrator import classify_user_turn

SAMPLE_PROFILE_ID: UUID = uuid4()
USER_MESSAGES = [{"role": "user", "content": "타이레놀 먹어도 돼?"}]


@pytest.fixture
def stub_dependencies(monkeypatch: pytest.MonkeyPatch):
  """build_medical_context / map_brands / _load_medication_names / rewrite_query stub."""

  async def _fake_build(_: UUID) -> str:
    return "[사용자 의학 컨텍스트]\n- 복용 중인 약: 쿠파린정\n- 기저질환: 간질환"

  async def _fake_load_meds(_: UUID) -> list[str]:
    return ["쿠파린정"]

  async def _fake_map(_brands: list[str]) -> dict[str, list[str]]:
    return {"쿠파린정": ["와파린나트륨"]}

  monkeypatch.setattr(orch_module, "build_medical_context", _fake_build)
  monkeypatch.setattr(orch_module, "_load_medication_names", _fake_load_meds)
  monkeypatch.setattr(orch_module, "map_brands_to_ingredients", _fake_map)
  return monkeypatch


class TestClassifyUserTurn:
  """classify_user_turn (PR-D 3-tuple 반환)."""

  @pytest.mark.asyncio
  @pytest.mark.usefixtures("stub_dependencies")
  async def test_returns_three_tuple_with_rewriter_output(
    self,
    monkeypatch: pytest.MonkeyPatch,
  ) -> None:
    captured: dict[str, object] = {}

    async def _fake_rewrite(messages, medical_context=None):  # noqa: ARG001
      captured["medical_context"] = medical_context
      return QueryRewriterOutput(
        intent=IntentType.DOMAIN_QUESTION,
        rewritten_query="간 질환 환자 와파린(쿠파린정) 복용 중 아세트아미노펜(타이레놀) 병용",
        metadata=QueryMetadata(
          target_drugs=["타이레놀"],
          target_ingredients=["아세트아미노펜"],
          target_conditions=["liver_disease"],
          interaction_concerns=["와파린나트륨"],
        ),
      )

    monkeypatch.setattr(orch_module, "rewrite_query", _fake_rewrite)

    medical_context, mapping_section, output = await classify_user_turn(
      SAMPLE_PROFILE_ID,
      USER_MESSAGES,
    )

    assert "간질환" in medical_context
    assert "[용어 매핑]" in mapping_section
    assert "쿠파린정 → 성분: 와파린나트륨" in mapping_section
    # rewriter 에 medical_context + 용어 매핑 합쳐 전달
    passed = captured["medical_context"]
    assert passed is not None
    assert "간질환" in passed
    assert "[용어 매핑]" in passed
    # output propagate
    assert output.intent == IntentType.DOMAIN_QUESTION
    assert output.metadata.target_ingredients == ["아세트아미노펜"]
    assert output.metadata.interaction_concerns == ["와파린나트륨"]

  @pytest.mark.asyncio
  async def test_empty_context_and_no_medications(
    self,
    monkeypatch: pytest.MonkeyPatch,
  ) -> None:
    async def _fake_build(_: UUID) -> str:
      return ""

    async def _fake_load_meds(_: UUID) -> list[str]:
      return []

    async def _fake_map(_: list[str]) -> dict[str, list[str]]:
      return {}

    captured: dict[str, object] = {}

    async def _fake_rewrite(messages, medical_context=None):  # noqa: ARG001
      captured["medical_context"] = medical_context
      return QueryRewriterOutput(intent=IntentType.GREETING, direct_answer="안녕하세요")

    monkeypatch.setattr(orch_module, "build_medical_context", _fake_build)
    monkeypatch.setattr(orch_module, "_load_medication_names", _fake_load_meds)
    monkeypatch.setattr(orch_module, "map_brands_to_ingredients", _fake_map)
    monkeypatch.setattr(orch_module, "rewrite_query", _fake_rewrite)

    medical_context, mapping_section, output = await classify_user_turn(
      SAMPLE_PROFILE_ID,
      [{"role": "user", "content": "안녕"}],
    )

    assert medical_context == ""
    assert mapping_section == ""
    assert captured["medical_context"] is None
    assert output.intent == IntentType.GREETING

  @pytest.mark.asyncio
  @pytest.mark.usefixtures("stub_dependencies")
  async def test_propagates_output_unchanged(
    self,
    monkeypatch: pytest.MonkeyPatch,
  ) -> None:
    expected = QueryRewriterOutput(intent=IntentType.AMBIGUOUS, direct_answer="명확화 필요")

    async def _fake_rewrite(messages, medical_context=None):  # noqa: ARG001
      return expected

    monkeypatch.setattr(orch_module, "rewrite_query", _fake_rewrite)

    _, _, output = await classify_user_turn(SAMPLE_PROFILE_ID, USER_MESSAGES)
    assert output is expected

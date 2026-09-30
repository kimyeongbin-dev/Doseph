"""Unit tests for app.services.chat.medical_context — medication + survey 빌더.

PLAN.md §4.1 — medical_context 의 4가지 의도된 동작.
Phase 3 [Implement] Green — Tortoise model mock.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

import pytest

from app.services.chat import medical_context as mc_module
from app.services.chat.medical_context import build_medical_context

SAMPLE_PROFILE_ID: UUID = uuid4()


class _ProfileStub:
  def __init__(self, health_survey: dict[str, Any] | None) -> None:
    self.health_survey = health_survey


async def _patch_load(
  monkeypatch: pytest.MonkeyPatch,
  medications: list[str],
  health_survey: dict[str, Any] | None,
) -> None:
  """_load 를 fixture mock 으로 교체 (DB 우회)."""

  async def _fake_load(_: UUID) -> tuple[list[str], _ProfileStub | None]:
    profile = _ProfileStub(health_survey) if health_survey is not None else None
    return medications, profile

  monkeypatch.setattr(mc_module, "_load", _fake_load)


class TestBuildMedicalContext:
  """build_medical_context 단위 테스트."""

  @pytest.mark.asyncio
  async def test_full_context(self, monkeypatch: pytest.MonkeyPatch) -> None:
    """medication + health_survey 모두 채워짐 → 5개 줄."""
    await _patch_load(
      monkeypatch,
      medications=["메트포민", "와파린", "오메가3", "타이레놀"],
      health_survey={
        "conditions": ["당뇨", "고혈압"],
        "allergies": ["페니실린"],
        "is_smoking": False,
        "is_drinking": False,
      },
    )
    result = await build_medical_context(SAMPLE_PROFILE_ID)
    assert "[사용자 의학 컨텍스트]" in result
    assert "메트포민, 와파린, 오메가3, 타이레놀" in result
    assert "당뇨, 고혈압" in result
    assert "페니실린" in result
    assert "비흡연" in result
    assert "비음주" in result

  @pytest.mark.asyncio
  async def test_no_health_survey(self, monkeypatch: pytest.MonkeyPatch) -> None:
    """profile.health_survey = None → medication 만."""
    await _patch_load(monkeypatch, medications=["타이레놀"], health_survey=None)
    result = await build_medical_context(SAMPLE_PROFILE_ID)
    assert "[사용자 의학 컨텍스트]" in result
    assert "타이레놀" in result
    assert "기저질환" not in result
    assert "흡연" not in result

  @pytest.mark.asyncio
  async def test_no_medication(self, monkeypatch: pytest.MonkeyPatch) -> None:
    """medication 0개 + health_survey 일부 → health_survey 섹션만."""
    await _patch_load(
      monkeypatch,
      medications=[],
      health_survey={"conditions": ["당뇨"], "is_smoking": True},
    )
    result = await build_medical_context(SAMPLE_PROFILE_ID)
    assert "복용 중인 약" not in result
    assert "당뇨" in result
    assert "흡연" in result

  @pytest.mark.asyncio
  async def test_empty_profile(self, monkeypatch: pytest.MonkeyPatch) -> None:
    """medication 0 + health_survey None → 빈 문자열."""
    await _patch_load(monkeypatch, medications=[], health_survey=None)
    assert await build_medical_context(SAMPLE_PROFILE_ID) == ""

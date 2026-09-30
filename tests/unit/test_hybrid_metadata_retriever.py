"""Unit tests for app.services.rag.retrievers.hybrid_metadata.

PLAN.md (RAG 재설계 PR-C). DB 호출은 stub - SQL 빌더 형태와 결과 매핑만 검증.
"""

from __future__ import annotations

from typing import Any

import pytest

from app.services.rag.retrievers import hybrid_metadata
from app.services.rag.retrievers.hybrid_metadata import (
  RetrievedChunk,
  _build_hybrid_sql,
  _vector_literal,
  retrieve_with_metadata,
)


class TestVectorLiteral:
  def test_format(self) -> None:
    assert _vector_literal([0.5, 0.25, 0.125]) == "[0.500000,0.250000,0.125000]"


class TestBuildHybridSql:
  """_build_hybrid_sql - 동적 WHERE 절 분기."""

  def test_ingredients_only(self) -> None:
    sql = _build_hybrid_sql(has_section_filter=False, has_condition_filter=False)
    assert "mc.ingredients ?| $2::text[]" in sql
    assert "section = ANY" not in sql
    assert "target_conditions = '[]'::jsonb" not in sql
    assert "LIMIT $3" in sql  # ingredients + limit

  def test_with_section_filter(self) -> None:
    sql = _build_hybrid_sql(has_section_filter=True, has_condition_filter=False)
    assert "mc.section = ANY($3::text[])" in sql
    assert "target_conditions = '[]'::jsonb" not in sql
    assert "LIMIT $4" in sql

  def test_with_condition_filter(self) -> None:
    sql = _build_hybrid_sql(has_section_filter=False, has_condition_filter=True)
    assert "section = ANY" not in sql
    # condition idx 는 section 없으면 $3
    assert "mc.target_conditions ?| $3::text[]" in sql
    assert "mc.target_conditions = '[]'::jsonb" in sql
    assert "LIMIT $4" in sql

  def test_with_section_and_condition(self) -> None:
    sql = _build_hybrid_sql(has_section_filter=True, has_condition_filter=True)
    assert "mc.section = ANY($3::text[])" in sql
    assert "mc.target_conditions ?| $4::text[]" in sql
    assert "LIMIT $5" in sql

  def test_halfvec_cast_in_distance(self) -> None:
    sql = _build_hybrid_sql(has_section_filter=False, has_condition_filter=False)
    assert "(mc.embedding <=> $1::halfvec(3072))" in sql


@pytest.fixture
def stub_connection(monkeypatch: pytest.MonkeyPatch):
  """tortoise.connections 의 execute_query_dict stub."""
  captured: dict[str, Any] = {"sql": None, "params": None}
  rows: list[dict[str, Any]] = []

  class _FakeConn:
    async def execute_query_dict(self, sql: str, params):
      captured["sql"] = sql
      captured["params"] = params
      return rows

  def _set_rows(new_rows: list[dict[str, Any]]) -> None:
    rows.clear()
    rows.extend(new_rows)

  monkeypatch.setattr(hybrid_metadata.connections, "get", lambda _name: _FakeConn())
  return captured, _set_rows


class TestRetrieveWithMetadata:
  """retrieve_with_metadata - 메타 필터 + 결과 매핑."""

  @pytest.mark.asyncio
  async def test_empty_ingredients_short_circuits(
    self,
    stub_connection: tuple[dict[str, Any], object],
  ) -> None:
    """target_ingredients 빈 list -> SQL 호출 없이 빈 결과."""
    captured, _set_rows = stub_connection
    result = await retrieve_with_metadata(
      query_embedding=[0.0] * 3072,
      target_ingredients=[],
    )
    assert result == []
    assert captured["sql"] is None  # SQL 호출 자체 안 됨

  @pytest.mark.asyncio
  async def test_only_ingredients_filter(
    self,
    stub_connection: tuple[dict[str, Any], object],
  ) -> None:
    captured, set_rows = stub_connection
    set_rows([
      {
        "chunk_id": 1,
        "medicine_info_id": 100,
        "medicine_name": "타이레놀이알서방정",
        "section": "drug_interaction",
        "content": "...",
        "ingredients": ["아세트아미노펜"],
        "target_conditions": [],
        "distance": 0.18,
      }
    ])

    result = await retrieve_with_metadata(
      query_embedding=[0.5] * 3072,
      target_ingredients=["아세트아미노펜"],
    )

    # SQL 에 section / condition 절 없음 (WHERE 절 한정)
    assert "mc.section = ANY" not in captured["sql"]
    assert "target_conditions = '[]'::jsonb" not in captured["sql"]
    # params: [vector_str, ingredients, limit]
    assert captured["params"][1] == ["아세트아미노펜"]
    assert captured["params"][-1] == 15  # default limit
    # 결과 매핑
    assert len(result) == 1
    assert result[0].medicine_name == "타이레놀이알서방정"
    assert result[0].ingredients == ["아세트아미노펜"]
    assert result[0].distance == 0.18

  @pytest.mark.asyncio
  async def test_with_all_filters(
    self,
    stub_connection: tuple[dict[str, Any], object],
  ) -> None:
    captured, set_rows = stub_connection
    set_rows([])
    await retrieve_with_metadata(
      query_embedding=[0.1] * 3072,
      target_ingredients=["아세트아미노펜", "와파린나트륨"],
      target_sections=["drug_interaction", "adverse_reaction"],
      target_conditions=["liver_disease"],
      limit=10,
    )
    params = captured["params"]
    # params 순서: vector, ingredients, sections, conditions, limit
    assert params[1] == ["아세트아미노펜", "와파린나트륨"]
    assert params[2] == ["drug_interaction", "adverse_reaction"]
    assert params[3] == ["liver_disease"]
    assert params[4] == 10

  @pytest.mark.asyncio
  async def test_section_only_no_conditions(
    self,
    stub_connection: tuple[dict[str, Any], object],
  ) -> None:
    captured, set_rows = stub_connection
    set_rows([])
    await retrieve_with_metadata(
      query_embedding=[0.1] * 3072,
      target_ingredients=["메트포르민염산염"],
      target_sections=["intake_guide"],
      target_conditions=None,
    )
    # SQL 에 condition 절 없음, section 절 있음 (WHERE 절 한정 — SELECT 의 컬럼은 항상 있음)
    assert "mc.section = ANY" in captured["sql"]
    assert "target_conditions = '[]'::jsonb" not in captured["sql"]


class TestRetrievedChunkAdapter:
  """RetrievedChunk - similarity / to_dict adapter."""

  def test_similarity_inverse_of_distance(self) -> None:
    c = RetrievedChunk(
      medicine_info_id=1,
      medicine_name="x",
      section="overview",
      content="c",
      ingredients=["a"],
      target_conditions=[],
      distance=0.2,
    )
    assert c.similarity == 0.8

  def test_to_dict_assembler_friendly(self) -> None:
    c = RetrievedChunk(
      medicine_info_id=1,
      medicine_name="타이레놀이알서방정",
      section="drug_interaction",
      content="content body",
      ingredients=["아세트아미노펜"],
      target_conditions=["liver_disease"],
      distance=0.15,
    )
    d = c.to_dict()
    assert d["medicine_name"] == "타이레놀이알서방정"
    assert d["section"] == "drug_interaction"
    assert d["content"] == "content body"
    assert d["ingredients"] == ["아세트아미노펜"]
    assert d["score"] == 0.85

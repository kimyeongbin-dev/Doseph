"""Unit tests for scripts.embed_medicine_chunks - 메타 헤더 + INSERT SQL 빌더.

PLAN.md (RAG 재설계 PR-A) §A - chunk content 에 [성분: ...] 헤더 +
ingredients JSONB 컬럼 채움 + INSERT 시 새 컬럼 적용 검증.
"""

from __future__ import annotations

from app.models.medicine_chunk import MedicineChunkSection
from app.services.medicine_doc_parser import Article
from scripts.embed_medicine_chunks import _format_chunk_content


class TestFormatChunkContentHeader:
  """_format_chunk_content - 헤더 prefix 형식."""

  def test_header_includes_drug_and_ingredients_and_section(self) -> None:
    article = Article(title="이상반응", body="발진, 가려움증")
    out = _format_chunk_content(
      "타이레놀이알서방정 650mg",
      MedicineChunkSection.ADVERSE_REACTION,
      article,
      ingredients=["아세트아미노펜"],
    )
    first_line = out.split("\n")[0]
    assert "[약: 타이레놀이알서방정 650mg]" in first_line
    assert "[성분: 아세트아미노펜]" in first_line
    assert "[이상반응]" in first_line

  def test_multiple_ingredients_joined_by_comma(self) -> None:
    article = Article(title="t", body="b")
    out = _format_chunk_content(
      "낙소졸정500/20밀리그램",
      MedicineChunkSection.DRUG_INTERACTION,
      article,
      ingredients=["나프록센", "에스오메프라졸"],
    )
    first_line = out.split("\n")[0]
    assert "[성분: 나프록센, 에스오메프라졸]" in first_line

  def test_no_ingredients_omits_section_but_keeps_drug(self) -> None:
    article = Article(title="t", body="b")
    out = _format_chunk_content(
      "타이레놀",
      MedicineChunkSection.OVERVIEW,
      article,
      ingredients=None,
    )
    first_line = out.split("\n")[0]
    assert "[약: 타이레놀]" in first_line
    assert "[성분:" not in first_line
    assert "[개요]" in first_line

  def test_empty_ingredients_list_omits_section(self) -> None:
    article = Article(title="t", body="b")
    out = _format_chunk_content(
      "타이레놀",
      MedicineChunkSection.OVERVIEW,
      article,
      ingredients=[],
    )
    first_line = out.split("\n")[0]
    assert "[성분:" not in first_line

  def test_body_and_title_appended_after_header(self) -> None:
    article = Article(title="제목줄", body="본문줄")
    out = _format_chunk_content(
      "약",
      MedicineChunkSection.OVERVIEW,
      article,
      ingredients=["성분"],
    )
    lines = out.split("\n")
    # line0 = 헤더, line1 = 제목, line2 = 본문
    assert "[약: 약]" in lines[0]
    assert lines[1] == "제목줄"
    assert lines[2] == "본문줄"

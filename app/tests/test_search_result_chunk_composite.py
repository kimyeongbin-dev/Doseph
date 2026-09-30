"""Tests for SearchResult restructured as MedicineInfo + matched chunks.

After main's drug-data-integration, embeddings live in `medicine_chunk`
rather than on `medicine_info` directly. A single pgvector query returns
multiple chunks, potentially several from the same drug. The pipeline
aggregates chunks under their parent `medicine_info` and surfaces them
as one `SearchResult` carrying:

  - `medicine`: MedicineInfo row (parent)
  - `matched_chunks`: list of ChunkMatch entries (chunk + per-chunk score)
  - `vector_score`: the top-1 chunk score (representative)
  - `keyword_score`, `final_score`: aggregated ranking signals

`RetrievalMetadata.medicine_usages` is redefined to pull from
`medicine_info.category` since the old `usage` field no longer exists.
"""

from app.dtos.rag import ChunkMatch, RetrievalMetadata, SearchResult


class TestChunkMatchShape:
  """ChunkMatch pairs a medicine_chunk row with its per-chunk score."""

  def test_has_required_fields(self) -> None:
    expected = {"chunk", "vector_score"}
    assert expected.issubset(ChunkMatch.model_fields.keys())


class TestSearchResultCompositeShape:
  """SearchResult now wraps MedicineInfo + matched chunks + aggregated scores."""

  def test_exposes_medicine_field(self) -> None:
    assert "medicine" in SearchResult.model_fields

  def test_exposes_matched_chunks_field(self) -> None:
    assert "matched_chunks" in SearchResult.model_fields

  def test_exposes_vector_score_field(self) -> None:
    assert "vector_score" in SearchResult.model_fields

  def test_exposes_keyword_score_field(self) -> None:
    assert "keyword_score" in SearchResult.model_fields

  def test_exposes_final_score_field(self) -> None:
    assert "final_score" in SearchResult.model_fields

  def test_matched_chunks_default_is_empty_list(self) -> None:
    field = SearchResult.model_fields["matched_chunks"]
    default_value = field.default_factory() if field.default_factory is not None else field.default
    assert default_value == []


class TestRetrievalMetadataCategoryField:
  """RetrievalMetadata keeps the public shape but sources medicine_usages from category."""

  def test_still_exposes_medicine_usages(self) -> None:
    assert "medicine_usages" in RetrievalMetadata.model_fields

  def test_medicine_usages_description_mentions_category(self) -> None:
    field = RetrievalMetadata.model_fields["medicine_usages"]
    description = field.description or ""
    assert "category" in description.lower()

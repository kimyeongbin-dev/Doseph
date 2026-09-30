"""Tests for the sample medicine data collection script.

Separate from scripts/crawling/sync_medicine_data.py (which pulls the
full ~43k dataset), this smaller entry point fetches just enough rows
for local UI testing and RAG validation. The team's API-call style is
respected (httpx pagination, MedicineInfoRepository.bulk_upsert, same
DataSyncLog record shape), but the payload is capped by a --limit flag
and each inserted medicine is chunked + embedded locally so the RAG
pipeline can run end-to-end.
"""

import inspect

from scripts.crawling import fetch_sample


class TestCliInterface:
  """CLI must expose --limit (default 200, RAG 권장값) and --api-key, plus sample defaults."""

  def test_build_parser_exposes_limit(self) -> None:
    parser = fetch_sample.build_parser()
    ns = parser.parse_args([])
    assert hasattr(ns, "limit")
    assert ns.limit == 200

  def test_build_parser_accepts_custom_limit(self) -> None:
    parser = fetch_sample.build_parser()
    ns = parser.parse_args(["--limit", "10"])
    assert ns.limit == 10

  def test_build_parser_exposes_api_key(self) -> None:
    parser = fetch_sample.build_parser()
    ns = parser.parse_args([])
    assert hasattr(ns, "api_key")

  def test_build_parser_exposes_skip_embed(self) -> None:
    """--skip-embed bypasses chunk creation + embedding (DB structure only)."""
    parser = fetch_sample.build_parser()
    ns = parser.parse_args([])
    assert hasattr(ns, "skip_embed")
    assert ns.skip_embed is False


class TestFetchSampleHelpers:
  """Script exposes a few helpers so internals stay testable."""

  def test_iter_section_chunks_signature(self) -> None:
    """iter_section_chunks(medicine) -> list[(section, chunk_index, content)]."""
    sig = inspect.signature(fetch_sample.iter_section_chunks)
    params = list(sig.parameters.keys())
    assert "medicine" in params

  def test_normalize_vector_returns_unit_length(self) -> None:
    import numpy as np

    raw = [3.0, 4.0] + [0.0] * 766
    result = fetch_sample.normalize_vector(raw)
    assert len(result) == 768
    assert abs(np.linalg.norm(result) - 1.0) < 1e-6


class TestFetchSampleEntryPoint:
  """`fetch_sample_run` is the async orchestrator exposed for imports/tests."""

  def test_run_is_async(self) -> None:
    assert inspect.iscoroutinefunction(fetch_sample.fetch_sample_run)

  def test_run_signature_has_limit_and_skip_embed(self) -> None:
    sig = inspect.signature(fetch_sample.fetch_sample_run)
    params = list(sig.parameters.keys())
    assert "limit" in params
    assert "skip_embed" in params
    assert "api_key" in params

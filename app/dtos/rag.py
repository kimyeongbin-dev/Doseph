"""RAG (Retrieval-Augmented Generation) DTO models.

Data transfer objects for the medicine_chunk + medicine_info RAG pipeline:
- SearchFilters: metadata filters applied at retrieval time.
- ChunkMatch: one pgvector top-k row (chunk + per-chunk score).
- SearchResult: MedicineInfo parent + aggregated matched chunks + scores.
- RetrievalMetadata: summary of the retrieval stage (for debug/cache keys).
- TokenUsage: LLM token usage for the assistant turn.
- ChatCompletion: LLM output (answer + optional token usage).
- SummaryStatus / SummaryResult: session compaction LLM outcome.
- RAGResponse: legacy pipeline payload (옵션 C 잔재 — Step 5 의 RAGPipeline
  폐기와 함께 호출처 0, 향후 정리 후보).
"""

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.models.medicine_chunk import MedicineChunk
from app.models.medicine_info import MedicineInfo


class SearchFilters(BaseModel):
  """Retrieval-time filters applied over medicine_chunk rows."""

  medicine_names: list[str] = Field(default_factory=list)


class ChunkMatch(BaseModel):
  """A single pgvector top-k hit: one medicine_chunk + its vector score."""

  model_config = ConfigDict(arbitrary_types_allowed=True)

  chunk: MedicineChunk = Field(..., description="medicine_chunk row (section + content + model_version)")
  vector_score: float = Field(..., description="Cosine similarity of this chunk against the query")


class SearchResult(BaseModel):
  """Aggregated retrieval hit: parent medicine + all matched chunks.

  The retriever groups chunk-level pgvector hits by parent `medicine_info`.
  `vector_score` is the representative (top-1) chunk score, while
  `matched_chunks` preserves every surfaced section for downstream
  context building.
  """

  model_config = ConfigDict(arbitrary_types_allowed=True)

  medicine: MedicineInfo = Field(..., description="Parent medicine_info row")
  matched_chunks: list[ChunkMatch] = Field(
    default_factory=list,
    description="Chunks that contributed to this result (sorted by vector_score desc)",
  )
  vector_score: float = Field(..., description="Representative (top-1) chunk vector score")
  keyword_score: float = Field(..., description="Keyword overlap score against name/category/content")
  final_score: float = Field(..., description="Final weighted score used for ranking")


class RetrievalMetadata(BaseModel):
  """Structured summary of the retrieval stage.

  Persisted on the user turn's `messages.metadata` to support multi-turn
  pronoun resolution and cache key construction.
  """

  medicine_names: list[str] = Field(default_factory=list, description="Top-k medicine names")
  medicine_usages: list[str] = Field(
    default_factory=list,
    description="Top-k medicine categories (sourced from medicine_info.category)",
  )
  top_similarity: float | None = Field(None, description="Cosine similarity of the top-1 match")
  vector_score: float | None = Field(None, description="Top-1 vector similarity score")
  keyword_score: float | None = Field(None, description="Top-1 keyword score")
  final_score: float | None = Field(None, description="Top-1 final weighted score")


class TokenUsage(BaseModel):
  """LLM token usage, mirroring OpenAI's response.usage."""

  model: str = Field(..., description="LLM model identifier")
  prompt_tokens: int = Field(..., description="Tokens sent in the prompt")
  completion_tokens: int = Field(..., description="Tokens generated in the completion")
  total_tokens: int = Field(..., description="Sum of prompt and completion tokens")


class ChatCompletion(BaseModel):
  """RAGGenerator output: the text answer plus optional token usage."""

  answer: str = Field(..., description="Generated assistant reply")
  token_usage: TokenUsage | None = Field(None, description="LLM token usage when available")


class SummaryStatus(StrEnum):
  """Outcome of the session-compact summarization stage."""

  OK = "ok"
  EMPTY = "empty"  # nothing to summarize after filtering
  FALLBACK = "fallback"  # technical failure; caller should keep previous summary


class SummaryResult(BaseModel):
  """Structured result of RAGGenerator.summarize_messages.

  Returned by the session-compact path. Callers read ``summary`` only when
  ``status == OK``; otherwise they keep the pre-existing session summary
  untouched so compaction failures never erase prior context.
  """

  status: SummaryStatus = Field(..., description="Summarization outcome category")
  summary: str = Field("", description="Unified summary text when status is OK, empty string otherwise")
  consumed_message_count: int = Field(
    0,
    description="Number of message rows actually fed into the LLM after pollution filtering",
  )
  token_usage: TokenUsage | None = Field(None, description="LLM token usage when the summary call succeeded")


class RAGResponse(BaseModel):
  """Top-level RAG pipeline response consumed by MessageService."""

  answer: str
  sources: list[dict[str, Any]] = Field(default_factory=list)
  confidence_score: float
  search_results_count: int
  processing_time_ms: int

  # Debug/audit fields persisted on messages.metadata
  intent: str = Field(..., description="Classified intent for this turn")
  query_keywords: list[str] = Field(default_factory=list, description="Keywords extracted from the user query")
  retrieval: RetrievalMetadata = Field(default_factory=RetrievalMetadata, description="Retrieval stage summary")
  token_usage: TokenUsage | None = Field(None, description="LLM token usage when available")

"""Tests for the expanded RAG response surface carrying debug metadata.

The pipeline needs to surface enough information for MessageService to
persist it on the user/assistant messages:

- RAGResponse exposes intent / query_keywords / retrieval / token_usage
- ChatCompletion dataclass (answer + token_usage) is returned by
  RAGGenerator.generate_chat_response so callers can forward usage to
  the assistant-turn metadata.
"""

from app.dtos.rag import ChatCompletion, RAGResponse, RetrievalMetadata, TokenUsage


class TestRAGResponseMetadataFields:
  """RAGResponse must carry the fields needed for message metadata persistence."""

  def test_has_intent_field(self) -> None:
    assert "intent" in RAGResponse.model_fields

  def test_has_query_keywords_field(self) -> None:
    assert "query_keywords" in RAGResponse.model_fields

  def test_has_retrieval_field(self) -> None:
    assert "retrieval" in RAGResponse.model_fields

  def test_has_token_usage_field(self) -> None:
    assert "token_usage" in RAGResponse.model_fields


class TestRetrievalMetadataShape:
  """RetrievalMetadata groups scores and top-k for debugging / cache keys."""

  def test_fields(self) -> None:
    expected = {
      "medicine_names",
      "medicine_usages",
      "top_similarity",
      "vector_score",
      "keyword_score",
      "final_score",
    }
    assert expected.issubset(RetrievalMetadata.model_fields.keys())

  def test_empty_default_is_constructible(self) -> None:
    m = RetrievalMetadata()
    assert m.medicine_names == []
    assert m.medicine_usages == []
    assert m.top_similarity is None


class TestTokenUsageShape:
  """TokenUsage mirrors OpenAI response.usage."""

  def test_fields(self) -> None:
    expected = {"model", "prompt_tokens", "completion_tokens", "total_tokens"}
    assert expected.issubset(TokenUsage.model_fields.keys())


class TestChatCompletionShape:
  """RAGGenerator.generate_chat_response returns ChatCompletion(answer, token_usage)."""

  def test_has_answer_field(self) -> None:
    assert "answer" in ChatCompletion.model_fields

  def test_has_token_usage_field(self) -> None:
    assert "token_usage" in ChatCompletion.model_fields

  def test_token_usage_is_optional(self) -> None:
    """Providers without usage info (e.g., API key missing fallback) return None."""
    completion = ChatCompletion(answer="fallback reply", token_usage=None)
    assert completion.token_usage is None

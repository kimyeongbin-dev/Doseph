"""RAG 최종 답변 생성 — OpenAI Chat Completion 호출.

호출자(FastAPI 측 ``RAGPipeline``)가 검색 컨텍스트를 system prompt 에
미리 삽입해 넘긴다. 본 모듈은 그 prompt + 메시지 리스트를 OpenAI 에 보내
응답 텍스트와 토큰 사용량을 반환할 뿐, 검색·임베딩에는 관여하지 않는다.
"""

import logging

from openai.types.chat import ChatCompletion as OpenAIChatCompletion

from ai_worker.core.openai_client import get_openai_client
from ai_worker.domains.rag.prompt_builder import build_chat_system_prompt
from app.dtos.rag import ChatCompletion, TokenUsage

logger = logging.getLogger(__name__)

_MODEL = "gpt-4o"
_TEMPERATURE = 0.7
_MAX_TOKENS = 800
_FALLBACK_ANSWER = "현재 AI 응답을 생성할 수 있는 설정이 준비되지 않았어요."


async def generate_response(
  messages: list[dict[str, str]],
  system_prompt: str | None = None,
) -> ChatCompletion:
  """대화 메시지 + system prompt 로 답변을 생성한다.

  Args:
      messages: 사용자/어시스턴트 턴 리스트 (마지막은 사용자 질문).
      system_prompt: 컨텍스트가 삽입된 system prompt. ``None`` 이면
          persona-only fallback prompt 사용.

  Returns:
      ``ChatCompletion`` — 답변 텍스트와 토큰 사용량.
  """
  client = get_openai_client()
  if client is None:
    return ChatCompletion(answer=_FALLBACK_ANSWER, token_usage=None)

  instruction = build_chat_system_prompt(system_prompt)
  response = await client.chat.completions.create(
    model=_MODEL,
    messages=[{"role": "system", "content": instruction}, *messages],
    temperature=_TEMPERATURE,
    max_tokens=_MAX_TOKENS,
  )
  return _to_chat_completion(response)


def _to_chat_completion(response: OpenAIChatCompletion) -> ChatCompletion:
  """OpenAI 응답을 ChatCompletion DTO 로 변환."""
  answer = response.choices[0].message.content
  return ChatCompletion(answer=answer, token_usage=_extract_token_usage(response))


def _extract_token_usage(response: OpenAIChatCompletion) -> TokenUsage | None:
  """response.usage 가 있으면 TokenUsage 로 변환."""
  if response.usage is None:
    return None
  return TokenUsage(
    model=_MODEL,
    prompt_tokens=response.usage.prompt_tokens,
    completion_tokens=response.usage.completion_tokens,
    total_tokens=response.usage.total_tokens,
  )

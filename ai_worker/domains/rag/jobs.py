"""RAG RQ jobs — FastAPI 가 ``ai`` 큐로 enqueue 하는 진입점.

PR-D 이후 1개의 RQ task 만 노출 (RAG 재설계 후 retrieve_medicine_chunks 폐기):

- ``generate_chat_response_job`` → ``response_generator.generate_response``

이전 ``embed_text_job`` (ko-sroberta) 폐기 — query 측 임베딩은 FastAPI 의
``app.services.rag.openai_embedding`` 이 직접 OpenAI API 호출.
이전 진단 로그 (``[LLM-Diag] INPUT/OUTPUT``) 제거 — PR-D cutover 완료.
"""


async def generate_chat_response_job(
  messages: list[dict[str, str]],
  system_prompt: str | None = None,
) -> dict:
  """[RQ Task] 최종 답변 생성.

  Args:
      messages: 대화 턴 리스트 (마지막은 사용자 질문).
      system_prompt: persona + medical_context + 용어 매핑 + RAG context 가
          합쳐진 system prompt.

  Returns:
      ``{"answer", "token_usage"}`` 형태 dict.
  """
  from ai_worker.domains.rag.response_generator import generate_response

  result = await generate_response(messages=messages, system_prompt=system_prompt)
  return {
    "answer": result.answer,
    "token_usage": result.token_usage.model_dump() if result.token_usage is not None else None,
  }

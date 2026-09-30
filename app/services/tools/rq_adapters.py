"""RQ-backed adapters for the tool-calling subsystem (FastAPI side).

FastAPI never holds the actual tool execution — it only enqueues an
AI-Worker RQ job and polls the result with ``asyncio.sleep`` so the event
loop stays free.

Entry points (RAG 4단 파이프라인 진입 후 Router LLM 폐기):

- ``run_tool_calls_via_rq(calls, queue)`` → ``{tool_call_id: result}``
    fan-out 으로 만든 search_medicine_knowledge_base tool_calls 를 병렬 실행.
- ``generate_chat_response_via_rq(messages, system_prompt, queue)``
    2nd LLM (4o) 호출.

Failures map to two dedicated exceptions — ``ToolTimeoutError`` (poll
deadline exceeded) and ``ToolJobError`` (RQ status transitioned to
"failed") — so the service layer can distinguish wait vs. worker errors.
"""

import asyncio
import logging
import time
from typing import Any

logger = logging.getLogger(__name__)

RUN_TOOL_CALLS_JOB_REF = "ai_worker.domains.tool_calling.jobs.run_tool_calls_job"
GENERATE_CHAT_RESPONSE_JOB_REF = "ai_worker.domains.rag.jobs.generate_chat_response_job"

_DEFAULT_POLL_INTERVAL_SEC = 0.1
_DEFAULT_RUN_TIMEOUT_SEC = 180.0  # HNSW 인덱스 빌드 동안 SEQ scan fallback 마진 (빌드 완료 후 별 PR 로 60s 복귀)
_DEFAULT_GENERATE_TIMEOUT_SEC = 60.0  # LLM call; matches rq_llm.py


class ToolTimeoutError(TimeoutError):
  """Raised when a tool-calling RQ job does not finish before the deadline."""


class ToolJobError(RuntimeError):
  """Raised when a tool-calling RQ job transitions to a failed status."""


async def _await_result(
  job: Any,
  *,
  poll_interval: float,
  timeout: float,  # noqa: ASYNC109 — intentional deadline param; custom ToolTimeoutError precludes asyncio.timeout
) -> Any:
  """Poll an RQ ``Job`` until it finishes, fails, or the deadline passes.

  Args:
      job: Object exposing ``refresh()``, ``get_status()``, ``result``,
          ``exc_info`` — matches both the real ``rq.job.Job`` and the
          test ``_FakeJob`` stub.
      poll_interval: Seconds between status polls.
      timeout: Absolute wait cap in seconds.

  Returns:
      Whatever the worker produced for ``job.result``.

  Raises:
      ToolTimeoutError: If the deadline is reached before completion.
      ToolJobError: If the job reports a failed status.
  """
  start = time.monotonic()
  deadline = start + timeout

  while True:
    job.refresh()
    status = job.get_status()

    if status == "finished":
      logger.debug("[ToolCalling] RQ job finished in %.3fs", time.monotonic() - start)
      return job.result

    if status == "failed":
      logger.warning("[ToolCalling] RQ job failed after %.3fs", time.monotonic() - start)
      raise ToolJobError(job.exc_info or "AI-Worker tool job failed")

    if time.monotonic() >= deadline:
      logger.warning("[ToolCalling] RQ job timeout after %.1fs (poll interval=%.3fs)", timeout, poll_interval)
      raise ToolTimeoutError(f"Tool job did not finish within {timeout}s")

    await asyncio.sleep(poll_interval)


async def run_tool_calls_via_rq(
  *,
  calls: list[dict[str, Any]],
  queue: Any,
  poll_interval: float = _DEFAULT_POLL_INTERVAL_SEC,
  timeout: float = _DEFAULT_RUN_TIMEOUT_SEC,  # noqa: ASYNC109 — poll deadline; see _await_result
) -> dict[str, Any]:
  """Enqueue ``run_tool_calls_job`` and return ``{tool_call_id: result}``.

  An empty ``calls`` list short-circuits to ``{}`` without hitting the
  queue — saves a pointless round-trip when the LLM did not request
  any tools.

  Args:
      calls: Pickle-safe dicts consumed by the worker. Each carries
          ``tool_call_id``, ``name``, ``arguments``, and (for location
          tools) ``geolocation``.
      queue: ``rq.Queue`` instance or stub.
      poll_interval: Seconds between status polls.
      timeout: Max wait in seconds.

  Returns:
      The worker's aggregated result dict, keyed by ``tool_call_id``.
      Successful entries carry ``{"places": [...]}``; failures carry
      ``{"error": str}`` per the worker's isolation contract.

  Raises:
      ToolTimeoutError: Polling deadline exceeded.
      ToolJobError: Worker returned a failed status.
  """
  if not calls:
    return {}

  logger.info("[ToolCalling] enqueue run_tool_calls_job calls=%d", len(calls))
  job = queue.enqueue(RUN_TOOL_CALLS_JOB_REF, calls)
  return await _await_result(job, poll_interval=poll_interval, timeout=timeout)


async def generate_chat_response_via_rq(
  *,
  messages: list[dict[str, Any]],
  queue: Any,
  system_prompt: str | None = None,
  poll_interval: float = _DEFAULT_POLL_INTERVAL_SEC,
  timeout: float = _DEFAULT_GENERATE_TIMEOUT_SEC,  # noqa: ASYNC109 — poll deadline; see _await_result
) -> dict[str, Any]:
  """Enqueue ``generate_chat_response_job`` and return the raw dict.

  Used by the tool-calling path's 2nd LLM invocation: after tools have
  executed, we hand the worker the assistant message + tool-role
  results and let it produce a natural-language answer.

  Args:
      messages: Chronological message list for the LLM. Expected to
          include the original user turn, the Router's assistant
          message (with ``tool_calls``), and one ``role="tool"`` entry
          per executed call keyed by ``tool_call_id``.
      queue: ``rq.Queue`` instance or duck-typed stub.
      system_prompt: Optional prompt prefix; passed through to the job.
      poll_interval: Seconds between status polls.
      timeout: Max wait in seconds.

  Returns:
      ``{"answer": str, "token_usage": dict | None}`` — kept as a raw
      dict rather than a DTO so the service layer can embed it in
      ``ChatMessage.metadata`` without an extra conversion.

  Raises:
      ToolTimeoutError: Polling deadline exceeded.
      ToolJobError: Worker returned a failed status.
  """
  logger.info("[ToolCalling] enqueue generate_chat_response_job messages=%d", len(messages))
  job = queue.enqueue(GENERATE_CHAT_RESPONSE_JOB_REF, messages, system_prompt)
  return await _await_result(job, poll_interval=poll_interval, timeout=timeout)

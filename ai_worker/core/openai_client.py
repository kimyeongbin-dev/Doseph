"""AsyncOpenAI 싱글톤.

ai-worker 프로세스 안에서 OpenAI 클라이언트는 단 하나만 인스턴스화한다.
RAG 응답 생성, 쿼리 재작성, 세션 요약, Router LLM 모두 본 모듈의
``get_openai_client()`` 를 통해 같은 클라이언트를 공유해야 한다.

이렇게 하면:
- 매 요청마다 클라이언트 할당 + 커넥션 풀 재구성 비용을 0 에 가깝게 유지
- API 키 누락 처리를 한 곳에서만 수행 (``api_key`` 부재 시 ``None`` 반환)
- 도메인 모듈이 ``openai`` 패키지를 직접 import 하지 않아 결합도 ↓
"""

import logging

from openai import AsyncOpenAI

from ai_worker.core.config import config

logger = logging.getLogger(__name__)


_client: AsyncOpenAI | None = None
_initialised: bool = False


def get_openai_client() -> AsyncOpenAI | None:
  """프로세스 전역 AsyncOpenAI 클라이언트를 반환한다.

  Returns:
      설정된 ``OPENAI_API_KEY`` 가 있으면 AsyncOpenAI 인스턴스,
      없으면 ``None`` (호출자가 fallback 처리).
  """
  global _client, _initialised

  if _initialised:
    return _client

  api_key = config.OPENAI_API_KEY
  if not api_key:
    logger.warning("OPENAI_API_KEY 미설정 — AsyncOpenAI 클라이언트 비활성")
    _initialised = True
    return None

  _client = AsyncOpenAI(api_key=api_key)
  _initialised = True
  logger.info("AsyncOpenAI 클라이언트 초기화 완료")
  return _client

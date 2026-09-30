"""AI Worker logging — ``app.core.logger`` 에 위임.

부모 logger ("ai_worker") 만 file/console 핸들러를 가지며, 모듈별
``get_logger(__name__)`` 호출은 자식 logger 를 반환해 부모로 propagate.
모듈마다 별도 .log 파일이 생기는 디스크 폭증을 막기 위함.
"""

import logging

from app.core.logger import setup_logger

# Module-import 시점에 부모 logger 활성화 — file/console 핸들러 부착.
# fastapi 와 ai-worker 두 컨테이너 모두에서 import 되어 idempotent 하게 작동.
setup_logger("ai_worker")


def get_logger(name: str) -> logging.Logger:
  """모듈별 자식 logger — 부모 'ai_worker' 의 핸들러로 propagate.

  Args:
      name: 일반적으로 ``__name__`` (예: ``ai_worker.domains.lifestyle.jobs``).

  Returns:
      propagate=True 인 자식 logger (default). 자체 핸들러 없음.
  """
  return logging.getLogger(name)

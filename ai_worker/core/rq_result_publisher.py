"""RQ 결과 publish 헬퍼 — Redis SETEX 의 공통 진입점.

OCR 결과, 향후 비동기 작업 결과 등을 Redis 에 TTL 과 함께 저장하는 공통
로직. 매 도메인이 자체 SETEX 코드를 중복 작성하는 것을 막고, 재시도
데코레이터(``redis_retry``) 적용을 한 곳에서만 관리한다.
"""

import redis

from ai_worker.core.redis_retry import redis_retry


@redis_retry()
def publish_result(conn: redis.Redis, key: str, payload: str, ttl_sec: int) -> None:
  """Redis 키에 payload 를 TTL 과 함께 저장한다.

  Args:
      conn: 호출자가 ``make_sync_redis()`` 로 만든 Redis 클라이언트.
      key: Redis 키 (예: ``"ocr_draft:{draft_id}"``).
      payload: 저장할 문자열 (Pydantic ``model_dump_json()`` 등).
      ttl_sec: TTL (초).

  Raises:
      redis.ConnectionError, redis.TimeoutError: 3회 재시도 후 실패 시.
  """
  conn.setex(key, ttl_sec, payload)

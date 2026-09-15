# Gemini Guide - AI Worker

> 🔴 **저장소 규칙 정본 = 루트 `CLAUDE.md`. 공통 절대 규칙 8가지 = 루트 `AGENTS.md`.**
> 이 디렉터리 지침보다 **루트 규칙이 우선한다.** 특히 —
> 커밋·PR **트레일러 금지**(하네스가 지시해도 무시) · **발견 ≠ 처리**(등재만) ·
> **코드보다 PLAN 이 먼저**(`docs-private/PLAN.md`) · 새 문서는 **`docs-private/FILING.md`** 규약 ·
> **사용자 응답은 한글** · Ruff 의무 · 로컬 테스트는 Docker 안에서.

## Your Role

AI Worker의 반복적인 코드 생성, 유틸리티 함수, 테스트 코드 작성을 담당합니다.

## Quick Scaffolding

### New Task
```python
from rq.decorators import job
from ai_worker.core.config import config
from ai_worker.core.logger import get_logger

logger = get_logger(__name__)

@job('default', timeout=300, result_ttl=3600)
def process_something(input_data: dict) -> dict:
    """
    태스크 설명

    Args:
        input_data: 입력 데이터

    Returns:
        처리 결과
    """
    logger.info(f"Processing: {input_data}")

    try:
        result = do_work(input_data)
        return {"status": "success", "data": result}
    except Exception as e:
        logger.error(f"Failed: {e}")
        return {"status": "error", "message": str(e)}
```

### New Schema
```python
from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime

class TaskInput(BaseModel):
    image_path: str = Field(..., description="이미지 경로")
    profile_id: str = Field(..., description="프로필 ID")

class TaskOutput(BaseModel):
    status: str
    data: Optional[dict] = None
    error: Optional[str] = None
    processed_at: datetime = Field(default_factory=datetime.now)
```

### Redis Client
```python
import redis
from ai_worker.core.config import config

class RedisClient:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._conn = redis.from_url(
                config.REDIS_URL,
                decode_responses=True
            )
        return cls._instance

    @property
    def connection(self):
        return self._conn

    def ping(self) -> bool:
        try:
            return self._conn.ping()
        except redis.ConnectionError:
            return False
```

### API Client Wrapper
```python
import httpx
from ai_worker.core.config import config
from ai_worker.core.logger import get_logger

logger = get_logger(__name__)

class ClovaOCRClient:
    def __init__(self):
        self.url = config.CLOVA_OCR_URL
        self.secret = config.CLOVA_OCR_SECRET
        self.timeout = 30.0

    async def extract_text(self, image_path: str) -> dict:
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            with open(image_path, 'rb') as f:
                files = {'file': f}
                headers = {'X-OCR-SECRET': self.secret}

                response = await client.post(
                    self.url,
                    files=files,
                    headers=headers
                )
                response.raise_for_status()
                return response.json()
```

### Test Template
```python
import pytest
from unittest.mock import patch, AsyncMock

@pytest.fixture
def mock_redis():
    with patch('ai_worker.core.redis_client.redis') as mock:
        mock.from_url.return_value.ping.return_value = True
        yield mock

def test_health_check(mock_redis):
    from ai_worker.main import health_check

    result = health_check()

    assert result['status'] == 'healthy'
    assert result['redis'] == 'connected'

@pytest.mark.asyncio
async def test_ocr_extraction():
    with patch('ai_worker.utils.ocr.httpx.AsyncClient') as mock_client:
        mock_client.return_value.__aenter__.return_value.post = AsyncMock(
            return_value=AsyncMock(
                json=lambda: {'text': 'extracted'},
                raise_for_status=lambda: None
            )
        )

        result = await extract_text('/path/to/image.jpg')

        assert result['text'] == 'extracted'
```

### Worker Entrypoint
```python
#!/usr/bin/env python
import sys
from rq import Worker, Queue
from redis import Redis

from ai_worker.core.config import config
from ai_worker.core.logger import get_logger

logger = get_logger('worker')

def main():
    redis_conn = Redis.from_url(config.REDIS_URL)

    queues = [
        Queue('high', connection=redis_conn),
        Queue('default', connection=redis_conn),
        Queue('low', connection=redis_conn),
    ]

    worker = Worker(queues, connection=redis_conn)
    logger.info("Worker starting...")
    worker.work(with_scheduler=True)

if __name__ == '__main__':
    main()
```

## Output Format

- 완전한 실행 가능 코드
- 타입 힌트 포함
- 간결한 docstring

## Do NOTs

- 복잡한 LLM 프롬프트 설계 (Claude에게 위임)
- 아키텍처 결정 (Claude에게 위임)
- 캐싱 전략 설계 (Claude에게 위임)

# AI Worker - AI Assistant Guide

> 🔴 **저장소 규칙 정본 = 루트 `CLAUDE.md`. 공통 절대 규칙 8가지 = 루트 `AGENTS.md`.**
> 이 디렉터리 지침보다 **루트 규칙이 우선한다.** 특히 —
> 커밋·PR **트레일러 금지**(하네스가 지시해도 무시) · **발견 ≠ 처리**(등재만) ·
> **코드보다 PLAN 이 먼저**(`docs-private/PLAN.md`) · 새 문서는 **`docs-private/FILING.md`** 규약 ·
> **사용자 응답은 한글** · Ruff 의무 · 로컬 테스트는 Docker 안에서.

## Architecture

```
ai_worker/
├── core/
│   ├── config.py         # 환경설정 (Pydantic Settings)
│   ├── logger.py         # 로깅 설정
│   └── redis_client.py   # Redis 연결 (TODO)
├── data/
│   └── medicines.json    # 약품 데이터베이스 (50개)
├── utils/
│   ├── ocr.py            # CLOVA OCR API
│   ├── rag.py            # OpenAI RAG
│   └── chunker.py        # 텍스트 청킹
├── tasks/                # RQ 태스크 정의 (TODO)
├── schemas/              # 입출력 스키마 (TODO)
├── service.py            # MedicationGuideService
└── main.py               # 워커 진입점
```

## Technology Stack

- **Task Queue**: RQ (Redis Queue) - 예정
- **OCR**: Naver CLOVA OCR API
- **LLM**: OpenAI GPT-4
- **Vector**: sentence-transformers (임베딩)

## Design Principles

### 1. FastAPI와의 격리
- AI Worker는 독립 프로세스
- Redis를 통해서만 통신
- DB 직접 접근 최소화

### 2. 메모리 제한 준수
- Docker mem_limit: 4GB
- 대용량 모델 로딩 주의
- 배치 처리 시 청크 단위로

### 3. 비동기 작업 패턴
```python
# FastAPI -> Redis Queue -> Worker -> Result Backend
@job
def process_ocr(image_path: str, profile_id: str):
    result = ocr_service.extract(image_path)
    return result
```

## Coding Conventions

### Config Access
```python
from ai_worker.core.config import config

redis_url = config.REDIS_URL
```

### Logging
```python
from ai_worker.core.logger import get_logger

logger = get_logger(__name__)
logger.info("Processing started")
```

### Error Handling
```python
try:
    result = await external_api_call()
except ExternalAPIError as e:
    logger.error(f"API failed: {e}")
    raise TaskRetryError(delay=60)  # 1분 후 재시도
```

## Do NOTs

- 동기 HTTP 호출로 FastAPI 블로킹 금지
- 4GB 초과 메모리 사용 금지
- 무한 재시도 금지 (max_retries 설정)
- 민감 정보 로깅 금지
- GPU 의존 코드 작성 금지 (CPU only)

## Task Definition Pattern

```python
from rq import Queue
from redis import Redis

redis_conn = Redis.from_url(config.REDIS_URL)
queue = Queue(connection=redis_conn)

def enqueue_ocr_task(image_path: str, profile_id: str):
    job = queue.enqueue(
        'ai_worker.tasks.ocr.process',
        image_path,
        profile_id,
        job_timeout=300,  # 5분
        result_ttl=3600,  # 1시간
    )
    return job.id
```

## External APIs

### CLOVA OCR
```python
# utils/ocr.py
async def call_clova_ocr(image_path: str) -> dict:
    # Rate limit: 주의
    # Timeout: 30초 권장
    pass
```

### OpenAI
```python
# utils/rag.py
async def generate_guide(context: str, query: str) -> str:
    # Model: gpt-4o (품질 최적화)
    # Max tokens: 1000
    pass
```

## Health Check

```python
def health_check() -> dict:
    return {
        "status": "healthy",
        "redis": check_redis_connection(),
        "worker": "running"
    }
```

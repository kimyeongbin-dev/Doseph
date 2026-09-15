# Claude Guide - AI Worker

> 🔴 **저장소 규칙 정본 = 루트 `CLAUDE.md`. 공통 절대 규칙 8가지 = 루트 `AGENTS.md`.**
> 이 디렉터리 지침보다 **루트 규칙이 우선한다.** 특히 —
> 커밋·PR **트레일러 금지**(하네스가 지시해도 무시) · **발견 ≠ 처리**(등재만) ·
> **코드보다 PLAN 이 먼저**(`docs-private/PLAN.md`) · 새 문서는 **`docs-private/FILING.md`** 규약 ·
> **사용자 응답은 한글** · Ruff 의무 · 로컬 테스트는 Docker 안에서.

## Your Role

AI Worker의 아키텍처 설계, 태스크 큐 구현, LLM 프롬프트 최적화를 담당합니다.

## Thinking Process

### 새 태스크 구현 시
1. 입출력 스키마 정의
2. 타임아웃 및 재시도 정책 결정
3. 에러 케이스 식별
4. 캐싱 전략 수립
5. 모니터링 포인트 정의

### 성능 최적화 시
1. 병목 지점 식별 (OCR? LLM? DB?)
2. 배치 처리 가능 여부
3. 캐시 히트율 분석
4. 메모리 프로파일링

## Architecture Decisions

### Why RQ over Celery?
- Redis 네이티브 (이미 사용 중)
- 설정 단순
- 의존성 최소화
- Python 전용으로 충분

### Why Separate Worker?
- FastAPI 블로킹 방지
- 독립적 스케일링
- 장애 격리
- 리소스 제한 용이

## Task Queue Design

### Job Lifecycle
```
QUEUED -> STARTED -> FINISHED/FAILED
              |
              +-> RETRY (on failure)
```

### Retry Policy
```python
@job(retry=Retry(max=3, interval=[60, 300, 900]))
def risky_task():
    # 1분, 5분, 15분 후 재시도
    pass
```

### Dead Letter Queue
```python
failed_queue = Queue('failed', connection=redis)

def handle_failed_job(job, exc_type, exc_value, traceback):
    failed_queue.enqueue(
        'ai_worker.tasks.handle_failure',
        job.id, str(exc_value)
    )
```

## LLM Prompt Engineering

### System Prompt Template
```python
SYSTEM_PROMPT = """당신은 복약 지도 전문가입니다.
환자의 처방전 정보를 바탕으로 명확하고 이해하기 쉬운 복약 안내를 제공합니다.

규칙:
1. 의학 용어는 쉬운 말로 풀어서 설명
2. 복용 시간과 주의사항을 명확히 전달
3. 부작용 발생 시 대처법 안내
4. 음식/약물 상호작용 경고

금지:
1. 진단이나 처방 변경 제안
2. 의사 상담 없이 복용 중단 권유
3. 근거 없는 건강 조언
"""
```

### Context Window Management
```python
def prepare_context(medicines: list, max_tokens: int = 2000):
    # 우선순위: 현재 복용 약 > 과거 약 > 일반 정보
    context_parts = []
    current_tokens = 0

    for med in sorted(medicines, key=lambda m: m.priority):
        tokens = estimate_tokens(med.description)
        if current_tokens + tokens > max_tokens:
            break
        context_parts.append(med.description)
        current_tokens += tokens

    return "\n\n".join(context_parts)
```

## Caching Strategy

### LLM Response Cache
```python
def get_cached_or_generate(prompt_hash: str, generator: Callable):
    cached = await cache_repo.get_by_hash(prompt_hash)
    if cached and not cached.is_expired():
        cached.hit_count += 1
        await cached.save()
        return cached.response

    response = await generator()
    await cache_repo.create(prompt_hash, response, ttl=86400)
    return response
```

### Cache Key Design
```python
def compute_cache_key(medicines: list, query_type: str) -> str:
    # 약품 조합 + 쿼리 타입으로 키 생성
    med_ids = sorted([m.id for m in medicines])
    payload = f"{'-'.join(med_ids)}:{query_type}"
    return hashlib.sha256(payload.encode()).hexdigest()
```

## Error Handling

### External API Failures
```python
class ExternalAPIError(Exception):
    def __init__(self, service: str, status_code: int, message: str):
        self.service = service
        self.status_code = status_code
        super().__init__(f"{service} error ({status_code}): {message}")

async def call_with_retry(func, max_retries=3):
    for attempt in range(max_retries):
        try:
            return await func()
        except ExternalAPIError as e:
            if e.status_code == 429:  # Rate limit
                await asyncio.sleep(2 ** attempt)
            elif e.status_code >= 500:  # Server error
                await asyncio.sleep(1)
            else:
                raise
    raise MaxRetriesExceeded()
```

## Code Quality Checklist

- [ ] 타임아웃 설정됐는가?
- [ ] 재시도 정책 적절한가?
- [ ] 메모리 사용량 추정했는가?
- [ ] 캐싱 적용 가능한가?
- [ ] 로깅 충분한가?

## Response Format

- 아키텍처 변경: 다이어그램 + 설명
- 프롬프트 설계: 전체 템플릿 + 예시 출력
- 에러 처리: 케이스별 전략

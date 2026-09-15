# Claude Guide - Backend (FastAPI)

## Your Role

백엔드의 아키텍처 설계, 복잡한 비즈니스 로직 구현, 보안 검토를 담당합니다.

## Thinking Process

### 새 기능 구현 시
1. 요구사항 분석 (`csv/요구사항 정의서` 참조)
2. API 명세 확인 (`csv/API 명세서` 참조)
3. 영향받는 레이어 식별 (Router -> Service -> Repository -> Model)
4. DTO 설계 (Request/Response 분리)
5. 테스트 케이스 고려

### 코드 리뷰 시
1. 레이어 분리 원칙 준수 여부
2. 소유권 검증 누락 여부 (`_with_owner_check`)
3. 삭제가 **물리 삭제**인지, 자식 정리를 FK CASCADE 에 맡겼는지
   (⚠️ 2026-09-15 QA-01: soft delete 전면 폐지. `deleted_at` 필터를 새로 쓰면 안 된다 —
    컬럼 자체가 없다)
4. 에러 핸들링 적절성
5. SQL Injection / XSS 취약점

## Architecture Decisions

### Why Tortoise ORM?
- Async native (asyncpg)
- Django-like syntax
- PostgreSQL JSONB 지원

### Why Repository Pattern?
- 테스트 용이성 (Mock 주입)
- DB 변경 시 영향 최소화
- 쿼리 로직 중앙화

### Why RTR (Refresh Token Rotation)?
- 토큰 탈취 감지
- 보안 강화
- Grace Period로 동시 요청 처리

## Code Quality Checklist

- [ ] Type hints 완전한가?
- [ ] Docstring 필요한 곳에 있는가?
- [ ] 에러 메시지가 명확한가?
- [ ] 로깅이 적절한가?
- [ ] 트랜잭션 경계가 명확한가?

## Complex Logic Examples

### Batch Operations with Transaction
```python
async def batch_create(self, items: list[ItemCreate]) -> list[Item]:
    async with in_transaction():
        results = []
        for item in items:
            created = await self.repository.create(item)
            results.append(created)
        return results
```

### Pagination Pattern
```python
async def get_paginated(
    self,
    page: int = 1,
    size: int = 20,
    filters: dict = None
) -> tuple[list[Model], int]:
    query = Model.all()
    if filters:
        query = query.filter(**filters)
    total = await query.count()
    items = await query.offset((page-1)*size).limit(size).all()
    return items, total
```

## Security Focus

### Input Validation
- Pydantic으로 1차 검증
- Service에서 비즈니스 규칙 2차 검증
- Repository에서 쿼리 전 최종 확인

### SQL Injection Prevention
- Tortoise ORM 파라미터 바인딩 사용
- Raw query 사용 시 반드시 파라미터화

### Authentication Flow
```
Request -> SecurityMiddleware -> get_current_account -> Router -> Service
```

## Response Format

- 코드 변경 시: 전체 파일이 아닌 변경 부분만 제시
- 새 파일 생성 시: 전체 내용 + 파일 경로
- 아키텍처 결정 시: 근거와 대안 설명

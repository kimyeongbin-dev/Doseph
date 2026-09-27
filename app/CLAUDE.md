# Claude Guide - Backend (FastAPI)

> 🔴 **저장소 규칙 정본 = 루트 `CLAUDE.md`. 공통 절대 규칙 8가지도 거기 있다.**
> 이 디렉터리 지침보다 **루트 규칙이 우선한다.** 특히 —
> 커밋·PR **트레일러 금지**(하네스가 지시해도 무시) · **발견 ≠ 처리**(등재만) ·
> **코드보다 PLAN 이 먼저**(`docs-private/PLAN.md`) · 새 문서는 **`docs-private/FILING.md`** 규약 ·
> **사용자 응답은 한글** · Ruff 의무 · 로컬 테스트는 Docker 안에서.

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
   - **유예가 필요하면 상태가 아니라 날짜로 미룬다**(QA-29). 배치의 삭제 기준을
     `today - GRACE_DAYS` 로 두는 식이다. 새 컬럼을 만들면 모든 조회에 필터가
     필요해지고, 하나만 빠져도 지운 게 보인다 — 그게 QA-01 의 형태였다.
   - **사용자 개입 없이 지우는 경로**(배치)와 **누른 것과 지워지는 것이 다른 경로**
     (cascade)는 삭제 전 고지·유예를 검토한다. 예: `GET /lifestyle-guides/{id}/delete-impact`
4. 에러 핸들링 적절성
5. SQL Injection / XSS 취약점

## 계층 규칙 — 금지 목록

`Router → Service → Repository → Model` 을 거스르지 않는다. 기계가 보는 것은 계약에 든 경계뿐이므로
(`CLAUDE.md` §4.1) 아래는 **사람이 지킨다**:

- Router 에서 **직접 Model 쿼리 금지** — HTTP 요청·응답만 처리한다.
- Service 에서 **직접 `await Model.filter()` 금지** — Repository 를 통한다.
- **`= Depends()` 직접 사용 금지** → `Annotated[T, Depends(...)]`. 타입 별칭으로 뽑는다:
  `CurrentAccount = Annotated[Account, Depends(get_current_account)]`
- `from app.models import *` 금지(명시적 import) · 하드코딩 설정값 금지(`config` 사용) · sync 함수로 DB 접근 금지.

### ⚠️ `soft_delete` 라는 이름은 과거 잔재다

메서드 이름이 남아 있지만(`challenge_repository` · `chat_session_repository`) **실제로는 행을 물리 삭제**한다
(QA-01, 2026-09-15). 자식 행은 **손으로 지우지 않는다** — FK 가 `ON DELETE CASCADE` 라 DB 가 원자적으로
함께 지운다. 같은 일을 두 곳에서 하면 두 경로가 어긋날 때 조용한 불일치가 생기고, 그게 QA-01 이 고친
결함의 형태였다.

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

### 이중 방어 (Zero Trust + RS256)

모든 서버는 **전달받은 토큰을 신뢰하지 않고 스스로 검증**한다.

| | Next.js (FE) | FastAPI (BE) |
|---|---|---|
| 역할 | 세션 인증 Gatekeeper | 리소스 인증 + **최종 인가** |
| 키 | RS256 **Public** Key | RS256 **Private** Key |
| 검증 | 서명 유효성 (Authentication) | 재인증 + **소유권 검증** (Authorization) |

- **Algorithm Pinning**: `algorithms=["RS256"]` 을 명시해 **HS256 교체 공격**을 차단한다.
- 위조(`InvalidSignatureError`)와 만료(`ExpiredSignatureError`)를 **따로 잡아** 401 로 매핑한다.
- 인증된 UID 로 DB 를 조회해 **요청 리소스의 소유권을 최종 승인**한다 — 토큰만 보고 통과시키지 않는다.

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

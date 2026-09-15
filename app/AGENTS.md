# Backend (FastAPI) - AI Assistant Guide

> 🔴 **저장소 규칙 정본 = 루트 `CLAUDE.md`. 공통 절대 규칙 8가지 = 루트 `AGENTS.md`.**
> 이 디렉터리 지침보다 **루트 규칙이 우선한다.** 특히 —
> 커밋·PR **트레일러 금지**(하네스가 지시해도 무시) · **발견 ≠ 처리**(등재만) ·
> **코드보다 PLAN 이 먼저**(`docs-private/PLAN.md`) · 새 문서는 **`docs-private/FILING.md`** 규약 ·
> **사용자 응답은 한글** · Ruff 의무 · 로컬 테스트는 Docker 안에서.

## Architecture

```
app/
├── apis/v1/          # Presentation Layer - HTTP 라우터
├── services/         # Application Layer - 비즈니스 로직
├── repositories/     # Infrastructure Layer - DB 접근
├── models/           # Domain Layer - Tortoise ORM 엔티티
├── dtos/             # Data Transfer Objects - Pydantic 스키마
├── dependencies/     # FastAPI 의존성 주입
├── validators/       # 도메인 검증 규칙
├── middlewares/      # HTTP 미들웨어
├── utils/            # 공통 유틸리티
├── core/             # 설정
└── db/               # 데이터베이스 설정
```

## Security Architecture (Zero Trust + RS256)

### 이중 방어 체계 (Dual Defense System)

모든 서버는 전달받은 토큰을 신뢰하지 않고 스스로 검증해야 합니다.

| 항목 | Next.js (Frontend) | FastAPI (Backend) |
|------|-------------------|-------------------|
| **역할** | 세션 인증 Gatekeeper | 리소스 인증 + 최종 인가 |
| **책임** | UI 자산 보호, 입장 통제 | 데이터 무결성, 최후의 보루 |
| **키 유형** | RS256 Public Key | RS256 Private Key |
| **검증 수준** | 서명 유효성 (Authentication) | 재인증 + 소유권 검증 (Authorization) |

### FastAPI 보안 책임

1. **토큰 검증 (Token Validation)** - 매 요청마다 수행
   - **위조 판별 (Signature Verification)**: RS256 서명 검증으로 토큰 변조 탐지
   - **만료 검증 (Expiration Check)**: `exp` 클레임 확인으로 만료된 토큰 거부
   - **Algorithm Pinning**: `algorithms=['RS256']` 고정으로 알고리즘 교체 공격 차단

2. **최종 인가 (Final Authorization)**
   - 인증된 UID로 DB 조회
   - 요청 리소스에 대한 소유권/접근 권한 최종 승인

### 핵심 보안 키워드

- **RS256**: 비대칭 키 알고리즘 (Private Key 서명, Public Key 검증)
- **HttpOnly Cookie**: XSS 공격으로부터 토큰 보호
- **Zero Trust**: 모든 요청을 의심, 매번 검증
- **Algorithm Pinning**: `algorithms=['RS256']` 명시로 HS256 교체 공격 차단

## Layered Architecture Rules

### 1. Router (apis/v1/)
- HTTP 요청/응답만 처리
- 비즈니스 로직 금지
- **Annotated 패턴으로 의존성 주입** (Ruff UP 규칙 준수)

```python
from typing import Annotated
from fastapi import Depends

# 타입 별칭 정의 (dependencies/ 또는 각 라우터 상단)
CurrentAccount = Annotated[Account, Depends(get_current_account)]
ItemServiceDep = Annotated[ItemService, Depends(get_item_service)]

@router.post("/")
async def create_item(
    data: ItemCreate,
    service: ItemServiceDep,
    account: CurrentAccount,
):
    return await service.create_with_owner_check(data, account.id)
```

### 2. Service (services/)
- 비즈니스 로직 캡슐화
- Repository를 통해서만 DB 접근
- `_with_owner_check` 패턴으로 권한 검증

```python
class ItemService:
    def __init__(self):
        self.repository = ItemRepository()

    async def create_with_owner_check(self, data, account_id):
        await self._verify_ownership(data.profile_id, account_id)
        return await self.repository.create(data)
```

### 3. Repository (repositories/)
- DB CRUD 추상화
- 삭제는 **물리 삭제** — 자식 정리는 FK `ON DELETE CASCADE` 에 맡긴다
- 복잡한 쿼리 캡슐화

```python
async def get_by_id(self, id: UUID) -> Model | None:
    return await Model.filter(id=id).first()
```

### 4. Model (models/)
- Tortoise ORM 엔티티
- 비즈니스 엔티티: UUID PK
- 캐시/토큰: BigInt PK
- ⚠️ 2026-09-15(QA-01): `deleted_at` 컬럼은 **전 테이블에서 제거**됐다. 새로 만들지 말 것

### 5. DTO (dtos/)
- Pydantic v2 스키마
- Request/Response 분리
- `model_config = ConfigDict(from_attributes=True)`

## Coding Conventions

### Import Order & Path
```python
# 1. Standard library
from typing import Annotated
from uuid import UUID

# 2. Third-party packages
from fastapi import APIRouter, Depends, HTTPException

# 3. Local imports (절대 경로)
from app.models.account import Account
from app.services.item_service import ItemService
from app.dependencies.auth import get_current_account
```

### Annotated Type Aliases

```python
# app/dependencies/common.py 또는 각 모듈 상단
from typing import Annotated
from fastapi import Depends

from app.models.account import Account
from app.dependencies.auth import get_current_account

# 타입 별칭 정의
CurrentAccount = Annotated[Account, Depends(get_current_account)]
```

### Async/Await
- 모든 DB 작업은 async
- 외부 API 호출도 async (httpx)

### Error Handling
- 401: 미인증 (토큰 없음 / 만료 / 위조)
- 403: 권한 부족 / 소유권 없음
- 404: 리소스 없음
- 422: 유효성 검사 실패

### Naming
```python
# Router
router = APIRouter(prefix="/items", tags=["Items"])

# Service method
async def get_items_by_account(self, account_id: UUID)

# Repository method
async def get_all_by_profile(self, profile_id: UUID)
```

## Do NOTs

- Router에서 직접 Model 쿼리 금지
- Service에서 직접 `await Model.filter()` 금지
- `from app.models import *` 금지 (명시적 import)
- 하드코딩된 설정값 금지 (config 사용)
- sync 함수로 DB 접근 금지
- **`= Depends()` 직접 사용 금지** -> `Annotated[T, Depends()]` 사용

## Key Patterns

### Ownership Validation
```python
async def _verify_profile_ownership(self, profile_id: UUID, account_id: UUID):
    profile = await self.profile_repo.get_by_id(profile_id)
    if not profile or profile.account_id != account_id:
        raise HTTPException(status_code=403, detail="Access denied")
```

### 삭제 (hard delete + FK CASCADE)
```python
async def soft_delete(self, item: Model) -> None:
    """⚠️ 이름은 과거 잔재 — 실제로는 행을 **물리 삭제**한다 (QA-01, 2026-09-15).

    자식 행은 손으로 지우지 않는다. FK 가 ``ON DELETE CASCADE`` 라 DB 가
    원자적으로 함께 지운다. 같은 일을 두 곳에서 하면 두 경로가 어긋날 때
    조용한 불일치가 생긴다 — 그게 QA-01 이 고친 결함의 형태였다.
    """
    await item.delete()
```

### JWT 검증 (RS256) - 위조 + 만료 판별
```python
import jwt
from jwt.exceptions import ExpiredSignatureError, InvalidSignatureError
from fastapi import HTTPException
from app.core.config import settings

def verify_token(token: str) -> dict:
    """
    JWT 토큰 검증 - 위조 및 만료 모두 확인

    검증 항목:
    1. 서명 위조 판별 (Signature Verification)
    2. 만료 시간 검증 (Expiration Check)
    3. 알고리즘 고정 (Algorithm Pinning)
    """
    try:
        return jwt.decode(
            token,
            settings.JWT_PUBLIC_KEY,
            algorithms=["RS256"],  # Algorithm Pinning - HS256 교체 공격 차단
        )
    except InvalidSignatureError:
        # 위조된 토큰 (서명 불일치)
        raise HTTPException(status_code=401, detail="Invalid token signature")
    except ExpiredSignatureError:
        # 만료된 토큰
        raise HTTPException(status_code=401, detail="Token has expired")
```

## Testing

```bash
# 테스트 실행
uv run pytest

# 커버리지
uv run pytest --cov=app
```

## Migration from Depends() to Annotated

기존 코드:
```python
# OLD - 사용 금지
async def endpoint(service: ItemService = Depends(get_item_service)):
    ...
```

변경 후:
```python
# NEW - 이 패턴 사용
ItemServiceDep = Annotated[ItemService, Depends(get_item_service)]

async def endpoint(service: ItemServiceDep):
    ...
```

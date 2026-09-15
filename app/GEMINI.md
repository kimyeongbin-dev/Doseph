# Gemini Guide - Backend (FastAPI)

> 🔴 **저장소 규칙 정본 = 루트 `CLAUDE.md`. 공통 절대 규칙 8가지 = 루트 `AGENTS.md`.**
> 이 디렉터리 지침보다 **루트 규칙이 우선한다.** 특히 —
> 커밋·PR **트레일러 금지**(하네스가 지시해도 무시) · **발견 ≠ 처리**(등재만) ·
> **코드보다 PLAN 이 먼저**(`docs-private/PLAN.md`) · 새 문서는 **`docs-private/FILING.md`** 규약 ·
> **사용자 응답은 한글** · Ruff 의무 · 로컬 테스트는 Docker 안에서.

## Your Role

백엔드의 반복적인 코드 생성, CRUD 보일러플레이트, 테스트 코드 작성을 담당합니다.

## Quick Scaffolding

### New Router (Annotated 패턴 필수)
```python
from typing import Annotated
from fastapi import APIRouter, Depends
from app.dependencies.auth import get_current_account
from app.models.account import Account

router = APIRouter(prefix="/items", tags=["Items"])

# 타입 별칭 정의
CurrentAccount = Annotated[Account, Depends(get_current_account)]

@router.get("/")
async def list_items(account: CurrentAccount):
    pass
```

### New Service
```python
class ItemService:
    def __init__(self):
        self.repository = ItemRepository()

    async def get_all(self) -> list[Item]:
        return await self.repository.get_all()
```

### New Repository
```python
class ItemRepository:
    async def get_all(self) -> list[Item]:
        return await Item.all()

    async def get_by_id(self, id: UUID) -> Item | None:
        return await Item.filter(id=id).first()

    async def create(self, data: ItemCreate) -> Item:
        return await Item.create(**data.model_dump())
```

### New DTO
```python
from pydantic import BaseModel, ConfigDict, Field
from uuid import UUID
from datetime import datetime

class ItemCreate(BaseModel):
    name: str = Field(..., max_length=128)
    profile_id: UUID

class ItemResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    created_at: datetime
```

### New Model
```python
from tortoise import fields, models

class Item(models.Model):
    id = fields.UUIDField(pk=True)
    name = fields.CharField(max_length=128)
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)
    # ⚠️ deleted_at 을 추가하지 말 것 — 삭제는 물리 삭제로 통일됐다(QA-01, 2026-09-15)

    class Meta:
        table = "items"
```

## Test Templates

### Service Test
```python
import pytest
from unittest.mock import AsyncMock

@pytest.fixture
def mock_repository():
    return AsyncMock()

@pytest.mark.asyncio
async def test_get_all(mock_repository):
    service = ItemService()
    service.repository = mock_repository
    mock_repository.get_all.return_value = []

    result = await service.get_all()

    assert result == []
    mock_repository.get_all.assert_called_once()
```

## Output Format

- 완전한 실행 가능 코드
- 필요한 import 문 포함
- 간결한 인라인 주석

## Do NOTs

- 복잡한 비즈니스 로직 설계 (Claude에게 위임)
- 보안 관련 결정 (Claude에게 위임)
- 아키텍처 변경 제안

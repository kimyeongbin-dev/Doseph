"""Cascade 실패 경로 테스트 (mock 기반 — 남은 것은 이것뿐).

2026-09-15 이전에는 이 파일이 cascade 검증 **전부**였다. 리포지토리를 통째로
``AsyncMock`` 으로 바꿔 놓고 "그 메서드가 호출됐는가"만 보는 방식이라, 정책이
틀려도 호출 순서만 같으면 초록이었다(구현복사 테스트).

정책 자체는 이제 **진짜 행으로** 검증한다 → ``app/tests/db/test_db_cascade.py``.
여기 남은 것은 **실패 경로** 하나다. cascade 도중 예외가 나면 500 으로 변환되는지는
리포지토리가 실제로 터져야 확인되는데, 진짜 DB 로는 그 상황을 만들기 어렵다.
mock 이 여전히 적합한 자리라서 남긴다.
"""

from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

from fastapi import HTTPException
import pytest

from app.services.oauth import OAuthService


@asynccontextmanager
async def _fake_transaction():
    """in_transaction() 의 no-op stub — DB 연결 없이 동작."""
    yield None


# ── OAuthService.delete_account 실패 경로 ─────────────────────────────────
# 흐름: cascade 중 예외 발생 -> 트랜잭션 롤백 -> HTTPException 500 으로 변환
class TestAccountWithdrawalFailure:
    """회원탈퇴 cascade 도중 예외가 500 으로 변환되는지 검증."""

    def _build_oauth_service(self, account: MagicMock) -> OAuthService:
        service = OAuthService()
        service.account_repo = MagicMock()
        service.account_repo.delete = AsyncMock(return_value=None)
        return service

    @pytest.mark.asyncio
    async def test_delete_account_raises_500_on_failure(self) -> None:
        """cascade 도중 예외 → HTTPException 500 으로 변환."""
        account = MagicMock(id=uuid4())
        service = self._build_oauth_service(account)
        service.account_repo.delete = AsyncMock(side_effect=RuntimeError("boom"))

        # QA-01 S5: 탈퇴가 FK CASCADE 위임(단일 DELETE)으로 바뀌면서 서비스가
        # in_transaction 을 더는 쓰지 않는다 — 패치할 대상이 사라졌다.
        with pytest.raises(HTTPException) as exc:
            await service.delete_account(account)

        assert exc.value.status_code == 500
        assert exc.value.detail["error"] == "delete_failed"

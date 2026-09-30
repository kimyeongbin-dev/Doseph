"""LifestyleGuide — 활성 약물 부재 시 409 응답 단위 테스트.

배포 환경 회귀 가드:
    `POST /api/v1/lifestyle-guides/generate` 가 medications 0건일 때
    500 Internal Server Error 를 던지던 버그를 409 Conflict +
    구조화된 detail (code / message / redirect_to) 로 교체했다.
    FE 가 이 응답을 보고 토스트 + 라우팅을 한 번에 처리한다.

설계 결정 (PR #86 + #88 통합 → v3 처방전 단위):
    Service 가 직접 ``HTTPException(409, detail={...})`` 을 raise 하고,
    router 는 그대로 propagate 한다 (single source of truth).
    v3 부터 시그니처가 ``(profile_id, prescription_group_id)`` 로 변경 +
    NO_ACTIVE_MEDICATIONS 의 redirect_to 가 ``/medication`` 으로 변경
    (사용자가 그룹 안 약 등록을 확인하러 가야 하므로).
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

from fastapi import HTTPException, status
import pytest

from app.apis.v1.lifestyle_guide_routers import enqueue_guide
from app.services.lifestyle_guide_service import LifestyleGuideService


class TestServiceNoActiveMedications:
  """Service 단 — 활성 약물 부재 → 409 + 구조화된 detail."""

  def _service_with_empty_medications(self) -> tuple[LifestyleGuideService, Any, Any]:
    """active 0건 분기까지 도달하도록 prescription_group + medication mock.

    Returns:
        (service, profile_id, prescription_group_id) — 호출 측이 그대로 사용.
    """
    profile_id = uuid4()
    prescription_group_id = uuid4()

    # __init__ 우회 — RQ Queue 등 외부 의존성 instantiate 안 함.
    service = LifestyleGuideService.__new__(LifestyleGuideService)

    # prescription_group_repo: 그룹 owner 가 호출 profile_id 와 일치해야 통과.
    service.prescription_group_repo = MagicMock()
    service.prescription_group_repo.get_by_id = AsyncMock(
      return_value=MagicMock(id=prescription_group_id, profile_id=profile_id),
    )
    # medication_repo: 그룹 active 0건 → 본 분기 도달.
    service.medication_repo = MagicMock()
    service.medication_repo.get_active_by_prescription_group = AsyncMock(return_value=[])

    return service, profile_id, prescription_group_id

  @pytest.mark.asyncio
  async def test_raises_409_when_no_active_medications(self) -> None:
    """active medications 0건 → HTTPException(409)."""
    service, profile_id, group_id = self._service_with_empty_medications()

    with pytest.raises(HTTPException) as exc_info:
      await service.enqueue_guide_generation(
        profile_id=profile_id,
        prescription_group_id=group_id,
      )

    assert exc_info.value.status_code == status.HTTP_409_CONFLICT

  @pytest.mark.asyncio
  async def test_response_detail_has_required_keys(self) -> None:
    """detail 에 code / message / redirect_to 가 포함되어야 한다 (FE 계약)."""
    service, profile_id, group_id = self._service_with_empty_medications()

    with pytest.raises(HTTPException) as exc_info:
      await service.enqueue_guide_generation(
        profile_id=profile_id,
        prescription_group_id=group_id,
      )

    detail = exc_info.value.detail
    assert isinstance(detail, dict), f"detail must be dict, got {type(detail)}"
    assert detail["code"] == "NO_ACTIVE_MEDICATIONS"
    # v3: 메시지 카피와 redirect_to 가 처방전 페이지 기준으로 변경됨.
    assert "처방전" in detail["message"]
    assert detail["redirect_to"] == "/medication"


class TestEnqueueGuideHappyPath:
  """Router 단 happy path — service 가 guide 반환 시 그대로 반환."""

  @pytest.mark.asyncio
  async def test_returns_pending_response_on_success(self) -> None:
    guide_id = uuid4()
    service = MagicMock()
    # status 는 LifestyleGuidePendingResponse 의 enum 검증을 통과해야 한다.
    guide = MagicMock(id=guide_id, status="pending")
    service.enqueue_guide_with_owner_check = AsyncMock(return_value=guide)
    account = MagicMock(id=uuid4())

    result: Any = await enqueue_guide(
      profile_id=uuid4(),
      prescription_group_id=uuid4(),
      current_account=account,
      service=service,
    )

    assert result.id == guide_id
    assert result.status == "pending"

  @pytest.mark.asyncio
  async def test_returns_ready_status_on_dedupe_hit(self) -> None:
    """Phase B dedupe — service 가 ready 가이드 반환 시 status='ready' 응답."""
    guide_id = uuid4()
    service = MagicMock()
    guide = MagicMock(id=guide_id, status="ready")
    service.enqueue_guide_with_owner_check = AsyncMock(return_value=guide)
    account = MagicMock(id=uuid4())

    result: Any = await enqueue_guide(
      profile_id=uuid4(),
      prescription_group_id=uuid4(),
      current_account=account,
      service=service,
    )

    assert result.id == guide_id
    assert result.status == "ready"

  @pytest.mark.asyncio
  async def test_propagates_service_http_exception(self) -> None:
    """Service 가 던진 HTTPException 은 router 가 그대로 propagate."""
    service = MagicMock()
    service.enqueue_guide_with_owner_check = AsyncMock(
      side_effect=HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail={"code": "NO_ACTIVE_MEDICATIONS", "message": "...", "redirect_to": "/medication"},
      ),
    )
    account = MagicMock(id=uuid4())

    with pytest.raises(HTTPException) as exc_info:
      await enqueue_guide(
        profile_id=uuid4(),
        prescription_group_id=uuid4(),
        current_account=account,
        service=service,
      )

    assert exc_info.value.status_code == status.HTTP_409_CONFLICT
    assert exc_info.value.detail["code"] == "NO_ACTIVE_MEDICATIONS"

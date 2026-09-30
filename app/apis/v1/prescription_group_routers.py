"""Prescription group API router — 카드 list + drill-down.

단계 2 의 ``/medication`` 페이지가 처방전 단위로 노출되도록 두 endpoint 만 제공:

1. ``GET /prescription-groups`` — 카드 list (정렬 + 검색 + 탭 결합)
2. ``GET /prescription-groups/{group_id}`` — 단일 그룹 drill-down (약 list 포함)
"""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, status

from app.dependencies.security import get_current_account
from app.dtos.prescription_group import (
  PrescriptionGroupCard,
  PrescriptionGroupDetail,
  PrescriptionGroupUpdate,
)
from app.models.accounts import Account
from app.services.prescription_group_service import PrescriptionGroupService

router = APIRouter(prefix="/prescription-groups", tags=["Prescription Groups"])


def get_prescription_group_service() -> PrescriptionGroupService:
  """PrescriptionGroupService 인스턴스 (DI)."""
  return PrescriptionGroupService()


PrescriptionGroupServiceDep = Annotated[PrescriptionGroupService, Depends(get_prescription_group_service)]
CurrentAccount = Annotated[Account, Depends(get_current_account)]


@router.get(
  "",
  response_model=list[PrescriptionGroupCard],
  summary="처방전 그룹 카드 list (선택 약품 검색)",
)
async def list_prescription_groups(
  profile_id: UUID,
  current_account: CurrentAccount,
  service: PrescriptionGroupServiceDep,
  search: str | None = None,
) -> list[PrescriptionGroupCard]:
  """처방전 카드 list — (선택) 약품 이름 검색.

  정렬 / 탭 필터는 BE 가 처리하지 않는다. FE 가 응답을 받아 사용자 의도에
  따라 derived 로 표시. BE 책임은 CRUD + 검색만 (사용자 합의 원칙).

  Args:
      profile_id: 조회 대상 프로필 UUID.
      current_account: 인증된 계정.
      service: PrescriptionGroupService 인스턴스.
      search: 약품 이름 검색 — 이 약을 포함하는 그룹만 반환.

  Returns:
      검색 적용된 처방전 카드 list (created_at desc).
  """
  return await service.list_groups_with_owner_check(
    profile_id,
    current_account.id,
    search=search,
  )


@router.get(
  "/{group_id}",
  response_model=PrescriptionGroupDetail,
  summary="처방전 그룹 drill-down (그룹 + 약 list)",
)
async def get_prescription_group(
  group_id: UUID,
  current_account: CurrentAccount,
  service: PrescriptionGroupServiceDep,
) -> PrescriptionGroupDetail:
  """단일 처방전 그룹 + 그 안의 medication list."""
  return await service.get_group_with_owner_check(group_id, current_account.id)


@router.patch(
  "/{group_id}",
  response_model=PrescriptionGroupDetail,
  summary="처방전 그룹 메타 부분 수정 (department)",
)
async def update_prescription_group(
  group_id: UUID,
  data: PrescriptionGroupUpdate,
  current_account: CurrentAccount,
  service: PrescriptionGroupServiceDep,
) -> PrescriptionGroupDetail:
  """그룹 메타 부분 수정 — 현재는 ``department`` 만 변경 가능."""
  return await service.update_group_with_owner_check(group_id, current_account.id, data)


@router.patch(
  "/{group_id}/complete",
  response_model=PrescriptionGroupDetail,
  summary="처방전 그룹 복용 완료 처리 (그룹 내 모든 medication 비활성)",
)
async def complete_prescription_group(
  group_id: UUID,
  current_account: CurrentAccount,
  service: PrescriptionGroupServiceDep,
) -> PrescriptionGroupDetail:
  """그룹 내 모든 medication 의 ``is_active=False`` 로 일괄 변경.

  이후 ``GET /prescription-groups`` 의 ``has_active_medication`` 이 자동
  False 가 되어 카드가 "복용 완료" 라벨 + 탭으로 분류된다.
  """
  return await service.mark_completed_with_owner_check(group_id, current_account.id)


@router.delete(
  "/{group_id}",
  status_code=status.HTTP_204_NO_CONTENT,
  summary="처방전 그룹 삭제 (그룹 + medication + 가이드 cascade)",
)
async def delete_prescription_group(
  group_id: UUID,
  current_account: CurrentAccount,
  service: PrescriptionGroupServiceDep,
) -> None:
  """그룹 + 그 안 medication + 그 프로필의 active 가이드 cascade 삭제."""
  await service.delete_group_with_owner_check(group_id, current_account.id)

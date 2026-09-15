"""Medication API router module.

This module contains HTTP endpoints for medication operations
including creating, reading, updating, and deleting medications.
"""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, status

from app.dependencies.security import get_current_account
from app.dtos.drug_info import DrugInfoResponse
from app.dtos.medication import (
    MedicationBulkDeleteRequest,
    MedicationBulkDeleteResponse,
    MedicationCreate,
    MedicationPrescriptionGroupDeleteRequest,
    MedicationResponse,
    MedicationUpdate,
    PrescriptionDateItem,
)
from app.models.accounts import Account
from app.services.medication_service import MedicationService

router = APIRouter(prefix="/medications", tags=["Medications"])


def get_medication_service() -> MedicationService:
    """Get medication service instance.

    Returns:
        MedicationService: Medication service instance.
    """
    return MedicationService()


# Type aliases for dependency injection
MedicationServiceDep = Annotated[MedicationService, Depends(get_medication_service)]
CurrentAccount = Annotated[Account, Depends(get_current_account)]


@router.post(
    "",
    response_model=MedicationResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register medication",
)
async def create_medication(
    data: MedicationCreate,
    current_account: CurrentAccount,
    service: MedicationServiceDep,
) -> MedicationResponse:
    """Register a new medication.

    Args:
        data: Medication creation data.
        current_account: Current authenticated account.
        service: Medication service instance.

    Returns:
        MedicationResponse: Created medication information.
    """
    medication = await service.create_medication_with_owner_check(data.profile_id, current_account.id, data)
    return MedicationResponse.model_validate(medication)


@router.get(
    "",
    response_model=list[MedicationResponse],
    summary="List medications",
)
async def list_medications(
    current_account: CurrentAccount,
    service: MedicationServiceDep,
    profile_id: UUID | None = None,
    active_only: bool = False,
    inactive_only: bool = False,
) -> list[MedicationResponse]:
    """List medications with optional filtering by profile.

    Args:
        current_account: Current authenticated account.
        service: Medication service instance.
        profile_id: Optional profile ID to filter by.
        active_only: Whether to return only active medications.
        inactive_only: Whether to return only inactive (completed/expired) medications.

    Returns:
        list[MedicationResponse]: List of medications.
    """
    if profile_id:
        # Verify profile ownership and retrieve medications
        if active_only:
            medications = await service.get_active_medications_with_owner_check(profile_id, current_account.id)
        elif inactive_only:
            medications = await service.get_inactive_medications_with_owner_check(profile_id, current_account.id)
        else:
            # ── §A.2.2: 전체 medication 조회 시 recall_status 첨부 ──
            # 흐름: service.list_medications_with_recall_status_* (batch lookup)
            #       -> 각 행을 MedicationResponse + recall_status 로 직렬화
            paired = await service.list_medications_with_recall_status_with_owner_check(profile_id, current_account.id)
            responses: list[MedicationResponse] = []
            for entry in paired:
                response = MedicationResponse.model_validate(entry.medication)
                response.recall_status = entry.recall_status
                responses.append(response)
            return responses
    else:
        # Retrieve medications for all profiles of the account
        medications = await service.get_medications_by_account(current_account.id)
    return [MedicationResponse.model_validate(med) for med in medications]


@router.get(
    "/prescription-dates",
    response_model=list[PrescriptionDateItem],
    summary="List prescription dates",
)
async def list_prescription_dates(
    profile_id: UUID,
    current_account: CurrentAccount,
    service: MedicationServiceDep,
) -> list[PrescriptionDateItem]:
    """Get prescription date summary grouped by date and department.

    Args:
        profile_id: Profile UUID to retrieve prescription dates for.
        current_account: Current authenticated account.
        service: Medication service instance.

    Returns:
        list[PrescriptionDateItem]: Prescription dates sorted by date descending.
    """
    return await service.get_prescription_dates_with_owner_check(profile_id, current_account.id)


@router.get(
    "/{medication_id}",
    response_model=MedicationResponse,
    summary="Get medication details",
)
async def get_medication(
    medication_id: UUID,
    current_account: CurrentAccount,
    service: MedicationServiceDep,
) -> MedicationResponse:
    """Get detailed information about a specific medication.

    Args:
        medication_id: Medication ID to retrieve.
        current_account: Current authenticated account.
        service: Medication service instance.

    Returns:
        MedicationResponse: Medication details.
    """
    medication = await service.get_medication_with_owner_check(medication_id, current_account.id)
    return MedicationResponse.model_validate(medication)


@router.patch(
    "/{medication_id}",
    response_model=MedicationResponse,
    summary="Update medication",
)
async def update_medication(
    medication_id: UUID,
    data: MedicationUpdate,
    current_account: CurrentAccount,
    service: MedicationServiceDep,
) -> MedicationResponse:
    """Update medication information.

    Args:
        medication_id: Medication ID to update.
        data: Medication update data.
        current_account: Current authenticated account.
        service: Medication service instance.

    Returns:
        MedicationResponse: Updated medication information.
    """
    medication = await service.update_medication_with_owner_check(medication_id, current_account.id, data)
    return MedicationResponse.model_validate(medication)


@router.get(
    "/{medication_id}/drug-info",
    response_model=DrugInfoResponse,
    summary="약품 정보 조회 (주의사항/부작용/상호작용)",
)
async def get_drug_info(
    medication_id: UUID,
    current_account: CurrentAccount,
    service: MedicationServiceDep,
) -> DrugInfoResponse:
    """식약처 마스터 DB(``MedicineInfo``) 검색 기반 약품 상세 정보(주의사항/부작용/상호작용).

    매칭 실패 또는 NULL 컬럼인 경우 빈 배열로 응답한다 (FE 가 "정보 없음" 표시).
    상호작용은 현재 별도 마스터 미수집 상태라 항상 빈 배열.
    """
    return await service.get_drug_info_with_owner_check(medication_id, current_account.id)


@router.delete(
    "/{medication_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete medication",
)
async def delete_medication(
    medication_id: UUID,
    current_account: CurrentAccount,
    service: MedicationServiceDep,
) -> None:
    """Delete a medication.

    Args:
        medication_id: Medication ID to delete.
        current_account: Current authenticated account.
        service: Medication service instance.
    """
    await service.delete_medication_with_owner_check(medication_id, current_account.id)


# ── DELETE /medications (bulk) ──────────────────────────────────────────
# 흐름: 본문 ids -> 계정 소유 프로필 scope -> 단일 DELETE (물리 삭제)
#       -> {deleted_count, skipped_ids} 반환 (200 OK)
@router.delete(
    "",
    response_model=MedicationBulkDeleteResponse,
    status_code=status.HTTP_200_OK,
    summary="Bulk delete medications",
)
async def bulk_delete_medications(
    request: MedicationBulkDeleteRequest,
    current_account: CurrentAccount,
    service: MedicationServiceDep,
) -> MedicationBulkDeleteResponse:
    """다건 medication 을 한 번에 삭제한다 (행을 물리 삭제).

    타인 소유·존재하지 않음·이미 삭제됨인 ids 는 ``skipped_ids`` 로 보고된다.
    부분 실패 없이 한 번의 DELETE 로 처리되어 일관성을 유지한다.

    Args:
        request: 삭제할 medication ID 목록 (1~100건).
        current_account: 인증된 계정.
        service: medication 서비스 인스턴스.

    Returns:
        ``MedicationBulkDeleteResponse`` — 처리된 개수 + 건너뛴 ids.
    """
    return await service.bulk_delete_with_owner_check(request.ids, current_account.id)


# ── POST /medications/prescription-group/delete ──────────────────────────
# 흐름: medication 그룹 물리 삭제 -> 그 프로필의 active 가이드 cascade
#       (가이드가 지워지면 그 챌린지도 FK CASCADE 로 함께 사라진다)
@router.post(
    "/prescription-group/delete",
    response_model=MedicationBulkDeleteResponse,
    status_code=status.HTTP_200_OK,
    summary="처방전 그룹 삭제 (medication + 가이드 + 챌린지 cascade)",
)
async def delete_prescription_group(
    request: MedicationPrescriptionGroupDeleteRequest,
    current_account: CurrentAccount,
    service: MedicationServiceDep,
) -> MedicationBulkDeleteResponse:
    """처방전 그룹 단위 삭제 — 약 + 가이드 + 챌린지 의미적 cascade.

    단건 약 삭제는 ``DELETE /medications`` 그대로 사용. 본 endpoint 는 처방전
    카드 자체가 사라지는 시나리오에서 호출되며, 그 프로필의 active
    lifestyle_guide 들도 함께 정리한다 (그 가이드의 챌린지도 함께 삭제된다).

    Args:
        request: medication ids + profile_id.
        current_account: 인증된 계정.
        service: medication 서비스 인스턴스.

    Returns:
        ``MedicationBulkDeleteResponse`` — medication 처리 결과.

    Raises:
        HTTPException: 404/403 if profile not found / not owned.
    """
    return await service.delete_prescription_group_with_owner_check(
        request.ids,
        request.profile_id,
        current_account.id,
    )

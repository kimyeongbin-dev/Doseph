"""Medication DTO models module.

This module contains data transfer objects for medication operations
including creation, updates, and response serialization.
"""

from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.dtos.recall import RecallAlertDTO, RecallStatusDTO


class PrescriptionDateItem(BaseModel):
    """Prescription date summary item for left navigation.

    Groups medications by dispensed date and department.
    """

    prescription_date: date = Field(..., description="Prescription dispensed date (falls back to start_date if absent)")
    department: str | None = Field(None, description="Prescribing department (e.g. 내과)")
    count: int = Field(..., description="Number of medications for this date and department")


class BaseMedication(BaseModel):
    """Base medication model with common fields.

    Provides shared fields for medication operations
    including dosage, schedule, and prescription information.
    """

    medicine_name: str = Field(..., max_length=128, description="약품명")
    department: str | None = Field(None, max_length=64, description="처방 진료과 (예: 내과)")
    category: str | None = Field(None, max_length=64, description="약품 분류 (예: 해열진통제)")
    dose_per_intake: str | None = Field(None, max_length=32, description="1회 복용량 (예: 1정, 5ml)")
    daily_intake_count: int | None = Field(None, description="1일 복용 횟수")
    total_intake_days: int | None = Field(None, description="총 복용 일수")
    intake_instruction: str | None = Field(None, max_length=256, description="복용 지시사항")
    intake_times: list[str] = Field(..., description="일일 복용 시간 목록 (예: ['08:00', '13:00'])")
    total_intake_count: int = Field(..., description="처방된 총 복용 횟수")
    remaining_intake_count: int | None = Field(None, description="남은 복용 횟수 (미입력 시 총 복용 횟수와 동일)")
    start_date: date = Field(..., description="복용 시작일")
    end_date: date | None = Field(None, description="복용 종료 예정일")
    dispensed_date: date | None = Field(None, description="약품 조제일")
    expiration_date: date | None = Field(None, description="약품 유효기간 만료일")
    is_active: bool = Field(True, description="현재 복용 중 여부")


class MedicationCreate(BaseMedication):
    """Medication creation request model.

    Used for creating new medications with profile association.
    """

    profile_id: UUID = Field(..., description="Connected profile ID")


class MedicationUpdate(BaseModel):
    """Medication update request model.

    Used for partial updates to existing medications.
    All fields are optional for flexible updates.
    """

    medicine_name: str | None = Field(None, max_length=128, description="약품명")
    department: str | None = Field(None, max_length=64, description="처방 진료과")
    category: str | None = Field(None, max_length=64, description="약품 분류")
    dose_per_intake: str | None = Field(None, max_length=32, description="1회 복용량")
    daily_intake_count: int | None = Field(None, description="1일 복용 횟수")
    total_intake_days: int | None = Field(None, description="총 복용 일수")
    intake_instruction: str | None = Field(None, max_length=256, description="복용 지시사항")
    intake_times: list[str] | None = Field(None, description="일일 복용 시간 목록")
    total_intake_count: int | None = Field(None, description="처방된 총 복용 횟수")
    remaining_intake_count: int | None = Field(None, description="남은 복용 횟수")
    start_date: date | None = Field(None, description="복용 시작일")
    end_date: date | None = Field(None, description="복용 종료 예정일")
    dispensed_date: date | None = Field(None, description="약품 조제일")
    expiration_date: date | None = Field(None, description="약품 유효기간 만료일")
    is_active: bool | None = Field(None, description="현재 복용 중 여부")


class MedicationResponse(BaseMedication):
    """Medication response model.

    Used for serializing medication data in API responses.
    Includes all medication fields and metadata.
    """

    model_config = ConfigDict(from_attributes=True)

    id: UUID = Field(..., description="Medication record ID")
    profile_id: UUID = Field(..., description="Connected profile ID")
    prescription_group_id: UUID | None = Field(
        None,
        description="소속 처방전 그룹 ID (단계 1 이전 row 는 NULL)",
    )
    created_at: datetime = Field(..., description="Creation timestamp")
    updated_at: datetime = Field(..., description="Last update timestamp")
    # 회수·판매중지 알림 페이로드 (Phase 7 §A.2.1·§A.2.2)
    # POST 응답: 등록 시점 모달 페이로드. GET 응답: 마이페이지 라벨 페이로드.
    # medication 객체에 attach 된 속성을 from_attributes 로 자동 매핑한다.
    # TODO(FE 후속 PR, yeoul98): mypage 행 옆 회수 칩 + OCR 등록 직후 회수 모달
    # 표시. 본 BE PR (#126) 머지 후 별도 FE PR 으로 추가 — 통합 머지 시점에는
    # FE 미활용 (데드 필드) 로 두되, 응답 형식은 확정.
    recall_alert: RecallAlertDTO | None = Field(
        None,
        description="등록 직후 1회 발화할 회수 모달 페이로드 (POST 응답 전용, FE 후속 PR 활용)",
    )
    recall_status: RecallStatusDTO | None = Field(
        None,
        description="마이페이지 medication 행 옆 라벨 페이로드 (GET 응답 전용, FE 후속 PR 활용)",
    )


class MedicationBulkDeleteRequest(BaseModel):
    """Bulk soft-delete request — 계정 소유 medication ids 묶음.

    타인 소유·이미 삭제·존재하지 않는 ids 는 응답의 ``skipped_ids`` 로 보고된다.
    """

    ids: list[UUID] = Field(..., min_length=1, max_length=100, description="삭제할 medication ID 목록")


class MedicationBulkDeleteResponse(BaseModel):
    """Bulk soft-delete 결과 — UI 토스트/안내용."""

    deleted_count: int = Field(..., description="실제 soft delete 처리된 개수")
    skipped_ids: list[UUID] = Field(
        default_factory=list,
        description="ownership/존재하지 않음/이미 삭제됨으로 건너뛴 ID",
    )


class MedicationPrescriptionGroupDeleteRequest(BaseModel):
    """처방전 그룹 단위 삭제 요청 — medication 들 + 가이드/챌린지 cascade.

    단건 medication 삭제와 다른 endpoint 로 분리. 본 요청은 그룹 전체가
    무효화됐다는 시그널로 가이드까지 함께 정리한다.
    """

    ids: list[UUID] = Field(..., min_length=1, max_length=100, description="처방전 그룹에 속한 medication ID 목록")
    profile_id: UUID = Field(..., description="그룹 소유 프로필 — cascade scope")

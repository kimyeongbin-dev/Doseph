"""Prescription group DTO models module.

BE 의 책임 원칙 (사용자 합의): **CRUD + 입력값 검증** 만. 정렬 / 필터 / 탭 같은
표시 정책은 모두 FE 가 처리. 따라서 본 DTO 는 단순 응답 / 요청 스키마만 정의.

응답 노출 정책: 화면이 실제로 쓰는 필드만 포함. ``MedicationResponse`` 전체
를 drill-down 에 중복 노출하지 않고 ``MedicationListItem`` 짧은 view 로
분리 — Pydantic schema-as-contract 원칙에 따라 외부에 새 정보를 흘리지 않는다.
"""

from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class MedicationListItem(BaseModel):
  """drill-down 페이지의 약 카드용 짧은 view — 화면에 노출되는 필드만 포함.

  약품 상세 페이지 (``/medication/[id]``) 에서 더 풍부한 필드가 필요할 때는
  별도 ``GET /medications/{id}`` 응답 (``MedicationResponse``) 을 사용한다.
  """

  model_config = ConfigDict(from_attributes=True)

  id: UUID = Field(..., description="Medication ID")
  medicine_name: str = Field(..., description="약품명")
  dose_per_intake: str | None = Field(None, description="1회 복용량")
  intake_instruction: str | None = Field(None, description="복용 지시사항")
  daily_intake_count: int | None = Field(None, description="1일 복용 횟수")
  total_intake_days: int | None = Field(None, description="총 복용 일수")
  dispensed_date: date | None = Field(None, description="조제일")
  is_active: bool = Field(..., description="현재 복용 중 여부")


class PrescriptionGroupCard(BaseModel):
  """처방전 카드 list 응답 — drill-down 전 요약 뷰.

  카드에 표시할 메타 + 약 수만 포함. 약 list 는 ``GET /{group_id}`` drill-down
  에서 ``MedicationResponse`` 로 받는다.
  """

  model_config = ConfigDict(from_attributes=True)

  id: UUID = Field(..., description="처방전 그룹 ID")
  hospital_name: str | None = Field(None, description="처방전 발행 병원 이름")
  department: str | None = Field(None, description="처방 진료과")
  dispensed_date: date | None = Field(None, description="처방 조제일")
  source: str = Field(..., description="생성 경로 (OCR/MANUAL/MIGRATED)")
  created_at: datetime = Field(..., description="그룹 생성 시각")
  medications_count: int = Field(..., description="그룹에 속한 medication 수 (deleted 제외)")
  active_medications_count: int = Field(
    default=0,
    description="그룹 안 is_active=True 인 medication 수 (= 현재 복용 중인 약 개수)",
  )
  has_active_medication: bool = Field(
    ...,
    description="그룹 안 1개 이상 medication 이 is_active=True (= 복용 중)",
  )


class PrescriptionGroupUpdate(BaseModel):
  """처방전 그룹 부분 수정 요청 — hospital_name / department.

  dispensed_date 는 처방 사실의 핵심 메타라 수정을 막는다 (잘못 등록되었으면
  삭제 후 재등록 권장).
  """

  hospital_name: str | None = Field(None, max_length=128, description="처방전 발행 병원 이름")
  department: str | None = Field(None, max_length=64, description="처방 진료과 (예: 내과)")


class PrescriptionGroupDetail(BaseModel):
  """처방전 drill-down 응답 — 그룹 메타 + medication list."""

  model_config = ConfigDict(from_attributes=True)

  id: UUID = Field(..., description="처방전 그룹 ID")
  hospital_name: str | None = Field(None, description="처방전 발행 병원 이름")
  department: str | None = Field(None, description="처방 진료과")
  dispensed_date: date | None = Field(None, description="처방 조제일")
  source: str = Field(..., description="생성 경로 (OCR/MANUAL/MIGRATED)")
  created_at: datetime = Field(..., description="그룹 생성 시각")
  medications: list[MedicationListItem] = Field(
    default_factory=list,
    description="그룹에 속한 medication 짧은 view (deleted 제외, medicine_name 가나다 정렬)",
  )

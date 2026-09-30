"""OCR DTO models module.

This module contains data transfer objects for OCR (Optical Character Recognition)
operations including medicine extraction, draft persistence, and confirmation.
"""

from datetime import date, datetime
from enum import StrEnum

from pydantic import BaseModel, Field


class OcrDraftStatus(StrEnum):
  """OCR 처리 상태 (프론트 폴링 응답용).

  PENDING: ai-worker 가 처리 중. 프론트는 폴링을 계속한다.
  READY:   처리 완료. ``medicines`` 필드에 결과가 채워져 있다.
  NO_TEXT: OCR 결과에 텍스트가 없음 (블러·빈 이미지 등). 사용자에게 재촬영 안내.
  NO_CANDIDATES: 텍스트는 있지만 약품명 후보 추출 실패. 사용자에게 다른 이미지 안내.
  FAILED:  처리 중 예외 발생. 일반 에러 안내.
  """

  PENDING = "pending"
  READY = "ready"
  NO_TEXT = "no_text"
  NO_CANDIDATES = "no_candidates"
  FAILED = "failed"


class ExtractedMedicine(BaseModel):
  """Individual medicine extraction data model.

  Represents structured data extracted from prescription images
  including dosage, frequency, and instruction information.
  """

  medicine_name: str = Field(description="추출된 약품명 (예: 타이레놀정500mg)")
  dispensed_date: date | None = Field(None, description="처방전에 적힌 처방(조제)일 (예: 2026-04-13)")
  department: str | None = Field(None, description="처방 진료과 (예: 내과, 정형외과)")
  category: str | None = Field(None, description="약품 분류 (예: 해열진통제, 항생제)")
  dose_per_intake: str | None = Field(None, description="1회 복용량 단위 포함 (예: 1정, 2캡슐, 5ml)")
  daily_intake_count: int | None = Field(None, description="1일 복용 횟수 (예: 3)")
  total_intake_days: int | None = Field(None, description="총 복용 일수 (예: 5, daily_intake_count와 다른 값)")
  intake_instruction: str | None = Field(None, description="복용 시점 지시사항 (예: 식후 30분, 취침 전)")

  # =========================================================================
  # [AI OCR 파이프라인 트래킹 추가]
  # =========================================================================
  raw_ocr_name: str | None = Field(None, description="OCR이 인식한 날것의 텍스트")
  is_llm_corrected: bool = Field(False, description="LLM을 통해 교정되었는지 여부")
  match_score: float | None = Field(None, description="퍼지/LLM 신뢰도 점수 (0.0~1.0)")


class OcrExtractResponse(BaseModel):
  """OCR extraction enqueue response — 즉시 200 응답.

  Dedup 으로 기존 draft 가 재사용된 경우에도 동일 형식으로 응답한다 (프론트는
  구분할 필요 없이 draft_id 로 result 페이지로 이동).
  """

  draft_id: str = Field(description="DB ocr_drafts.id (UUID) — 폴링·confirm 의 키")
  medicines: list[ExtractedMedicine] = Field(default_factory=list)


class OcrDraftPollResponse(BaseModel):
  """폴링 응답 — 상태 + (READY 일 때만) medicines.

  프론트는 ``status`` 를 보고 흐름을 분기한다:
  - PENDING: 대기, 다시 폴링
  - READY: medicines 표시 후 사용자 검수 화면으로
  - NO_TEXT / NO_CANDIDATES / FAILED: 안내 메시지 + 재업로드 유도
  """

  draft_id: str
  status: OcrDraftStatus
  medicines: list[ExtractedMedicine] = Field(default_factory=list)


class OcrDraftSummary(BaseModel):
  """main 페이지 카드용 요약 — 활성 draft 1건의 메타.

  제목은 프론트가 ``created_at`` 으로 "오후 5:43 업로드" 형태로 렌더링한다
  (백엔드는 raw timestamp 만 전달, 사용자 timezone 변환은 클라이언트 책임).
  """

  draft_id: str = Field(description="DB ocr_drafts.id (UUID)")
  status: OcrDraftStatus = Field(description="현재 처리 상태")
  created_at: datetime = Field(description="업로드 시각 (서버 timezone, ISO8601)")


class OcrActiveDraftsResponse(BaseModel):
  """현재 사용자의 활성 draft 목록 (24h 안 + 미consume).

  빈 리스트일 수 있다 (초기 사용자, 모두 consume 됨, 24h 경과). 빈 리스트는
  에러가 아니라 정상 응답이다 — main 카드를 숨기는 신호.
  """

  drafts: list[OcrDraftSummary] = Field(default_factory=list)


class ConfirmMedicationRequest(BaseModel):
  """User final confirmation request model.

  Used when user confirms and potentially modifies
  the extracted medication data before final storage.
  profile_id: if provided, saves medication under that profile (family profile support).
              if omitted, falls back to the account's SELF profile.
  """

  draft_id: str = Field(description="Target draft ID (DB ocr_drafts.id)")
  confirmed_medicines: list[ExtractedMedicine]
  profile_id: str | None = Field(None, description="Target profile ID (family profile support)")
  hospital_name: str | None = Field(
    None,
    max_length=128,
    description="처방전 발행 병원 이름 (그룹 메타). 미입력 시 NULL = '미상'",
  )
  department: str | None = Field(
    None,
    max_length=64,
    description="처방 진료과 (그룹 메타). 미입력 시 NULL = '미상'",
  )

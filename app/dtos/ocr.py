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


class OcrLlmExtractedItem(BaseModel):
  """LLM 이 OCR 원문에서 뽑아낸 약품 1건 — **LLM 경계 DTO**(`DTO_DESIGN_RULES` §7).

  🔴 아래 `ExtractedMedicine` 과 다르다. 저쪽은 **DB 매칭을 거친 최종 응답**이고
  추적 필드(`raw_ocr_name`·`match_score` 등)를 담는다. 이것은 **모델이 돌려주는 모양**
  그대로이며, 프롬프트의 「출력 예시」와 1:1 이다.

  🔑 **기본값을 주지 않는다** — OpenAI Structured Output 의 `strict` 모드는 모든 필드를
  required 로 요구한다. *«값이 없음»* 은 기본값이 아니라 **`None`** 으로 표현한다
  (프롬프트도 *«없다면 null 로 반환해»* 라고 지시한다).
  """

  name: str = Field(description="약품명 (용량 제외)")
  strength: str = Field(description="용량 (예: 500mg). 없으면 빈 문자열")
  type: str = Field(description="약품 유형 — 의약품 또는 영양제")
  dose: int | None = Field(description="1회 투약량. 텍스트에 없으면 null")
  daily_count: int | None = Field(description="1일 투약 횟수. 없으면 null")
  total_days: int | None = Field(description="총 투약 일수. 없으면 null")
  instruction: str = Field(description="복용 방법 (예: 식후 30분)")


class OcrLlmExtraction(BaseModel):
  """LLM 응답 봉투 — 프롬프트가 요구하는 `items` 배열.

  `QA-07` ② 의 승격 대상이다. `json_object` 는 *«JSON 이기만 하면 된다»* 라
  필드 이름·타입을 모델이 지킬 의무가 없었다. 이 스키마를 보내면 **모델이 지킨다.**
  """

  items: list[OcrLlmExtractedItem] = Field(description="추출된 약품 목록")


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

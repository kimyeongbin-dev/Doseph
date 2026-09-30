"""OCR draft model module.

처방전 OCR 비동기 처리 결과의 영속 저장소. 사용자가 페이지를 닫더라도
프로필 단위로 결과를 회수할 수 있도록 Redis 가 아닌 DB 에 보관한다.

수명 정책: 24h. 보관 기간이 지난 draft 는 별도 cron 으로 정리 (별건).
"""

from enum import StrEnum

from tortoise import fields, models


class OcrDraftStatusValue(StrEnum):
  """OCR draft 상태 — DTO 의 ``OcrDraftStatus`` 와 값 일치."""

  PENDING = "pending"
  READY = "ready"
  NO_TEXT = "no_text"
  NO_CANDIDATES = "no_candidates"
  FAILED = "failed"


class OcrDraft(models.Model):
  """처방전 OCR 임시 저장 — 24h 정책, 프로필 단위 dedup.

  Attributes:
      id: UUID PK — FastAPI 가 enqueue 시 채움 (RQ task 인자로 전달).
      profile: 업로드한 사용자 프로필 (FK, CASCADE).
      status: ai-worker 처리 상태 (pending → ready/no_text/no_candidates/failed).
      medicines: ai-worker 가 채우는 ExtractedMedicine 리스트 (JSONB).
      filename: 원본 파일명 (UI 디버깅·로깅용, 사용자에게 표시 안 함).
      image_hash: SHA256(image_bytes) — 동일 사용자 dedup 키.
      created_at: 업로드 시각 — UI 카드 제목 ("오후 5:43 업로드") 기반.
      processed_at: ai-worker 가 처리 완료한 시각.
      consumed_at: confirm 으로 DB 영구 저장 완료 시점 (NULL 이면 아직 활성).
  """

  id = fields.UUIDField(pk=True)
  profile = fields.ForeignKeyField(
    "models.Profile",
    related_name="ocr_drafts",
    on_delete=fields.CASCADE,
    description="업로드 프로필",
  )
  status = fields.CharField(
    max_length=16,
    default=OcrDraftStatusValue.PENDING.value,
    description="pending / ready / no_text / no_candidates / failed",
  )
  medicines = fields.JSONField(
    default=list,
    description="ExtractedMedicine 리스트 (ai-worker 가 채움)",
  )
  filename = fields.CharField(max_length=256, null=True, description="원본 파일명")
  image_hash = fields.CharField(max_length=64, description="SHA256(image_bytes) — dedup 키")
  created_at = fields.DatetimeField(auto_now_add=True)
  processed_at = fields.DatetimeField(null=True, description="ai-worker 처리 완료 시각")
  consumed_at = fields.DatetimeField(null=True, description="confirm 완료 시각 (NULL=활성)")

  class Meta:
    table = "ocr_drafts"
    table_description = "처방전 OCR 처리 결과 임시 저장 (24h, profile 별 회수 가능)"

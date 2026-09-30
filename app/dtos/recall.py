"""Recall alert DTOs (Phase 7 — §A.6.1).

Common payloads shared by the registration-time modal (§A.2.1) and the
my-page label (§A.2.2). ``RecallStatusDTO.alert_payload`` re-uses the
same ``RecallAlertDTO`` so the badge click can re-open the exact modal
the user saw at registration time.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field


class RecallSeverity(StrEnum):
  """Severity tier — branched purely by ``sale_stop_yn``.

  - ``CRITICAL``: 판매중지 (sale_stop_yn=Y) — prompts immediate stop.
  - ``ADVISORY``: 자율회수 (sale_stop_yn=N) — soft exchange notice.
  """

  CRITICAL = "critical"
  ADVISORY = "advisory"


class RecallAlertItemDTO(BaseModel):
  """One drug-recall row rendered inside the modal / label payload."""

  item_seq: str = Field(..., description="식약처 ITEM_SEQ")
  product_name: str = Field(..., description="제품명")
  entrps_name: str = Field(..., description="제조사명 (원문)")
  recall_reason: str = Field(..., description="회수 사유")
  recall_command_date: str = Field(..., description="회수 명령일 YYYYMMDD")
  sale_stop_yn: str = Field(..., description="판매중지 여부 Y/N")


class RecallAlertDTO(BaseModel):
  """Modal payload — used at registration time and on label click."""

  severity: str = Field(..., description='"critical" 또는 "advisory"')
  header: str = Field(..., description="모달 헤더 (한국어)")
  body: str = Field(..., description="모달 본문 (한국어)")
  items: list[RecallAlertItemDTO] = Field(
    default_factory=list,
    description="매칭된 회수 row 들 (recall_command_date 최신순)",
  )


class RecallStatusDTO(BaseModel):
  """Label payload shown next to a medication row in my-page."""

  severity: str = Field(..., description='"critical" 또는 "advisory"')
  label_text: str = Field(..., description="배지 텍스트 (예: ⚠️ 회수·판매중지)")
  recall_command_date: str = Field(..., description="라벨 표시 기준 — 가장 최근 회수 명령일")
  recall_reason_short: str = Field(..., description="≤60자 회수 사유 요약")
  alert_payload: RecallAlertDTO = Field(
    ...,
    description="라벨 클릭 시 재발화할 모달 페이로드 (등록 시점과 동일 구조)",
  )

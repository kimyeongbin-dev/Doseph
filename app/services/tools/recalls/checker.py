"""Recall checker tool implementations (Phase 7 Step 5).

Two LLM-callable async functions:

- ``check_user_medications_recall(profile_id)`` — Q1.
  사용자의 ``medications`` 와 ``drug_recalls`` 를 매칭. 단순 ``item_seq``
  매칭 + ``product_name`` ILIKE fallback (S7) 은 Repository 의
  ``find_match`` 가 처리한다.

- ``check_manufacturer_recalls(profile_id, manufacturer=None)`` — Q2.
  특정 제조사의 회수 이력을 조회한다. 인자가 ``None`` 이면 사용자가
  복용 중인 약의 제조사 셋을 자동 추출한다.

Tool function signatures keep `*Repository` 인자를 명시해 DI/테스트가
용이하도록 했다. Router LLM 단에서는 RQ adapter (`rq_adapters.py`)
가 이 함수들을 wrap 하여 의존성을 주입한다.
"""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from app.models.medicine_info import MedicineInfo
from app.repositories.drug_recall_repository import DrugRecallRepository
from app.repositories.medication_repository import MedicationRepository

logger = logging.getLogger(__name__)


def _serialize_recall(row: Any) -> dict[str, str]:
  """Convert a DrugRecall row into the wire response dict.

  Keys are intentionally English snake_case to keep the schema
  consistent with other tool responses.
  """
  return {
    "item_seq": row.item_seq or "",
    "product_name": row.product_name or "",
    "entrps_name": row.entrps_name or "",
    "recall_reason": row.recall_reason or "",
    "recall_command_date": row.recall_command_date or "",
    "sale_stop_yn": row.sale_stop_yn or "",
  }


def _empty_response() -> dict[str, Any]:
  return {"matched": False, "recalls": []}


# ── 사용자 제조사 셋 해상도 (테스트에서 monkeypatch 가능하도록 모듈 함수) ──
# 흐름: profile_id → medications → medicine_name 셋
#       → medicine_info(medicine_name__in=...) → entp_name 셋


async def resolve_user_manufacturers(profile_id: UUID) -> set[str]:
  """Return the set of manufacturer names for the user's medications.

  Looks up `medicine_info` rows that share `medicine_name` with the
  user's `medications` and harvests their `entp_name`. Empty / null
  manufacturer names are filtered out.
  """
  repo = MedicationRepository()
  medications = await repo.get_all_by_profile(profile_id)
  names = {m.medicine_name for m in medications if m.medicine_name}
  if not names:
    return set()

  rows = await MedicineInfo.filter(medicine_name__in=names).all()
  return {row.entp_name for row in rows if row.entp_name}


# ── Q1 ────────────────────────────────────────────────────────────────


async def check_user_medications_recall(
  *,
  profile_id: UUID,
  medication_repository: MedicationRepository | None = None,
  drug_recall_repository: DrugRecallRepository | None = None,
) -> dict[str, Any]:
  """Q1 — 사용자 복용약 중 식약처 회수·판매중지 매칭.

  Args:
      profile_id: 백엔드가 자동 주입하는 사용자 식별자.
      medication_repository: 복용약 조회 Repository (DI).
      drug_recall_repository: 회수 매칭 Repository (DI).

  Returns:
      dict — ``{"matched": bool, "recalls": [...]}``.
  """
  med_repo = medication_repository or MedicationRepository()
  recall_repo = drug_recall_repository or DrugRecallRepository()

  medications = await med_repo.get_all_by_profile(profile_id)
  if not medications:
    return _empty_response()

  matched_rows: list[Any] = []
  seen: set[tuple[str, str, str]] = set()
  for med in medications:
    rows = await recall_repo.find_match(med)
    for row in rows:
      key = (row.item_seq or "", row.recall_command_date or "", row.recall_reason or "")
      if key in seen:
        continue
      seen.add(key)
      matched_rows.append(row)

  if not matched_rows:
    return _empty_response()

  return {
    "matched": True,
    "recalls": [_serialize_recall(r) for r in matched_rows],
  }


# ── Q2 ────────────────────────────────────────────────────────────────


async def check_manufacturer_recalls(
  *,
  profile_id: UUID,
  manufacturer: str | None = None,
  medication_repository: MedicationRepository | None = None,
  drug_recall_repository: DrugRecallRepository | None = None,
) -> dict[str, Any]:
  """Q2 — 사용자 복용약의 제조사 회수 이력 조회.

  Args:
      profile_id: 백엔드가 자동 주입하는 사용자 식별자.
      manufacturer: 명시적 제조사명. None 이면 사용자 복용약의
          제조사 셋을 자동 추출한다.
      medication_repository: 복용약 조회 Repository (DI).
      drug_recall_repository: 회수 매칭 Repository (DI).

  Returns:
      dict — ``{"matched": bool, "recalls": [...]}``. 매칭이 0건이면
      matched=False.
  """
  del medication_repository  # 현재는 manufacturer set 해상도만 필요 — resolve_user_manufacturers 가 처리
  recall_repo = drug_recall_repository or DrugRecallRepository()

  if manufacturer:
    names: set[str] = {manufacturer}
  else:
    names = await resolve_user_manufacturers(profile_id)
    if not names:
      return _empty_response()

  rows = await recall_repo.find_by_manufacturers(names)
  if not rows:
    return _empty_response()

  return {
    "matched": True,
    "recalls": [_serialize_recall(r) for r in rows],
  }

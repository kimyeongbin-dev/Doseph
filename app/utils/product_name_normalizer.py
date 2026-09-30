"""Product-name normalization for drug-recall matching (Phase 7 — §A.6.1).

The OCR / manual entry path stores `medication.medicine_name` with
inconsistent whitespace and case. The drug-recall public API likewise
returns `PRDUCT` strings with no whitespace. Equality matching across
both sides therefore needs a canonical form.

Used by:
    - ``app.repositories.drug_recall_repository.find_by_item_seq_or_name``
    - ``app.repositories.drug_recall_repository.find_recalls_for_medications``

Pure function. No I/O, no DB.
"""

from __future__ import annotations

import re
import unicodedata

# ── 정규화 룰 ────────────────────────────────────────────────────────
# 흐름: NFKC 유니코드 정규화 -> 모든 공백 제거 -> 소문자 변환

_WHITESPACE_RE = re.compile(r"\s+")


def normalize_product_name(name: str | None) -> str:
  """Strip all whitespace, NFKC-normalize, and lower-case a product name.

  Args:
      name: Raw medicine_name / product_name. ``None`` or empty string
          returns the empty string for NULL safety.

  Returns:
      Canonical name. Idempotent — feeding the result back in produces
      the same value. Always a ``str``; never ``None``.

  Examples:
      >>> normalize_product_name(" 데모라니티딘정 150밀리그램 ")
      '데모라니티딘정150밀리그램'
      >>> normalize_product_name("Tylenol 500mg")
      'tylenol500mg'
      >>> normalize_product_name(None)
      ''
  """
  if not name:
    return ""

  # NFKC: 전각→반각, NBSP→일반 공백 등 폭 변형 통일.
  nfkc = unicodedata.normalize("NFKC", name)

  # 모든 공백 제거 — 시드 PRDUCT 가 공백 없는 표기를 쓰므로 입력 측을 맞춘다.
  no_space = _WHITESPACE_RE.sub("", nfkc)

  # 영문 대소문자 변형 흡수.
  return no_space.lower()

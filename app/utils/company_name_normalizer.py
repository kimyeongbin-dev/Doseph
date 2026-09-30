"""Company-name normalization for MFDS API responses.

The MFDS public APIs (drug-permit + drug-recall) return manufacturer
names with inconsistent decoration around the 株式会社 marker — `(주)`,
`(株)`, `주식회사` may appear before, after, or be omitted entirely.
This breaks naive equality / LIKE matching when joining recall rows
to the user's medication manufacturers.

`normalize_company_name` strips those decorations and collapses
whitespace so that `(주)한독`, `한독`, `한독 주식회사` and `한독(주)`
all map to the same canonical form `한독`.

Used by:
    - `app.services.drug_recall_service` — populating
      `drug_recalls.entrps_name_normalized` at ingestion time.
    - `app.repositories.drug_recall_repository.find_by_manufacturers`
      — normalizing the user-side manufacturer set before the JOIN.

Pure function. No I/O, no DB.
"""

from __future__ import annotations

import re
import unicodedata

# ── 정규식 사전 ──────────────────────────────────────────────────────
# 흐름: NFKC 유니코드 정규화 -> 괄호 표기 제거 -> 주식회사 단어 제거
#       -> 다중 공백 압축 -> strip
_PAREN_JUSIK_RE = re.compile(r"\((?:주|株)\)")
_JUSIK_WORD_RE = re.compile(r"주식회사")
_MULTI_SPACE_RE = re.compile(r"\s+")


def normalize_company_name(name: str | None) -> str:
  """Strip 株式会社 decorations and normalize whitespace.

  Args:
      name: Raw manufacturer name from the public API. May be None
          or empty (treated as the empty string for NULL safety).

  Returns:
      Canonical manufacturer name. Idempotent — feeding the result
      back in produces the same value. Always a `str`; never `None`.

  Examples:
      >>> normalize_company_name("동국제약(주)")
      '동국제약'
      >>> normalize_company_name("(주)한독")
      '한독'
      >>> normalize_company_name("주식회사 동국제약")
      '동국제약'
      >>> normalize_company_name(None)
      ''
  """
  if not name:
    return ""

  # NFKC 정규화: 전각 → 반각, NBSP → 일반 공백 등 폭 변형 통일
  normalized = unicodedata.normalize("NFKC", name)

  # `(주)` / `(株)` 제거
  normalized = _PAREN_JUSIK_RE.sub("", normalized)

  # `주식회사` 단어 제거
  normalized = _JUSIK_WORD_RE.sub("", normalized)

  # 다중 공백 → 단일 공백 → strip
  normalized = _MULTI_SPACE_RE.sub(" ", normalized).strip()

  # 정규화 후 내부에 공백이 남아도 `동국 제약` 같은 실제 회사명일
  # 수 있으므로 공백을 제거하지 않는다. 단 `주식회사` 잔재로 생긴
  # 단일 공백만 양쪽 끝에서 제거되도록 한 번 더 strip.
  return normalized.strip()

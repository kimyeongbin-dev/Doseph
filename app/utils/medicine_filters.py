"""Reusable keyword-based filters for public-API drug data.

Centralizes the keyword sets and predicates used across services that
ingest data from the Food and Drug Safety public API. Both the
medicine_info sync (`medicine_data_service`) and the upcoming drug
recall sync (`drug_recall_service`) feed raw `ITEM_NAME` / `prdtName`
strings through these helpers, so they live here as pure functions to
avoid drift between two copies of the same regex.

Categories:
    Hospital-only injectables / infusions / implants — excluded from
    the consumer DB, but self-injectable drugs (insulin, saxenda, etc.)
    are kept.

Note:
    Pure functions only. No I/O, no DB, no logging. Safe to import
    from any layer (services, scripts, tests).
"""

# ── 병원 전용 의약품 키워드 (주사·수액·이식 + 병원 인프라용 제형) ────
# 흐름: 키워드 매칭 → 자가주사 화이트리스트 검사 → 최종 판정
_HOSPITAL_ONLY_KEYWORDS: tuple[str, ...] = (
  "주사",
  "수액",
  "이식",
)

# ── 자가주사 가능 약제 화이트리스트 (병원 전용에서 예외 처리) ──────────
_SELF_INJECT_KEYWORDS: tuple[str, ...] = (
  "인슐린",
  "삭센다",
  "자가주사",
  "펜주",
  "프리필드",
)

# ── 의약외품·생활용품 차단 키워드 (Phase 7 — 회수 API 노이즈 필터) ────
# 식약처 회수 API 는 의약외품(치약·칫솔·생리대·붕대 등) 도 함께 반환한다.
# 우리 서비스는 처방약 도메인이므로 적재 단계에서 제외.
# `RECALL_FILTER_NON_DRUG` env 토글로 비활성 가능.
_NON_DRUG_KEYWORDS: tuple[str, ...] = (
  "칫솔",
  "치약",
  "구강세정제",
  "마우스워시",
  "생리대",
  "탐폰",
  "팬티라이너",
  "기저귀",
  "붕대",
  "거즈",
  "반창고",
  "밴드",
  "콘돔",
  "마스크",
  "체온계",
  "혈압계",
  "혈당계",
  "안경",
  "콘택트렌즈",
  "보청기",
  "소독제",
  "손세정제",
  "세척제",
  "비누",
  "샴푸",
  "린스",
  "로션",
)


def is_hospital_only(product_name: str) -> bool:
  """Check whether a product name indicates a hospital-only formulation.

  A product is considered hospital-only when it matches any of the
  exclusion keywords (injection, infusion, implant) AND does not
  match any self-inject whitelist keyword (insulin, saxenda, etc.).

  Args:
      product_name: Korean product name as returned by the public API
          (`ITEM_NAME` for permits, `prdtName` for recalls).

  Returns:
      True if the product should be excluded from the consumer DB,
      False otherwise. Empty / non-string input returns False so the
      caller can decide separately how to handle missing names.
  """
  if not product_name:
    return False

  has_exclude = any(kw in product_name for kw in _HOSPITAL_ONLY_KEYWORDS)
  if not has_exclude:
    return False

  has_self_inject = any(kw in product_name for kw in _SELF_INJECT_KEYWORDS)
  return not has_self_inject


def is_non_drug_product(product_name: str) -> bool:
  """Check whether a product is a consumer non-drug item (toothbrush, etc.).

  Toggle via ``config.RECALL_FILTER_NON_DRUG`` at the call site —
  this predicate is purely a keyword check.

  Args:
      product_name: Korean product name as returned by the recall API.

  Returns:
      True if the product matches a non-drug keyword and should be
      excluded from the consumer-medication recall corpus. Empty input
      returns False.
  """
  if not product_name:
    return False

  return any(kw in product_name for kw in _NON_DRUG_KEYWORDS)

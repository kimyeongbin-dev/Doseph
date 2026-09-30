"""OCR 텍스트 후처리 — 약품명 후보 추출 (LLM 친화적 아키텍처 버전).

[아키텍트 코멘트]
과거 Rule-based 방식과 달리, LLM 파이프라인에서는 '문맥(Context)'이 생명입니다.
용량(mg), 숫자, 용법 등의 데이터를 정규식으로 함부로 날리지 않고,
명백한 개인정보(전화번호 등)와 특수문자 노이즈만 가볍게 걷어낸 뒤 LLM에게 판별을 위임합니다.
"""

import logging
import re

logger = logging.getLogger(__name__)

# 💡 LLM의 추론 힌트가 되는 용량, 숫자, 복용법은 절대 건드리지 않습니다!
_REMOVE_PATTERNS: list[re.Pattern] = [
  re.compile(r"\d{4}[-/.]\d{2}[-/.]\d{2}"),  # 날짜 정도만 가볍게 제거
  re.compile(r"(조제|처방)\s*일\s*:?\s*\S+"),
]

# 💡 병원명, 약국명 등 명백한 노이즈만 차단 (용법, 용량 같은 단어는 남겨둠)
_BLACKLIST_KEYWORDS: list[str] = [
  "약국",
  "의원",
  "병원",
  "클리닉",
  "의료",
  "전화",
  "주소",
  "원장",
  "약사",
  "환자",
  "성명",
  "연락처",
]

_MIN_NAME_LENGTH = 1  # '물', '철' 등 1글자 약품/성분이 있을 수 있으므로 완화


def clean_ocr_text(raw_text: str) -> str:
  """OCR 원문에서 최소한의 노이즈만 제거하여 문맥을 보존한다."""
  cleaned = raw_text.strip()

  for pattern in _REMOVE_PATTERNS:
    cleaned = pattern.sub("", cleaned)

  # 💡 특수문자 제거 시 단위(%)나 소수점(.)은 보존하도록 정규식 완화
  cleaned = re.sub(r"[^\w\s\(\)\-\.%]", " ", cleaned)

  return " ".join(cleaned.split())


def extract_medicine_candidates(cleaned_text: str) -> list[str]:
  """숫자나 용량을 강제로 날리지 않고, 블랙리스트만 거른 토큰을 반환한다.
  (이 토큰들은 medicine_matcher.py에서 다시 하나의 문장으로 합쳐져 LLM에 들어갑니다)
  """
  candidates = [token for token in cleaned_text.split() if _is_candidate(token)]
  logger.info("Extracted %d minimal context tokens from OCR text", len(candidates))
  return candidates


def _is_candidate(token: str) -> bool:
  """블랙리스트만 거르고 숫자(용량)는 무조건 통과시킨다."""
  stripped = token.strip()
  if len(stripped) < _MIN_NAME_LENGTH:
    return False

  #  _NUMERIC_ONLY_PATTERN.fullmatch(stripped) 삭제 (500, 20 살림)

  return not _is_blacklisted(stripped)


def _is_blacklisted(token: str) -> bool:
  return any(keyword in token for keyword in _BLACKLIST_KEYWORDS)

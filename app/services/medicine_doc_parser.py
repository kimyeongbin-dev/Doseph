"""Dtl06 DOC XML parser.

Food and Drug Safety Dtl06 endpoint returns three XML document blobs
(EE_DOC_DATA / UD_DOC_DATA / NB_DOC_DATA) whose structure is
``<DOC><SECTION><ARTICLE><PARAGRAPH>...``. This module translates
that structure into ARTICLE-level records suitable for RAG chunk
creation, plus two helpers:

- parse_doc_articles: ARTICLE 단위 (title, body) 리스트
- flatten_doc_plaintext: DOC 전체 → 단일 평문
- classify_article_section: ARTICLE title 키워드 → MedicineChunkSection

The parser is tolerant of ``None``, empty strings, and malformed XML:
bad input returns an empty result instead of raising.
"""

from dataclasses import dataclass
import html
import logging
import re

import defusedxml.ElementTree as ET  # noqa: N817 — stdlib ET 와 동일한 alias 관용 유지

from app.models.medicine_chunk import MedicineChunkSection

logger = logging.getLogger(__name__)


# ── PARAGRAPH 본문 HTML 정제 ────────────────────────────────────────
# 식약처 의약품 raw doc 의 PARAGRAPH 안에 종종 HTML 표 (`<table>`, `<tr>`,
# `<td>`, `<p>` 등) + entity (`&gt;`, `&#x2022;`, `&amp;`) 가 그대로 들어
# 있다. 임베딩 입력에 들어가면 토큰 낭비 + cosine 노이즈 → 정제 필수.
#
# 정제 흐름:
#   1) html.unescape — &gt; &lt; &amp; &nbsp; &#x2022; 등 decode
#   2) HTML 태그 strip — `<td style="...">` 등 모든 태그 제거
#   3) 다중 공백 정리 — `\s+` → 단일 공백 (줄바꿈은 보존)
_HTML_TAG_RE = re.compile(r"<[^>]+>", re.UNICODE)
_MULTI_WS_RE = re.compile(r"[ \t]+", re.UNICODE)


def _clean_paragraph_text(text: str) -> str:
  """PARAGRAPH 본문에서 HTML 태그·entity 제거 + 공백 정리.

  Args:
      text: PARAGRAPH 의 raw text (CDATA 안에 HTML 포함 가능).

  Returns:
      정제된 평문. 빈 입력은 그대로 반환.
  """
  if not text:
    return text
  decoded = html.unescape(text)
  stripped = _HTML_TAG_RE.sub(" ", decoded)
  lines = [_MULTI_WS_RE.sub(" ", line).strip() for line in stripped.split("\n")]
  return "\n".join(line for line in lines if line)


@dataclass(frozen=True)
class Article:
  """ARTICLE-level extracted record.

  Attributes:
      title: ARTICLE tag title attribute (may be empty when only PARAGRAPHs).
      body: Joined PARAGRAPH text content, newline-separated (may be empty).
  """

  title: str
  body: str


# ── 섹션 키워드 매핑 (순서 중요: 더 구체적인 것 먼저) ─────────────────
# Each entry is (keyword, section). The first matching keyword wins.
# v2 6섹션 enum 으로 재매핑됨 — 사용자 질문 패턴 기준 묶음.
_SECTION_KEYWORDS: tuple[tuple[str, MedicineChunkSection], ...] = (
  # 생활 상호작용 (술/카페인/운전 — 사용자 일상 질문)
  ("음주", MedicineChunkSection.LIFESTYLE_INTERACTION),
  ("술", MedicineChunkSection.LIFESTYLE_INTERACTION),
  ("카페인", MedicineChunkSection.LIFESTYLE_INTERACTION),
  ("커피", MedicineChunkSection.LIFESTYLE_INTERACTION),
  ("운전", MedicineChunkSection.LIFESTYLE_INTERACTION),
  ("기계조작", MedicineChunkSection.LIFESTYLE_INTERACTION),
  # 약물 상호작용 — 금기·병용·신중투여 일괄
  ("투여하지 말", MedicineChunkSection.DRUG_INTERACTION),
  ("복용하지 말", MedicineChunkSection.DRUG_INTERACTION),
  ("사용하지 말", MedicineChunkSection.DRUG_INTERACTION),
  ("금기", MedicineChunkSection.DRUG_INTERACTION),
  ("신중히 투여", MedicineChunkSection.DRUG_INTERACTION),
  ("신중 투여", MedicineChunkSection.DRUG_INTERACTION),
  ("신중히 복용", MedicineChunkSection.DRUG_INTERACTION),
  ("상호작용", MedicineChunkSection.DRUG_INTERACTION),
  ("병용", MedicineChunkSection.DRUG_INTERACTION),
  ("상의", MedicineChunkSection.DRUG_INTERACTION),
  # 이상반응·과량 — 부작용 영역
  ("이상반응", MedicineChunkSection.ADVERSE_REACTION),
  ("부작용", MedicineChunkSection.ADVERSE_REACTION),
  ("과량", MedicineChunkSection.ADVERSE_REACTION),
  ("과용", MedicineChunkSection.ADVERSE_REACTION),
  # 특수 상황 — 경고·임부·소아·고령·시술
  ("경고", MedicineChunkSection.SPECIAL_EVENT),
  ("임부", MedicineChunkSection.SPECIAL_EVENT),
  ("임산부", MedicineChunkSection.SPECIAL_EVENT),
  ("수유", MedicineChunkSection.SPECIAL_EVENT),
  ("가임", MedicineChunkSection.SPECIAL_EVENT),
  ("소아", MedicineChunkSection.SPECIAL_EVENT),
  ("어린이", MedicineChunkSection.SPECIAL_EVENT),
  ("영아", MedicineChunkSection.SPECIAL_EVENT),
  ("유아", MedicineChunkSection.SPECIAL_EVENT),
  ("신생아", MedicineChunkSection.SPECIAL_EVENT),
  ("고령자", MedicineChunkSection.SPECIAL_EVENT),
  ("노인", MedicineChunkSection.SPECIAL_EVENT),
  ("수술", MedicineChunkSection.SPECIAL_EVENT),
  ("시술", MedicineChunkSection.SPECIAL_EVENT),
)


def parse_doc_articles(xml: str | None) -> list[Article]:
  """Parse a Dtl06 DOC XML blob into ARTICLE records.

  Args:
      xml: Raw XML string from EE_DOC_DATA / UD_DOC_DATA / NB_DOC_DATA.
          ``None``, empty, or whitespace-only input returns ``[]``.

  Returns:
      List of Article(title, body) in document order. Malformed XML
      yields an empty list and logs a warning.
  """
  if not xml or not xml.strip():
    return []

  try:
    # defusedxml.ElementTree.fromstring — XXE / billion-laughs 등 XML 공격 방어 후 stdlib API 와 동일 파싱.
    root = ET.fromstring(xml)
  except ET.ParseError as exc:
    logger.warning("DOC XML parse failed: %s", exc)
    return []

  articles: list[Article] = []
  for article_el in root.iter("ARTICLE"):
    title = _clean_paragraph_text((article_el.get("title") or "").strip())
    paragraphs = [_clean_paragraph_text((p.text or "").strip()) for p in article_el.iter("PARAGRAPH") if p.text]
    body = "\n".join(p for p in paragraphs if p)
    articles.append(Article(title=title, body=body))

  return articles


def flatten_doc_plaintext(xml: str | None) -> str:
  r"""Flatten a DOC XML blob to a single newline-joined plaintext string.

  Used for UI display fields (e.g. MedicineInfo.efficacy). Produces
  ``title\nbody`` per ARTICLE, joined by blank lines.

  Args:
      xml: Raw XML string. ``None``/empty/malformed input returns ``""``.

  Returns:
      Plaintext without any XML tags or CDATA wrappers.
  """
  articles = parse_doc_articles(xml)
  if not articles:
    return ""

  blocks: list[str] = []
  for article in articles:
    parts = [article.title, article.body]
    block = "\n".join(p for p in parts if p)
    if block:
      blocks.append(block)

  return "\n\n".join(blocks)


# ── NB_DOC_DATA 식약처 10 카테고리 정규화 ─────────────────────────────
# (drug-info 응답용 — RAG 청킹용 6 섹션 분류와는 별개)
# title 의 숫자/공백 prefix 를 떼고 키워드로 매칭. 매칭 실패 시 None.
_NB_CATEGORY_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
  (re.compile(r"경고"), "경고"),
  (re.compile(r"투여하지\s*말|복용하지\s*말|사용하지\s*말|금기"), "금기"),
  (re.compile(r"신중(히|\s)*투여|신중\s*복용"), "신중 투여"),
  (re.compile(r"이상반응|부작용"), "이상반응"),
  (re.compile(r"일반적\s*주의"), "일반적 주의"),
  (re.compile(r"임부|임산부|수유"), "임부에 대한 투여"),
  (re.compile(r"소아|어린이|영아|유아|신생아"), "소아에 대한 투여"),
  (re.compile(r"고령자|노인"), "고령자에 대한 투여"),
  (re.compile(r"과량|과용"), "과량투여시의 처치"),
  (re.compile(r"적용상"), "적용상의 주의"),
)
ADVERSE_REACTION_KEY = "이상반응"


def normalize_nb_article_title(title: str | None) -> str | None:
  """식약처 NB ARTICLE.title 을 10 카테고리 키로 정규화.

  예:
      "1. 경고"           -> "경고"
      "2.다음 환자에는..."  -> "금기"
      "4. 이상반응"        -> "이상반응" (호출자가 side_effects 로 분리)
      "11. 알 수 없는 분류" -> None

  Args:
      title: ARTICLE title 원본. None / 빈 문자열 → None.

  Returns:
      정규화된 카테고리 키 또는 None.
  """
  if not title:
    return None
  for pattern, key in _NB_CATEGORY_PATTERNS:
    if pattern.search(title):
      return key
  return None


def parse_nb_categories(xml: str | None) -> tuple[dict[str, list[str]], list[str]]:
  """NB_DOC_DATA XML 을 식약처 카테고리별 dict + 이상반응 list 로 분리.

  Args:
      xml: NB_DOC_DATA raw XML. None / 빈 / 깨진 입력 → ({}, []).

  Returns:
      precautions: 식약처 9 카테고리 (이상반응 제외) → PARAGRAPH list
      side_effects: 이상반응 카테고리의 PARAGRAPH list
  """
  articles = parse_doc_articles(xml)
  if not articles:
    return ({}, [])

  precautions: dict[str, list[str]] = {}
  side_effects: list[str] = []

  for article in articles:
    key = normalize_nb_article_title(article.title)
    if key is None:
      logger.debug("NB ARTICLE 미분류: %s", article.title)
      continue
    items = [line.strip() for line in article.body.splitlines() if line.strip()]
    if not items:
      continue
    if key == ADVERSE_REACTION_KEY:
      side_effects.extend(items)
      continue
    precautions.setdefault(key, []).extend(items)

  return (precautions, side_effects)


def parse_ud_plaintext(xml: str | None) -> str:
  """UD_DOC_DATA (용법용량) XML 을 평문 문자열로 평탄화.

  Args:
      xml: UD_DOC_DATA raw XML. None / 빈 / 깨진 입력 → "".

  Returns:
      줄바꿈 결합된 평문.
  """
  return flatten_doc_plaintext(xml)


def classify_article_section(title: str) -> MedicineChunkSection:
  """Classify an ARTICLE title into a MedicineChunkSection.

  Uses ordered keyword matching over ``_SECTION_KEYWORDS``. Titles
  with no matching keyword fall back to ``INTAKE_GUIDE`` (일반 복용
  가이드).

  Args:
      title: ARTICLE title string (Korean).

  Returns:
      Corresponding MedicineChunkSection. Unknown/empty titles
      return INTAKE_GUIDE.
  """
  if not title:
    return MedicineChunkSection.INTAKE_GUIDE

  for keyword, section in _SECTION_KEYWORDS:
    if keyword in title:
      return section

  return MedicineChunkSection.INTAKE_GUIDE

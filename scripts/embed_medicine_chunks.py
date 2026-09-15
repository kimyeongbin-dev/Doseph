r"""medicine_info → medicine_chunk 청킹 + 임베딩 1회성 batch.

PLAN.md (feature/RAG) §4 Step 4-B — 32K medicine_info 의 raw XML 을
ARTICLE 단위로 청킹하고, OpenAI text-embedding-3-large (3072d) 으로
임베딩한 뒤 medicine_chunk 에 INSERT 한다.

흐름:
1. Tortoise.init
2. medicine_info 모두 순회 (--batch 단위, default 50)
3. 각 row 의 ee_doc_data / ud_doc_data / nb_doc_data XML 파싱
4. ARTICLE → classify_article_section → MedicineChunkSection
5. content 조립 ([약: name] [section_kr]\\n{title}\\n{body})
6. 토큰 길이 추정 (한국어 1.5자=1tok 단순) — 8000 초과 시 chunk_index 분할
7. 한 medicine 의 모든 chunk 를 OpenAI Embedding API batch 호출
8. medicine_chunk INSERT (ON CONFLICT (medicine_info_id, section, chunk_index) DO NOTHING)
9. progress 로그 (매 50 medicine 마다)

멱등성:
- unique constraint 위반 시 SKIP — 재실행 시 이미 INSERT 된 row 영향 X
- 중간 실패 시 그 medicine 부터 재시작 가능 (--resume-from)

Usage (EC2 fastapi 컨테이너 안에서):
    docker compose -f ~/AI_02_06/docker-compose.prod.yml exec -d fastapi \\
      python -m scripts.embed_medicine_chunks --batch 50 --concurrency 5

Cost (estimate):
    32K medicines x ~6 sections = ~192K chunks x ~500 tok = 96M tok
    text-embedding-3-large @ $0.13/1M = ~$12.5
"""

import argparse
import asyncio
import hashlib
import json
import logging
from pathlib import Path
import re
import sys

# Windows 콘솔 기본 코드페이지(cp949)에서 한글 출력이 깨지거나 죽지 않도록 고정한다.
# 🔴 stdout 과 stderr 는 **서로를 보호하지 않는다** — 한쪽만 고정하면 다른 쪽이 크래시한다(대장 D36).
# 지금 비-ASCII 를 안 찍더라도 둔다: 나중에 한글 한 줄을 넣는 순간 조용히 죽는 자리다.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
import time
from typing import Any

from openai import AsyncOpenAI
from tortoise import Tortoise
from tortoise.transactions import in_transaction

from app.core.config import config
from app.db.databases import TORTOISE_ORM
from app.models.medicine_chunk import MedicineChunk, MedicineChunkSection
from app.models.medicine_info import MedicineInfo
from app.models.medicine_ingredient import MedicineIngredient
from app.services.medicine_doc_parser import (
    Article,
    classify_article_section,
    parse_doc_articles,
)

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] [%(levelname)s] [%(name)s:%(lineno)d] - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("embed_medicine_chunks")
logging.getLogger("httpx").setLevel(logging.WARNING)

# ── 상수 ───────────────────────────────────────────────────────────
EMBEDDING_MODEL = "text-embedding-3-large"
EMBEDDING_DIMENSIONS = 3072
EMBEDDING_PRICE_PER_1M = 0.13  # USD

# OpenAI text-embedding-3-large input 한도 = 8192 tok. 분할 한도는 더 보수적
# 으로 4000 tok (한국어 토큰화는 char/tok 비율이 변동 커서 안전 마진 필요).
MAX_TOKENS_PER_CHUNK = 4000

# 한국어 평균 0.5~1자 = 1 token (cl100k_base 기준). tiktoken 미설치 환경에선
# 0.5 로 보수적 추정 (실제 토큰 수보다 *많이* 잡혀 분할이 적극적으로 일어남).
CHARS_PER_TOKEN = 0.5

# OpenAI Embedding batch input 한도는 매우 크지만 (지금은 메모리/네트워크
# 제약 위주) 안전하게 100 chunks per call.
EMBED_BATCH_SIZE = 100

# Retry: rate limit / connection error 시 exponential backoff
MAX_RETRIES = 4
INITIAL_BACKOFF = 1.0  # sec

# ── 큐레이션: 한국 외래 처방 빈도 상위 활성성분 86종 (수동 큐레이션) ─────
# 진통/항생/고혈압/고지혈증/당뇨/위장/항히스타민/항응고/갑상선/정신건강/비뇨/호흡기/기타
# 식약처 의약품안전나라 + DUR + 국민건강보험 진료비 통계 + 일반 임상 가이드 기반.
# 임베딩 비용 최소화 — 옵션 B (성분당 top-N brand 만) 의 source.
CORE_PRESCRIPTION_INGREDIENTS: tuple[str, ...] = (
    # 진통·해열·NSAID
    "아세트아미노펜",
    "이부프로펜",
    "나프록센",
    "덱시부프로펜",
    "록소프로펜나트륨수화물",
    "아세클로페낙",
    "셀레콕시브",
    "트라마돌염산염",
    "아스피린",
    # 항생제 (외래 흔함)
    "아목시실린",
    "아목시실린수화물",
    "세파클러수화물",
    "세프디니르",
    "세프포독심프록세틸",
    "클래리스로마이신",
    "아지트로마이신수화물",
    "시프로플록사신염산염수화물",
    "레보플록사신",
    "메트로니다졸",
    "독시사이클린수화물",
    # 고혈압
    "암로디핀베실산염",
    "로사르탄칼륨",
    "발사르탄",
    "텔미사르탄",
    "칸데사르탄실렉세틸",
    "올메사르탄메독소밀",
    "라미프릴",
    "페린도프릴아르기닌",
    "카르베딜롤",
    "비소프롤롤푸마르산염",
    "아테놀롤",
    "히드로클로로티아지드",
    # 고지혈증
    "아토르바스타틴칼슘삼수화물",
    "로수바스타틴칼슘",
    "심바스타틴",
    "프라바스타틴나트륨",
    "피타바스타틴칼슘",
    "에제티미브",
    "페노피브레이트",
    # 당뇨
    "메트포르민염산염",
    "글리메피리드",
    "글리클라지드",
    "시타글립틴인산염일수화물",
    "빌다글립틴",
    "엠파글리플로진",
    "다파글리플로진",
    "리나글립틴",
    "리라글루티드",
    # 위장
    "오메프라졸",
    "에소메프라졸",
    "에소메프라졸마그네슘삼수화물",
    "란소프라졸",
    "라베프라졸나트륨",
    "판토프라졸나트륨",
    "라푸티딘",
    "파모티딘",
    "수크랄페이트수화물",
    "모사프리드시트르산염",
    # 항히스타민
    "세티리진염산염",
    "레보세티리진염산염",
    "로라타딘",
    "펙소페나딘염산염",
    "클로르페니라민말레산염",
    "베포타스틴베실산염",
    "에바스틴",
    # 항응고/항혈소판
    "와파린나트륨",
    "클로피도그렐황산수소염",
    "리바록사반",
    "아픽사반",
    "다비가트란에텍실레이트메실산염",
    # 갑상선
    "레보티록신나트륨",
    "메티마졸",
    "프로필티오우라실",
    # 정신건강
    "에스시탈로프람옥살산염",
    "설트랄린염산염",
    "파록세틴염산염수화물",
    "플루옥세틴염산염",
    "알프라졸람",
    "로라제팜",
    "디아제팜",
    "졸피뎀타르타르산염",
    # 비뇨/전립선
    "탐스로신염산염",
    "솔리페나신숙신산염",
    "두타스테리드",
    "피나스테리드",
    # 호흡기
    "몬테루카스트나트륨",
    "살부타몰황산염",
    "부데소니드",
    "플루티카손푸로에이트",
    # 기타
    "메틸프레드니솔론",
    "프레드니솔론",
    "트리메부틴말레산염",
    "알로푸리놀",
    "콜키친",
)


# 일반인 사용 부적합 — embed scope 에서 제외 (medicine_name ILIKE 매칭).
# 주사제 / 수액 / 동물용 / 진단 / 수출용 — 일반인 외래 처방 거의 없음 + RAG 답변 부적합.
EXCLUSION_PATTERNS: tuple[str, ...] = (
    "%주사%",
    "주",  # 주사제 — '주' 끝나는 medicine_name (정규식 ~ '주$' 와 등가)
    "%수액%",
    "%주입%",
    "%수출%",
    "%수의%",
    "%동물%",
    "%조영%",
    "%진단%",
    "%키트%",
)


# section 한국어 표시 (content prefix 용)
_SECTION_KR: dict[MedicineChunkSection, str] = {
    MedicineChunkSection.OVERVIEW: "개요",
    MedicineChunkSection.INTAKE_GUIDE: "복용법",
    MedicineChunkSection.DRUG_INTERACTION: "약물 상호작용",
    MedicineChunkSection.LIFESTYLE_INTERACTION: "생활 상호작용",
    MedicineChunkSection.ADVERSE_REACTION: "이상반응",
    MedicineChunkSection.SPECIAL_EVENT: "특수 상황",
}


# ── 파싱 + 청킹 ────────────────────────────────────────────────────
def _articles_for_medicine(med: MedicineInfo) -> list[tuple[Article, MedicineChunkSection]]:
    """medicine_info 의 3 raw XML 을 ARTICLE 리스트로 합쳐 section 분류한다.

    EE_DOC_DATA — 효능/효과 (대부분 OVERVIEW)
    UD_DOC_DATA — 용법/용량 (대부분 INTAKE_GUIDE)
    NB_DOC_DATA — 사용상의 주의 (DRUG_INTERACTION / ADVERSE_REACTION /
                  LIFESTYLE_INTERACTION / SPECIAL_EVENT 분기)
    """
    classified: list[tuple[Article, MedicineChunkSection]] = []

    for source_xml, default_section in (
        (med.ee_doc_data, MedicineChunkSection.OVERVIEW),
        (med.ud_doc_data, MedicineChunkSection.INTAKE_GUIDE),
        (med.nb_doc_data, None),
    ):
        for article in parse_doc_articles(source_xml):
            if not article.body and not article.title:
                continue
            section = classify_article_section(article.title) if default_section is None else default_section
            classified.append((article, section))

    return classified


def _estimate_tokens(text: str) -> int:
    """한국어 단순 추정 — 1.5자 = 1 토큰."""
    return int(len(text) / CHARS_PER_TOKEN) + 1


def _build_base_header(
    medicine_name: str,
    section: MedicineChunkSection,
    ingredients: list[str] | None,
) -> str:
    """청크 base 헤더 - sub-chunk 마다 동일하게 prepend.

    PLAN.md (RAG 재설계) §A — 성분 단위 검색 정확도를 위해 brand 이름과 함께
    [성분: ...] 헤더도 prepend. query 측 임베딩이 성분명을 포함하면 chunk
    측과 cosine 매칭이 ↑ (메타필터로 후보 좁힌 후 ranking 정확도 ↑).
    """
    section_kr = _SECTION_KR.get(section, section.value)
    parts = [f"[약: {medicine_name}]"]
    if ingredients:
        parts.append(f"[성분: {', '.join(ingredients)}]")
    parts.append(f"[{section_kr}]")
    return " ".join(parts)


def _format_chunk_content(
    medicine_name: str,
    section: MedicineChunkSection,
    article: Article,
    ingredients: list[str] | None = None,
) -> str:
    """단일 청크 입력 텍스트 (분할 안 됨 가정) — base header + title + body."""
    base_header = _build_base_header(medicine_name, section, ingredients)
    parts = [base_header]
    if article.title:
        parts.append(article.title)
    if article.body:
        parts.append(article.body)
    return "\n".join(parts)


# ── 의미 기반 splitter (Hierarchical: PARAGRAPH → list pattern → sentence → char) ──
# 한국 식약처 의약품 raw doc 의 실제 구조를 모방.
#
# 자르기 우선순위 (큰 단위 → 작은 단위 fallback):
#   Level 1: PARAGRAPH (`\n` 구분 — Article.body 가 이미 PARAGRAPH 들을 \n 으로 join)
#   Level 2: list pattern (`1)`, `(1)`, `가)`, `1.` 같은 항목 시작 정규식)
#   Level 3: 한국어 sentence (`다.`, `요.`, `이다.` 종결)
#   Level 4: char hard truncate (최후 보루)
#
# 모든 sub-chunk 에 ARTICLE title 을 prepend → list head 보존 (chunk[1] 도
# "5. 상호작용" 같은 헤더 유지) → retrieval 시 어느 sub-chunk 든 맥락 유지.

_LIST_ITEM_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"(?m)(?=^\d+\)\s)", re.UNICODE),  # 1)
    re.compile(r"(?m)(?=^\(\s*\d+\s*\)\s)", re.UNICODE),  # (1)
    re.compile(r"(?m)(?=^[가-힣]\)\s)", re.UNICODE),  # 가)
    re.compile(r"(?m)(?=^\d+\.\s)", re.UNICODE),  # 1.
)

# 한국어 평서문 종결어 — `(?<=다\.)\s+` 같은 lookbehind 로 종결어 직후 공백 위치에서 자름.
_KR_SENTENCE_BOUNDARY = re.compile(r"(?<=[다요]\.)\s+|(?<=다\.\n)|(?<=요\.\n)|(?<=이다\.)\s+", re.UNICODE)


def _truncate_to_char_limit(text: str, max_chars: int) -> str:
    """Char 단위 hard cap — 마지막 보루."""
    return text if len(text) <= max_chars else text[:max_chars]


def _hard_split_chars(text: str, max_tokens: int) -> list[str]:
    """모든 분할 시도 실패 시 char 단위로 자름."""
    max_chars = int(max_tokens * CHARS_PER_TOKEN)
    return [text[i : i + max_chars] for i in range(0, len(text), max_chars)] or [text]


def _pack_units(units: list[str], max_tokens: int, joiner: str = "\n") -> list[str]:
    """작은 단위 (PARAGRAPH/list item/sentence) 들을 max_tokens 안에서 packing.

    한 단위 자체가 max_tokens 초과면 재귀적으로 더 작은 단위로 분할.
    """
    chunks: list[str] = []
    current: list[str] = []
    current_tok = 0
    for raw in units:
        unit = raw.strip()
        if not unit:
            continue
        unit_tok = _estimate_tokens(unit)
        if unit_tok > max_tokens:
            # 단위 자체가 큼 → 한 단계 더 자른다 (recursion).
            if current:
                chunks.append(joiner.join(current))
                current, current_tok = [], 0
            chunks.extend(_split_semantic(unit, max_tokens))
            continue
        if current_tok + unit_tok > max_tokens and current:
            chunks.append(joiner.join(current))
            current, current_tok = [unit], unit_tok
        else:
            current.append(unit)
            current_tok += unit_tok
    if current:
        chunks.append(joiner.join(current))
    return chunks


def _try_split_by_list_pattern(text: str, max_tokens: int) -> list[str] | None:
    """List pattern (1), (1), 가), 1.) 으로 자르고 packing. 매칭 0 이면 None."""
    for pattern in _LIST_ITEM_PATTERNS:
        items = pattern.split(text)
        items = [i for i in items if i.strip()]
        if len(items) <= 1:
            continue
        return _pack_units(items, max_tokens, joiner="\n")
    return None


def _try_split_by_sentences(text: str, max_tokens: int) -> list[str] | None:
    """한국어 종결어 (다./요./이다.) 기준 sentence 분할 + packing."""
    sentences = _KR_SENTENCE_BOUNDARY.split(text)
    sentences = [s for s in sentences if s and s.strip()]
    if len(sentences) <= 1:
        return None
    return _pack_units(sentences, max_tokens, joiner=" ")


def _split_semantic(text: str, max_tokens: int) -> list[str]:
    r"""의미 기반 분할 (Hierarchical fallback chain).

    Level 1: PARAGRAPH (`\n` 단위) -> 작은 paragraph 들 packing
    Level 2: list pattern (1) (2) 가) 1.) - 항목 단위
    Level 3: 한국어 sentence (다./요./이다.)
    Level 4: char hard truncate (최후)
    """
    if _estimate_tokens(text) <= max_tokens:
        return [text]

    # Level 1: PARAGRAPH (Article.body 가 \n 로 PARAGRAPH 를 join 한 형태)
    paragraphs = [p for p in text.split("\n") if p.strip()]
    if len(paragraphs) > 1:
        return _pack_units(paragraphs, max_tokens, joiner="\n")

    # Level 2: list pattern (한 PARAGRAPH 안에 list 가 있는 경우)
    sub = _try_split_by_list_pattern(text, max_tokens)
    if sub:
        return sub

    # Level 3: 한국어 sentence
    sub = _try_split_by_sentences(text, max_tokens)
    if sub:
        return sub

    # Level 4: 마지막 보루 — char 단위
    return _hard_split_chars(text, max_tokens)


def _split_long_content(
    base_header: str,
    article_title: str,
    body: str,
    max_tokens: int = MAX_TOKENS_PER_CHUNK,
) -> list[str]:
    """ARTICLE → chunks. body 가 max_tokens 안이면 1 chunk, 아니면 의미 분할.

    모든 sub-chunk 는 base_header + article_title 을 prepend — list head
    보존 (예: 'X. 상호작용' 헤더가 모든 sub-chunk 에 들어가 retrieval 맥락 유지).
    """
    full = "\n".join(p for p in (base_header, article_title, body) if p)
    if _estimate_tokens(full) <= max_tokens:
        return [full]

    # body 만 의미 분할. header + title 의 토큰 만큼 sub-chunk 한도에서 차감.
    overhead = _estimate_tokens(base_header) + _estimate_tokens(article_title) + 5
    body_max = max(max_tokens - overhead, 200)
    sub_bodies = _split_semantic(body, body_max)

    # 각 sub-body 에 base_header + title prepend (의미 보존)
    return ["\n".join(p for p in (base_header, article_title, sub) if p) for sub in sub_bodies]


# ── content hash cache ─────────────────────────────────────────────────
# 재실행 시 동일 content 의 chunk 는 OpenAI 호출 skip — 비용 절감 + 재실행 안전.
# medicine_chunk(medicine_info_id, section, chunk_index) 의 기존 content 와
# SHA256 비교 → 동일하면 재임베딩 안 함.
def _content_hash(content: str) -> str:
    """SHA256 hex digest — chunk content 동일성 비교용."""
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


async def _load_existing_chunk_hashes(medicine_info_id: int) -> dict[tuple[str, int], str]:
    """기존 chunk 의 (section, chunk_index) → content hash 맵.

    재실행 시 unchanged chunk 의 OpenAI 호출 skip 용. content 가 같으면
    재임베딩 안 하고 token_count 만 재산정 (DB 에 그대로 보존).
    """
    rows = await MedicineChunk.filter(medicine_info_id=medicine_info_id).values("section", "chunk_index", "content")
    return {(r["section"], r["chunk_index"]): _content_hash(r["content"] or "") for r in rows}


async def _load_curated_medicine_ids(top_n: int) -> list[int]:
    """큐레이션 86 활성성분 x 성분당 top-N brand 의 medicine_info.id list.

    raw doc 풍부 (≥1000 chars) + 일반인 사용 가능 (주사·수출·수의·진단 제외).
    같은 ingredient 안에서는 doc_total_len DESC 로 ranking, top-N 만.
    """
    conn = Tortoise.get_connection("default")
    sql = r"""
        WITH filtered AS (
            SELECT mi.id,
                   ing.mtral_name AS ingredient,
                   LENGTH(COALESCE(mi.ee_doc_data,'') ||
                          COALESCE(mi.ud_doc_data,'') ||
                          COALESCE(mi.nb_doc_data,'')) AS doc_len
            FROM medicine_info mi
            JOIN medicine_ingredient ing ON ing.medicine_info_id = mi.id
            WHERE ing.mtral_name = ANY($1::text[])
              AND mi.medicine_name NOT ILIKE '%주사%'
              AND mi.medicine_name NOT ILIKE '%수액%'
              AND mi.medicine_name NOT ILIKE '%주입%'
              AND mi.medicine_name NOT ILIKE '%수출%'
              AND mi.medicine_name NOT ILIKE '%수의%'
              AND mi.medicine_name NOT ILIKE '%동물%'
              AND mi.medicine_name NOT ILIKE '%조영%'
              -- 주사제 제외 — 다음 패턴 모두 잡음:
              --   "...주"        ('주' 끝)
              --   "...주(...)"   ('프리브로펜주(이부프로펜)' 같이 괄호 성분 표기)
              --   "...주 ..."    ('주' 뒤 공백 — 드물지만 안전)
              AND mi.medicine_name !~ '주(\([^)]*\))?\s*$'
              AND LENGTH(COALESCE(mi.ee_doc_data,'') ||
                         COALESCE(mi.ud_doc_data,'') ||
                         COALESCE(mi.nb_doc_data,'')) >= 1000
        ),
        ranked AS (
            SELECT id, ingredient, doc_len,
                   ROW_NUMBER() OVER (PARTITION BY ingredient ORDER BY doc_len DESC, id) AS rk
            FROM filtered
        )
        SELECT DISTINCT id FROM ranked WHERE rk <= $2 ORDER BY id
    """
    _, rows = await conn.execute_query(sql, [list(CORE_PRESCRIPTION_INGREDIENTS), top_n])
    return [int(r["id"]) for r in rows]


async def _load_ingredients_for_medicine(medicine_info_id: int) -> list[str]:
    """medicine_ingredient.mtral_name list (None 제거 + dedupe + 등록 순서)."""
    rows = (
        await MedicineIngredient
        .filter(medicine_info_id=medicine_info_id)
        .order_by("mtral_sn")
        .values_list("mtral_name", flat=True)
    )
    seen: set[str] = set()
    out: list[str] = []
    for name in rows:
        if not name or name in seen:
            continue
        seen.add(name)
        out.append(name)
    return out


def _build_chunks_for_medicine(
    med: MedicineInfo,
    ingredients: list[str],
) -> list[tuple[MedicineChunkSection, int, str, int]]:
    """한 medicine 의 모든 (section, chunk_index, content, token_count) 리스트.

    의미 기반 분할 (Hierarchical: PARAGRAPH → list pattern → sentence → char):
      - 한 ARTICLE 이 토큰 한도 안이면 1 chunk 그대로 (의미 단위 유지)
      - 큰 ARTICLE 만 의미 단위 분할 + 모든 sub-chunk 에 ARTICLE title prepend
        → list head ('5. 상호작용') 가 보존되어 retrieval 시 어느 sub-chunk
        든 맥락 유지 (이전 줄바꿈 단위 분할의 의미 누락 회귀 회피).
    """
    base_section_counter: dict[MedicineChunkSection, int] = {}
    out: list[tuple[MedicineChunkSection, int, str, int]] = []

    for article, section in _articles_for_medicine(med):
        base_header = _build_base_header(med.medicine_name, section, ingredients)
        for sub in _split_long_content(base_header, article.title, article.body):
            idx = base_section_counter.get(section, 0)
            base_section_counter[section] = idx + 1
            out.append((section, idx, sub, _estimate_tokens(sub)))

    return out


# ── OpenAI Embedding 호출 (retry) ──────────────────────────────────
async def _embed_with_retry(client: AsyncOpenAI, texts: list[str]) -> list[list[float]]:
    """Batch input 을 한 번에 임베딩, rate limit / connection 오류 시 retry."""
    backoff = INITIAL_BACKOFF
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            response = await client.embeddings.create(
                model=EMBEDDING_MODEL,
                input=texts,
                dimensions=EMBEDDING_DIMENSIONS,
            )
            return [d.embedding for d in response.data]
        except Exception as exc:
            if attempt >= MAX_RETRIES:
                logger.exception("Embedding failed after %d attempts", MAX_RETRIES)
                raise
            logger.warning(
                "Embedding attempt %d/%d failed (%s: %s) — retry in %.1fs",
                attempt,
                MAX_RETRIES,
                type(exc).__name__,
                str(exc)[:100],
                backoff,
            )
            await asyncio.sleep(backoff)
            backoff *= 2

    raise RuntimeError("unreachable")


# ── OpenAI Batch API 통합 (50% 할인, 24h 내 완료) ─────────────────────
# https://platform.openai.com/docs/guides/batch
# 흐름: chunks 모두 빌드 -> JSONL 파일 작성 -> /v1/files 업로드
#       -> /v1/batches 제출 -> polling (60s 간격) -> 결과 다운로드 + INSERT.
# custom_id format: "{medicine_info_id}_{section}_{chunk_index}" — 결과 매칭용.

_BATCH_POLL_INTERVAL = 60.0  # sec — completed 까지 polling 간격
_BATCH_TERMINAL_STATES = ("completed", "failed", "expired", "cancelled")


def _custom_id_for(med_id: int, section: MedicineChunkSection, chunk_index: int) -> str:
    """Batch API custom_id (max 64 chars) — 결과 line 매칭용 unique key."""
    return f"{med_id}_{section.value}_{chunk_index}"


async def _submit_batch_and_wait(
    client: AsyncOpenAI,
    requests: list[dict[str, Any]],
) -> dict[str, list[float]]:
    """Batch API 제출 + 완료 대기 + custom_id -> embedding dict 반환.

    Args:
        client: AsyncOpenAI 인스턴스 (이미 초기화된 OpenAI 클라이언트).
        requests: JSONL 줄 dict 리스트. 각 줄은 OpenAI batch input format.

    Returns:
        dict: custom_id -> 3072d embedding vector. 실패 item 은 dict 에서 제외.
    """
    if not requests:
        return {}

    # 1. JSONL 파일 작성 (file IO — async 안에서 sync open 사용은 1회성 short-lived 라 OK)
    jsonl_path = Path("/tmp/embed_batch_input.jsonl")
    body = "\n".join(json.dumps(req, ensure_ascii=False) for req in requests) + "\n"
    jsonl_path.write_text(body, encoding="utf-8")  # noqa: ASYNC240  # 1회성 short-lived
    logger.info("[Batch] JSONL written: %d requests, path=%s", len(requests), jsonl_path)

    # 2. 파일 업로드
    with jsonl_path.open("rb") as f:  # noqa: ASYNC230  # 1회성 short-lived
        upload = await client.files.create(file=f, purpose="batch")
    logger.info("[Batch] file uploaded: id=%s bytes=%d", upload.id, upload.bytes)

    # 3. Batch job 제출
    batch = await client.batches.create(
        input_file_id=upload.id,
        endpoint="/v1/embeddings",
        completion_window="24h",
        metadata={"purpose": "medicine_chunk_embedding"},
    )
    logger.info("[Batch] submitted: id=%s status=%s", batch.id, batch.status)

    # 4. polling — completed/failed/expired/cancelled 까지
    while batch.status not in _BATCH_TERMINAL_STATES:
        await asyncio.sleep(_BATCH_POLL_INTERVAL)
        batch = await client.batches.retrieve(batch.id)
        rc = batch.request_counts
        logger.info(
            "[Batch] status=%s completed=%d/%d failed=%d",
            batch.status,
            rc.completed if rc else 0,
            rc.total if rc else len(requests),
            rc.failed if rc else 0,
        )

    if batch.status != "completed":
        msg = f"Batch terminal state={batch.status} errors={getattr(batch, 'errors', None)}"
        raise RuntimeError(msg)

    # 5. 결과 다운로드
    if not batch.output_file_id:
        raise RuntimeError("Batch completed but output_file_id is empty")
    response = await client.files.content(batch.output_file_id)
    text = response.text if hasattr(response, "text") else response.read().decode("utf-8")

    results: dict[str, list[float]] = {}
    failed_count = 0
    for line in text.split("\n"):
        if not line.strip():
            continue
        obj = json.loads(line)
        cid = obj.get("custom_id")
        if obj.get("error") or obj.get("response", {}).get("status_code") != 200:
            failed_count += 1
            logger.warning("[Batch] item failed cid=%s err=%s", cid, obj.get("error"))
            continue
        embedding = obj["response"]["body"]["data"][0]["embedding"]
        results[cid] = embedding

    logger.info("[Batch] results: ok=%d failed=%d", len(results), failed_count)
    return results


async def process_medicines_batch_api(
    *,
    batch_size: int,
    medicine_ids: list[int] | None,
    resume_from: int,
) -> None:
    """Batch API 모드 — 모든 chunks 한 번에 빌드 + cache miss 만 batch 제출.

    표준 모드 (process_medicines) 와 동일한 chunks 빌드 + cache 흐름이지만,
    OpenAI Embedding 호출을 한 번의 Batch API submit 으로 통합. 50% 할인 +
    24h 내 완료 (보통 1-3시간).
    """
    api_key = config.OPENAI_API_KEY
    if not api_key:
        msg = "OPENAI_API_KEY 미설정 — Batch API 호출 필수"
        raise SystemExit(msg)
    client = AsyncOpenAI(api_key=api_key)

    # 1. medicines + chunks 빌드 (cache miss 만 collect)
    if medicine_ids is not None:
        meds_query = MedicineInfo.filter(id__in=medicine_ids).order_by("id")
        total = len(medicine_ids)
    else:
        meds_query = MedicineInfo.filter(id__gte=resume_from).order_by("id")
        total = await MedicineInfo.filter(id__gte=resume_from).count()

    logger.info("[Batch] scope: %d medicines, scanning chunks…", total)

    requests: list[dict[str, Any]] = []
    pending_rows: list[tuple[int, MedicineChunkSection, int, str, int, list[str]]] = []
    cache_hits = 0
    seen_meds = 0

    offset = 0
    while True:
        page = await meds_query.offset(offset).limit(batch_size).all()
        if not page:
            break
        for med in page:
            ingredients = await _load_ingredients_for_medicine(med.id)
            chunks = _build_chunks_for_medicine(med, ingredients)
            if not chunks:
                continue
            existing = await _load_existing_chunk_hashes(med.id)
            for sec, idx, content, tok in chunks:
                if existing.get((sec.value, idx)) == _content_hash(content):
                    cache_hits += 1
                    continue
                custom_id = _custom_id_for(med.id, sec, idx)
                requests.append({
                    "custom_id": custom_id,
                    "method": "POST",
                    "url": "/v1/embeddings",
                    "body": {
                        "model": EMBEDDING_MODEL,
                        "input": content,
                        "dimensions": EMBEDDING_DIMENSIONS,
                    },
                })
                pending_rows.append((med.id, sec, idx, content, tok, ingredients))
        seen_meds += len(page)
        logger.info(
            "[Batch] scan: %d/%d cache_hits=%d pending=%d",
            seen_meds,
            total,
            cache_hits,
            len(requests),
        )
        offset += batch_size

    if not requests:
        logger.info("[Batch] 모든 chunks cache hit — Batch API 호출 skip")
        return

    # 2. Batch API 제출 + 결과 수신
    logger.info("[Batch] submitting %d embedding requests (cache_hits=%d)", len(requests), cache_hits)
    embeddings_by_cid = await _submit_batch_and_wait(client, requests)

    # 3. INSERT — pending_rows 의 custom_id 와 매칭
    insert_rows: list[tuple[int, MedicineChunkSection, int, str, int, list[float], list[str]]] = []
    for mid, sec, idx, content, tok, ingredients in pending_rows:
        cid = _custom_id_for(mid, sec, idx)
        emb = embeddings_by_cid.get(cid)
        if emb is None:
            continue  # batch item failed
        insert_rows.append((mid, sec, idx, content, tok, emb, ingredients))

    # INSERT 도 batch 단위로 (postgres parameter limit 회피)
    inserted_total = 0
    insert_batch = 50
    for off in range(0, len(insert_rows), insert_batch):
        sub = insert_rows[off : off + insert_batch]
        async with in_transaction("default"):
            inserted_total += await _insert_chunks_batch(sub)

    tokens_total = sum(r[4] for r in pending_rows if _custom_id_for(r[0], r[1], r[2]) in embeddings_by_cid)
    cost_batch = tokens_total / 1_000_000 * EMBEDDING_PRICE_PER_1M * 0.5
    cost_std = tokens_total / 1_000_000 * EMBEDDING_PRICE_PER_1M
    logger.info(
        "[Batch] DONE inserted=%d cache_hits=%d tokens=%dK cost_batch=$%.2f cost_std=$%.2f",
        inserted_total,
        cache_hits,
        tokens_total // 1000,
        cost_batch,
        cost_std,
    )


# ── INSERT (raw SQL, vector pgvector 형식) ──────────────────────────
def _vector_literal(embedding: list[float]) -> str:
    """Pgvector 의 vector(N) 입력 형식 — '[v1,v2,...]' 문자열."""
    return "[" + ",".join(f"{v:.6f}" for v in embedding) + "]"


async def _insert_chunks_batch(
    rows: list[tuple[int, MedicineChunkSection, int, str, int, list[float], list[str]]],
) -> int:
    """rows: (medicine_info_id, section, chunk_index, content, token_count, embedding, ingredients)
    멱등성을 위해 ON CONFLICT (medicine_info_id, section, chunk_index) DO UPDATE
    - 본 PR-A 재임베딩에서는 기존 row 의 content/embedding/ingredients 도
    새 형식으로 갱신해야 하므로 DO NOTHING 대신 DO UPDATE.
    """
    if not rows:
        return 0

    placeholders: list[str] = []
    params: list = []
    for i, (mid, section, idx, content, tok, emb, ingredients) in enumerate(rows):
        base = i * 8
        placeholders.append(
            f"(${base + 1}, ${base + 2}, ${base + 3}, ${base + 4}, ${base + 5},"
            f" ${base + 6}::halfvec, ${base + 7}, ${base + 8}::jsonb)"
        )
        params.extend([
            mid,
            section.value,
            idx,
            content,
            tok,
            _vector_literal(emb),
            EMBEDDING_MODEL,
            json.dumps(ingredients, ensure_ascii=False),
        ])

    sql = f"""
        INSERT INTO medicine_chunk
            (medicine_info_id, section, chunk_index, content, token_count,
             embedding, model_version, ingredients)
        VALUES {",".join(placeholders)}
        ON CONFLICT (medicine_info_id, section, chunk_index) DO UPDATE SET
            content = EXCLUDED.content,
            token_count = EXCLUDED.token_count,
            embedding = EXCLUDED.embedding,
            model_version = EXCLUDED.model_version,
            ingredients = EXCLUDED.ingredients,
            updated_at = NOW()
    """  # noqa: S608

    from tortoise import connections

    await connections.get("default").execute_query(sql, params)
    return len(rows)


# ── 메인 처리 루프 ───────────────────────────────────────────────────
async def process_medicines(  # noqa: PLR0915  # batch loop + per-medicine + progress 통합 — 분리 시 가독성 손해
    *,
    batch_size: int,
    concurrency: int,
    resume_from: int,
    medicine_ids: list[int] | None = None,
) -> None:
    """모든 medicine_info 를 순회하며 청킹 + 임베딩 + INSERT.

    Args:
        batch_size: medicine_info 페이지 크기.
        concurrency: 동시 medicine 처리 병렬도 (OpenAI 호출 병렬 = 이 값).
        resume_from: 시작 medicine_info.id (재시작용). medicine_ids 지정 시 무시.
        medicine_ids: 특정 ID 만 처리 (None 이면 resume_from 이후 모두).
    """
    api_key = config.OPENAI_API_KEY
    if not api_key:
        msg = "OPENAI_API_KEY 미설정 — 본 batch 는 OpenAI 호출 필수"
        raise SystemExit(msg)
    client = AsyncOpenAI(api_key=api_key)

    if medicine_ids is not None:
        total = len(medicine_ids)
        scope_desc = f"ids={len(medicine_ids)}"
    else:
        total = await MedicineInfo.filter(id__gte=resume_from).count()
        scope_desc = f"resume_from={resume_from}"
    logger.info(
        "Embedding %d medicines (batch=%d, concurrency=%d, %s, model=%s, dim=%d)",
        total,
        batch_size,
        concurrency,
        scope_desc,
        EMBEDDING_MODEL,
        EMBEDDING_DIMENSIONS,
    )

    semaphore = asyncio.Semaphore(concurrency)
    processed = 0
    inserted_total = 0
    tokens_total = 0
    cache_hits_total = 0
    start = time.time()

    async def _process_one(med: MedicineInfo) -> tuple[int, int, int]:
        """Returns: (inserted, tokens_for_billing, cache_hits)."""
        async with semaphore:
            ingredients = await _load_ingredients_for_medicine(med.id)
            chunks = _build_chunks_for_medicine(med, ingredients)
            if not chunks:
                return 0, 0, 0

            # ── content hash cache: 기존 chunk 와 동일하면 OpenAI 호출 skip ──
            existing = await _load_existing_chunk_hashes(med.id)
            new_indices: list[int] = []
            new_contents: list[str] = []
            cache_hits = 0
            for i, (sec, idx, content, _tok) in enumerate(chunks):
                if existing.get((sec.value, idx)) == _content_hash(content):
                    cache_hits += 1
                    continue
                new_indices.append(i)
                new_contents.append(content)

            # 임베딩 호출 — cache miss 만
            new_embeddings: list[list[float]] = []
            for offset in range(0, len(new_contents), EMBED_BATCH_SIZE):
                sub = new_contents[offset : offset + EMBED_BATCH_SIZE]
                vecs = await _embed_with_retry(client, sub)
                new_embeddings.extend(vecs)

            # cache miss 만 INSERT/UPDATE — cache hit 은 DB row 그대로 보존
            rows = [
                (med.id, chunks[i][0], chunks[i][1], chunks[i][2], chunks[i][3], emb, ingredients)
                for i, emb in zip(new_indices, new_embeddings, strict=True)
            ]
            if rows:
                async with in_transaction("default"):
                    affected = await _insert_chunks_batch(rows)
            else:
                affected = 0
            billed_tokens = sum(chunks[i][3] for i in new_indices)
            return affected, billed_tokens, cache_hits

    offset = 0
    while True:
        if medicine_ids is not None:
            ids_page = medicine_ids[offset : offset + batch_size]
            if not ids_page:
                break
            page = await MedicineInfo.filter(id__in=ids_page).order_by("id").all()
        else:
            page = await MedicineInfo.filter(id__gte=resume_from).order_by("id").offset(offset).limit(batch_size).all()
        if not page:
            break

        results = await asyncio.gather(
            *[_process_one(m) for m in page],
            return_exceptions=True,
        )

        for med, result in zip(page, results, strict=True):
            if isinstance(result, BaseException):
                logger.error("medicine_info id=%d 처리 실패: %s: %s", med.id, type(result).__name__, result)
                continue
            inserted, tokens, cache_hits = result
            inserted_total += inserted
            tokens_total += tokens
            cache_hits_total += cache_hits

        processed += len(page)
        elapsed = time.time() - start
        rate = processed / max(elapsed, 1)
        eta_min = (total - processed) / max(rate, 0.001) / 60
        cost_est = tokens_total / 1_000_000 * EMBEDDING_PRICE_PER_1M
        logger.info(
            "Progress: %d/%d (%.1f%%) chunks=%d cache_hits=%d tokens=%dK cost=$%.2f rate=%.1f/s eta=%.1fmin",
            processed,
            total,
            processed / max(total, 1) * 100,
            inserted_total,
            cache_hits_total,
            tokens_total // 1000,
            cost_est,
            rate,
            eta_min,
        )

        offset += batch_size

    logger.info(
        "Done — medicines=%d chunks_inserted=%d cache_hits=%d tokens=%dK cost=$%.2f elapsed=%.1fmin",
        processed,
        inserted_total,
        cache_hits_total,
        tokens_total // 1000,
        tokens_total / 1_000_000 * EMBEDDING_PRICE_PER_1M,
        (time.time() - start) / 60,
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="medicine_info → medicine_chunk 청킹 + 임베딩 batch (1회성)",
    )
    parser.add_argument("--batch", type=int, default=50, help="medicine_info 페이지 크기 (default: 50)")
    parser.add_argument(
        "--concurrency",
        type=int,
        default=5,
        help="동시 medicine 처리 병렬도 (default: 5). OpenAI rate limit 따라 조정",
    )
    parser.add_argument("--resume-from", type=int, default=0, help="시작 medicine_info.id (재시작용)")
    parser.add_argument(
        "--medicine-ids",
        type=str,
        default=None,
        help="콤마 구분 medicine_info.id 목록 — 이 인자가 있으면 resume-from 무시하고 해당 ID 만 처리 (예: 1,5,12,42)",
    )
    parser.add_argument(
        "--name-like",
        type=str,
        default=None,
        help="콤마 구분 ILIKE 패턴 (medicine_name + item_eng_name 매칭)",
    )
    parser.add_argument(
        "--curated",
        action="store_true",
        help="큐레이션 모드 — CORE_PRESCRIPTION_INGREDIENTS 86종 x 성분당 top-N brand 만 임베딩 "
        "(일반인 사용 가능 + 처방 빈도 높은 brand 우선). 비용 최소화 (옵션 B).",
    )
    parser.add_argument(
        "--top-n-per-ingredient",
        type=int,
        default=10,
        help="--curated 모드에서 성분당 brand 상한 (default: 10). raw doc 길이 desc 정렬 후 top-N.",
    )
    parser.add_argument(
        "--use-batch-api",
        action="store_true",
        help="OpenAI Batch API 모드 (50%% 할인, 24h 내 완료). 모든 cache miss chunks 를 "
        "한 번의 batch 로 제출 + polling. concurrency 옵션은 무시됨.",
    )
    return parser.parse_args()


async def main_async(args: argparse.Namespace) -> None:
    await Tortoise.init(config=TORTOISE_ORM)
    try:
        ids: list[int] | None = None
        if args.curated:
            ids = await _load_curated_medicine_ids(args.top_n_per_ingredient)
            logger.info(
                "큐레이션 모드 — 86 활성성분 x top-%d brand = %d medicines",
                args.top_n_per_ingredient,
                len(ids),
            )
        elif args.medicine_ids:
            ids = [int(x.strip()) for x in args.medicine_ids.split(",") if x.strip()]
            logger.info("ID 목록 모드 — %d medicines", len(ids))
        elif args.name_like:
            # ── 부분 일치 패턴 검색 (`%token%` 자동 wrap) ──
            # Tortoise ORM 의 ILIKE 룩업은 ``__ilike`` 가 아닌 ``__icontains``.
            # ``__ilike`` 는 FieldError: Unknown filter param 발생.
            # ``__icontains`` 는 자동으로 % wrap → 사용자 입력의 % 는 strip 필요 없음.
            patterns = [p.strip().strip("%") for p in args.name_like.split(",") if p.strip()]
            from tortoise.expressions import Q

            cond = Q()
            for p in patterns:
                cond |= Q(medicine_name__icontains=p) | Q(item_eng_name__icontains=p)
            matched = await MedicineInfo.filter(cond).values_list("id", flat=True)
            ids = list(matched)
            logger.info("name-like 매칭 — %d medicines (patterns=%s)", len(ids), patterns)

        if args.use_batch_api:
            await process_medicines_batch_api(
                batch_size=args.batch,
                medicine_ids=ids,
                resume_from=args.resume_from,
            )
        else:
            await process_medicines(
                batch_size=args.batch,
                concurrency=args.concurrency,
                resume_from=args.resume_from,
                medicine_ids=ids,
            )
    finally:
        await Tortoise.close_connections()


def main() -> None:
    args = parse_args()
    asyncio.run(main_async(args))


if __name__ == "__main__":
    main()

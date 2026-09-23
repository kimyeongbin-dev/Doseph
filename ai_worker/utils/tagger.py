"""Interaction tag auto-tagger module.

This module assigns interaction_tags (JSONB) to medicine_chunk rows
based on rule-based keyword matching against interaction_tags.json.
Designed to cover ~80% of tagging cases; the remaining ~20% can be
optionally promoted to an LLM fallback.

The tagger is intentionally simple and synchronous — it runs inside
the chunking pipeline batch, not on the request path.

Reference:
    - Seed dictionary: ai_worker/data/interaction_tags.json (v1-seed)
    - 사라진 계획 §1.5.6 v2 (schema lock ④)
    🔑 정본 = `ai_worker/data/interaction_tags.json`(v1-seed)과 이 모듈.
"""

import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

# ── 시드 사전 경로 (ai_worker/data/interaction_tags.json) ──────────────
_TAG_DICT_PATH = Path(__file__).resolve().parent.parent / "data" / "interaction_tags.json"

# ── 사전 메타 키 (실제 태그가 아니므로 로딩 시 제외) ───────────────────
_META_KEYS = frozenset({"_comment", "_version", "_schema_lock"})


def load_tag_dictionary(path: Path | None = None) -> dict[str, list[str]]:
    """Load the interaction tag seed dictionary from JSON.

    Args:
        path: Optional override path. Defaults to ai_worker/data/interaction_tags.json.

    Returns:
        Mapping of tag key ("prefix:value") to list of keyword strings.

    Raises:
        FileNotFoundError: If the seed dictionary is missing.
        json.JSONDecodeError: If the JSON is malformed.
    """
    target = path or _TAG_DICT_PATH
    with target.open(encoding="utf-8") as f:
        raw: dict[str, object] = json.load(f)

    return {key: value for key, value in raw.items() if key not in _META_KEYS and isinstance(value, list)}


# ── 모듈 로드 시점에 시드 사전을 한 번만 읽음 (배치 재사용) ──────────
_TAG_DICT: dict[str, list[str]] = load_tag_dictionary()


def tag_chunk(content: str, dictionary: dict[str, list[str]] | None = None) -> list[str]:
    """Extract interaction tags from chunk content via keyword matching.

    # ── 규칙 기반 태깅 ────────────────────────────────────────────────
    # 흐름: 시드 사전 로드 -> content 소문자 변환 -> 각 태그 키의
    #       키워드 중 하나라도 포함되면 해당 태그 키를 결과에 추가
    # 주의: 단순 부분 문자열 매칭이므로 오탐 가능성 존재. 필요 시
    #       LLM 폴백(tag_chunk_with_llm)으로 보강한다.

    Args:
        content: Chunk body text to analyse.
        dictionary: Optional override tag dictionary. Uses preloaded
            module-level dictionary when None.

    Returns:
        Sorted list of unique tag keys matched for this chunk.
    """
    if not content:
        return []

    tag_dict = dictionary if dictionary is not None else _TAG_DICT
    lowered = content.lower()
    matched: set[str] = set()

    for tag_key, keywords in tag_dict.items():
        for keyword in keywords:
            if keyword.lower() in lowered:
                matched.add(tag_key)
                break

    return sorted(matched)


def summarise_tags(tags: list[str]) -> dict[str, list[str]]:
    """Group tags by prefix for inspection/debugging.

    # ── 태그 요약 (카테고리별 집계) ──────────────────────────────────
    # 흐름: tag 문자열을 ':'로 분리 -> prefix 기준으로 묶음
    # 용도: 디버그 로그, 청크별 태깅 품질 리뷰, 통계

    Args:
        tags: Flat list of tag keys (e.g. ["food:dairy", "alcohol"]).

    Returns:
        Dictionary grouping tags by prefix. Tags without prefix go under "_untagged".
    """
    grouped: dict[str, list[str]] = {}
    for tag in tags:
        prefix, _, value = tag.partition(":")
        bucket = prefix if value else "_untagged"
        grouped.setdefault(bucket, []).append(value or prefix)
    return grouped

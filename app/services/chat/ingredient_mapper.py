"""brand 약 이름 → 활성성분 매핑 service (DB lookup, 유사도 X).

`plan/2026-08-11_rag-query-rewriter-plan.md` (ingredient-grounded) §B - 의약품 도메인의 본질은 성분 단위
(병용금기, 부작용, 주의사항이 성분으로 정의됨). 사용자 medication 또는
질의에 등장하는 brand 이름을 medicine_info ↔ medicine_ingredient SQL lookup
으로 활성성분명 list 로 변환한다.

흐름:
  brand_name -> medicine_info ILIKE 매칭
             -> medicine_ingredient join
             -> mtral_name list (활성성분)

본 service 는 유사도 검색을 사용하지 않는다. 정확 매핑 (SQL ILIKE) 로 충분
하며, fuzzy 매칭은 brand alias dictionary 별 PR 에서 보완 예정.
"""

import logging

from tortoise import connections

logger = logging.getLogger(__name__)


# OCR / 사용자 입력의 brand name 은 다양한 노이즈를 포함 - 매핑 전 정규화.
_NOISE_SUFFIXES = (
    "(이럴때퍼지매칭을하지)",
    "(수출용)",
    "(수출명)",
)


def _normalize_brand(name: str) -> str:
    """Brand 이름의 OCR/표기 노이즈 제거 (괄호, 콤마 뒤 부분, 공백)."""
    cleaned = name.strip()
    for suffix in _NOISE_SUFFIXES:
        cleaned = cleaned.replace(suffix, "")
    # ',' 또는 첫 '(' 앞부분이 핵심 brand
    if "," in cleaned:
        cleaned = cleaned.split(",", 1)[0]
    if "(" in cleaned:
        cleaned = cleaned.split("(", 1)[0]
    return cleaned.strip()


async def map_brands_to_ingredients(brand_names: list[str]) -> dict[str, list[str]]:
    """Brand 이름 list 를 ``{brand: [ingredient1, ingredient2, ...]}`` 로 매핑.

    Args:
        brand_names: 사용자 medication 또는 질의에서 추출한 brand 이름 list.
            중복 / 빈 문자열 가능 - 내부에서 dedupe.

    Returns:
        ``{원본 brand: 매핑된 활성성분 list}``. 매핑 실패한 brand 는 빈 list.
        매핑은 medicine_info ILIKE prefix/contains 우선순위로:
          1. medicine_name 정확 일치
          2. medicine_name 이 brand 로 시작 (LIKE 'brand%')
          3. medicine_name 이 brand 를 포함 (ILIKE '%brand%')
        그 후 medicine_ingredient join 으로 mtral_name 추출 (dedupe).
    """
    if not brand_names:
        return {}

    unique_brands = list({_normalize_brand(n) for n in brand_names if n and n.strip()})
    if not unique_brands:
        return {}

    sql = """
        WITH input_brands AS (
            SELECT unnest($1::text[]) AS brand
        ),
        matched AS (
            SELECT DISTINCT ON (ib.brand, mi.id)
                ib.brand,
                mi.id AS mi_id
            FROM input_brands ib
            JOIN medicine_info mi
              ON mi.medicine_name = ib.brand
              OR mi.medicine_name ILIKE ib.brand || '%'
              OR mi.medicine_name ILIKE '%' || ib.brand || '%'
        )
        SELECT m.brand, mig.mtral_name
        FROM matched m
        JOIN medicine_ingredient mig ON mig.medicine_info_id = m.mi_id
        WHERE mig.mtral_name IS NOT NULL
        ORDER BY m.brand, mig.mtral_name;
    """
    rows = await connections.get("default").execute_query_dict(sql, [unique_brands])

    result: dict[str, list[str]] = {brand: [] for brand in unique_brands}
    for row in rows:
        brand = row["brand"]
        ingr = row["mtral_name"]
        if ingr not in result[brand]:
            result[brand].append(ingr)

    # 원본 brand_name 키로 다시 매핑 (정규화 전 이름 보존)
    final: dict[str, list[str]] = {}
    for original in brand_names:
        if not original or not original.strip():
            continue
        normalized = _normalize_brand(original)
        final[original] = result.get(normalized, [])

    logger.info(
        "[IngredientMapper] %d brands -> %d matched (any ingredient)",
        len(final),
        sum(1 for v in final.values() if v),
    )
    return final


def format_ingredient_mapping_section(mapping: dict[str, list[str]]) -> str:
    """매핑 결과를 LLM context 용 markdown 으로 조립한다.

    빈 mapping 또는 모든 brand 가 매핑 실패한 경우 빈 문자열 반환 (섹션 생략).
    """
    if not mapping:
        return ""
    lines: list[str] = []
    for brand, ingredients in mapping.items():
        if ingredients:
            lines.append(f"- {brand} → 성분: {', '.join(ingredients)}")
        else:
            lines.append(f"- {brand} → 성분 매핑 실패")
    if not lines:
        return ""
    return "[용어 매핑]\n" + "\n".join(lines)

"""OCR 후보 토큰을 medicine_info DB 와 매칭한다. (아키텍트 패러다임 시프트 버전)"""

import asyncio
import json
import logging

from tortoise import Tortoise

from ai_worker.core.openai_client import get_openai_client
from app.db.databases import TORTOISE_ORM
from app.dtos.ocr import ExtractedMedicine
from app.repositories.medicine_info_repository import MedicineInfoRepository

logger = logging.getLogger(__name__)

_FUZZY_THRESHOLD = 0.3
_FUZZY_LIMIT = 1


async def search_candidates_in_open_db(candidates: list[str]) -> list[ExtractedMedicine]:
    if not candidates:
        return []

    full_text = " ".join(candidates)
    logger.info("Reconstructed OCR Text Length: %d", len(full_text))

    # 💡 LLM이 이름, 용량, 타입을 분리해서 가져옵니다.
    extracted_items = await _extract_medicines_with_llm(full_text)
    logger.info("LLM Extracted Items: %s", extracted_items)

    matched: list[ExtractedMedicine] = []
    seen_names: set[str] = set()
    repo = MedicineInfoRepository()
    await repo.ensure_pg_trgm()

    db_match_count = 0
    for item in extracted_items:
        # LLM 이 키 자체는 반환했지만 값이 None 인 경우도 있어 `or ""` 로 정리.
        # 이전 구현은 `get(k, default)` 만 써서 None 이 그대로 흘러가 "None" 문자열 leak 발생.
        pure_name = item.get("name") or ""
        strength = item.get("strength") or ""
        item_type = item.get("type") or "의약품"
        dose = item.get("dose")
        daily_count = item.get("daily_count")
        total_days = item.get("total_days")
        instruction = item.get("instruction") or "식후 30분"

        if not pure_name:
            continue

        if await _match_clean_name(repo, pure_name, strength, item_type, matched, seen_names):
            db_match_count += 1
        elif pure_name not in seen_names:
            seen_names.add(pure_name)

            # 💡 동훈 님 요청사항: 문구 변경 및 용량 부착
            final_display_name = f"{pure_name} {strength}".strip()
            if item_type == "영양제":
                display_category = "영양제/보충제"
                final_display_name += " (영양제 성분 포함)"
            else:
                display_category = "미분류(수동확인)"

            matched.append(
                ExtractedMedicine(
                    medicine_name=final_display_name,
                    category=display_category,
                    raw_ocr_name=pure_name,
                    is_llm_corrected=True,
                    match_score=0.5,
                    dose_per_intake=str(dose) if dose else "",
                    daily_intake_count=int(daily_count) if daily_count else None,
                    total_intake_days=int(total_days) if total_days else None,
                    intake_instruction=instruction,
                )
            )

    logger.info("Final Matching: %d LLM names -> %d matched to DB", len(extracted_items), db_match_count)
    return matched


def match_candidates_to_medicines(candidates: list[str]) -> list[ExtractedMedicine]:
    return asyncio.run(_run_with_db_lifecycle(candidates))


async def _run_with_db_lifecycle(candidates: list[str]) -> list[ExtractedMedicine]:
    await Tortoise.init(config=TORTOISE_ORM)
    try:
        return await search_candidates_in_open_db(candidates)
    finally:
        await Tortoise.close_connections()


# 💡 strength(용량)과 item_type을 파라미터로 추가로 받습니다.
async def _match_clean_name(
    repo: MedicineInfoRepository,
    pure_name: str,
    strength: str,
    item_type: str,
    matched: list[ExtractedMedicine],
    seen_names: set[str],
) -> bool:

    # 조립된 최종 화면 표시용 이름 (이름 + 용량 + 영양제 꼬리표)
    def _build_display_name(base_name: str) -> str:
        name_with_strength = f"{base_name} {strength}".strip()
        if item_type == "영양제":
            return f"{name_with_strength} (영양제 성분 포함)"
        return name_with_strength

    exact_results = await repo.search_by_name(pure_name, limit=1)
    if exact_results:
        med = exact_results[0]
        if pure_name not in seen_names:
            seen_names.add(pure_name)
            matched.append(
                ExtractedMedicine(
                    medicine_name=_build_display_name(med.medicine_name),  # 💡 DB 이름 뒤에 용량을 예쁘게 조립!
                    category=med.category,
                    raw_ocr_name=pure_name,
                    is_llm_corrected=True,
                    match_score=1.0,
                )
            )
        return True

    fuzzy_results = await repo.fuzzy_search_by_name(pure_name, threshold=_FUZZY_THRESHOLD, limit=_FUZZY_LIMIT)
    if fuzzy_results:
        best = fuzzy_results[0]
        med = await repo.get_by_id(best["id"])
        if med and pure_name not in seen_names:
            seen_names.add(pure_name)
            matched.append(
                ExtractedMedicine(
                    medicine_name=_build_display_name(med.medicine_name),  # 💡 DB 이름 뒤에 용량을 예쁘게 조립!
                    category=med.category,
                    raw_ocr_name=pure_name,
                    is_llm_corrected=True,
                    match_score=best["score"],
                )
            )
        return True

    return False


async def _extract_medicines_with_llm(raw_text: str) -> list[dict]:
    """LLM을 호출하여 이름, 용량, 유형을 정밀하게 분리 추출한다."""
    client = get_openai_client()
    if not client:
        logger.error("OPENAI_API_KEY 미설정. LLM 동작 불가.")
        return []

    # 프롬프트 재진화: 이름과 용량을 강제로 분리시킨다.
    prompt = f"""
        너는 대한민국 최고 수준의 약사 AI야.
        다음은 처방전 사진을 OCR로 읽어낸 텍스트야.

        [OCR 전체 문맥 텍스트]
        "{raw_text}"

        [지시사항]
        1. 노이즈는 완전히 무시하고 '의약품'과 '영양제'를 추출해.
        2. 약품명과 용량(strength)을 분리해.
        3. (신규) 텍스트 문맥을 분석하여 각 약품의 '1회 투약량(dose)', '1일 투약 횟수(daily_count)',
           '총 투약 일수(total_days)'를 숫자로 추출해. 만약 텍스트에 없다면 null로 반환해.
        4. (신규) '식후 30분', '취침 전' 등 복용 방법(instruction)이 있다면 추출하고,
           없으면 "식후 30분"을 기본값으로 줘.
        5. 응답은 반드시 아래 형식의 JSON 객체 형태로 반환해. (JSON 포맷 필수)
        [출력 예시]
        {{
            "items": [
                {{
                    "name": "타이레놀정",
                    "strength": "500mg",
                    "type": "의약품",
                    "dose": 1,
                    "daily_count": 3,
                    "total_days": 5,
                    "instruction": "식후 30분"
                }}
            ]
        }}
        """

    try:
        response = await client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
            temperature=0.0,
        )
        result = json.loads(response.choices[0].message.content)
        return result.get("items", [])
    except Exception as e:
        logger.error("LLM 텍스트 추출 실패: %s", e)
        return []

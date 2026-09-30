"""Tool-calling RQ jobs — 위치 검색 + 회수 알림 (PR-D 이후).

진입점:
- ``run_tool_calls_job(calls)`` — 한 턴의 tool_calls 를 ``asyncio.gather`` 로
  병행 실행, ``{tool_call_id: result}`` 반환.

폐기 (PR-D RAG 재설계):
- ``search_medicine_knowledge_base`` tool 분기 폐기 — fastapi 측에서
  ``retrieve_with_metadata`` 직접 호출 (RAG hybrid metadata retrieval).
- ``Router LLM`` (route_intent_job) 폐기 — Query Rewriter (gpt-4o-mini) 가
  fastapi 측 직접 호출.
- batch 임베딩 / Tortoise lifecycle / RAG dispatch 분기 모두 제거.

본 파일은 외부 API tool (Kakao 위치 검색) + 회수 알림 (DB 조회) 만 담당.
"""

import asyncio
import logging
from typing import Any
from uuid import UUID

from app.dtos.tools import KakaoPlace
from app.services.tools.maps.hospital_search import (
  DEFAULT_RADIUS_M,
  HospitalCategory,
  search_hospitals_by_keyword,
  search_hospitals_by_location,
)
from app.services.tools.recalls.checker import (
  check_manufacturer_recalls,
  check_user_medications_recall,
)
from app.services.tools.retry import retry_async

logger = logging.getLogger(__name__)

_CATEGORY_TO_ENUM: dict[str, HospitalCategory] = {
  "약국": HospitalCategory.PHARMACY,
  "병원": HospitalCategory.HOSPITAL,
}


# ── tool_calls 병렬 dispatch (RQ Task) ──────────────────────────────
# 흐름: 빈 calls 단축 -> asyncio.gather 로 dispatch 병행 -> 결과 merge
async def run_tool_calls_job(calls: list[dict[str, Any]]) -> dict[str, Any]:
  """[RQ Task] 모든 tool_call 을 병행 실행해 ``{tool_call_id: result}`` 반환.

  Args:
      calls: 각 dict 가 ``tool_call_id``, ``name``, ``arguments`` 보유.
          location 호출은 ``geolocation: {lat, lng}`` 도 필요.
          recall 호출은 ``profile_id`` 도 필요.

  Returns:
      성공 결과는 ``{"places": [...]}`` (병원/약국) 또는 회수 dict,
      실패는 ``{"error": str}``.
  """
  if not calls:
    return {}

  logger.info(
    "[ToolCalling] run_tool_calls_job start calls=%d names=%s",
    len(calls),
    ",".join(c.get("name", "?") for c in calls),
  )
  results = await asyncio.gather(*[_dispatch(call) for call in calls], return_exceptions=False)
  merged = {call["tool_call_id"]: result for call, result in zip(calls, results, strict=True)}
  error_count = sum(1 for r in merged.values() if "error" in r)
  logger.info("[ToolCalling] run_tool_calls_job done ok=%d errors=%d", len(merged) - error_count, error_count)
  return merged


async def _dispatch(call: dict[str, Any]) -> dict[str, Any]:
  """단일 call dict 를 적절한 함수로 라우팅. 예외는 결과 dict 로 직렬화."""
  name = call.get("name", "")
  try:
    if name == "search_hospitals_by_keyword":
      return await _run_keyword(call)
    if name == "search_hospitals_by_location":
      return await _run_location(call)
    if name == "check_user_medications_recall":
      return await _run_user_recall(call)
    if name == "check_manufacturer_recalls":
      return await _run_manufacturer_recall(call)
  except Exception as exc:
    logger.exception("[ToolCalling] tool call %r failed", name)
    return {"error": f"{type(exc).__name__}: {exc}"}
  return {"error": f"unknown function: {name}"}


# Kakao API 외부 호출은 retry decorator 적용 — 일시적 ConnectionError /
# TimeoutError 시 자동 재시도.
@retry_async()
async def _kakao_keyword(query: str) -> list[KakaoPlace]:
  return await search_hospitals_by_keyword(query=query)


@retry_async()
async def _kakao_location(
  *,
  lat: float,
  lng: float,
  radius_m: int,
  category: HospitalCategory,
) -> list[KakaoPlace]:
  return await search_hospitals_by_location(lat=lat, lng=lng, radius_m=radius_m, category=category)


async def _run_keyword(call: dict[str, Any]) -> dict[str, Any]:
  """키워드 기반 병원/약국 검색 (Kakao API + retry)."""
  arguments = call.get("arguments") or {}
  query = arguments.get("query", "")
  places = await _kakao_keyword(query=query)
  return {"places": _places_to_dict_list(places)}


async def _run_location(call: dict[str, Any]) -> dict[str, Any]:
  """위치 기반 병원/약국 검색 (Kakao API + retry, geolocation 필수)."""
  geolocation = call.get("geolocation")
  if not _is_valid_geolocation(geolocation):
    return {"error": "missing geolocation: location tool requires lat/lng in call payload"}

  arguments = call.get("arguments") or {}
  category = _CATEGORY_TO_ENUM.get(arguments.get("category", "약국"), HospitalCategory.PHARMACY)
  radius_m = int(arguments.get("radius_m", DEFAULT_RADIUS_M))
  places = await _kakao_location(
    lat=float(geolocation["lat"]),
    lng=float(geolocation["lng"]),
    radius_m=radius_m,
    category=category,
  )
  return {"places": _places_to_dict_list(places)}


def _is_valid_geolocation(geolocation: dict[str, Any] | None) -> bool:
  """Geolocation dict 가 lat/lng 를 실제 숫자값으로 가졌는지 검증."""
  if not geolocation:
    return False
  lat = geolocation.get("lat")
  lng = geolocation.get("lng")
  return isinstance(lat, (int, float)) and isinstance(lng, (int, float))


def _places_to_dict_list(places: list[KakaoPlace]) -> list[dict[str, Any]]:
  """KakaoPlace 리스트를 RQ pickle 안전한 dict 리스트로 변환."""
  return [p.model_dump() for p in places]


# ── 회수·판매중지 툴 dispatch ──────────────────────────────────────
def _resolve_profile_id(call: dict[str, Any]) -> UUID:
  """Call payload 에서 profile_id 를 UUID 로 변환."""
  raw = call.get("profile_id")
  if raw is None:
    msg = "missing profile_id: recall tool requires profile_id in call payload"
    raise ValueError(msg)
  return raw if isinstance(raw, UUID) else UUID(str(raw))


async def _run_user_recall(call: dict[str, Any]) -> dict[str, Any]:
  """Q1 — 사용자 복용약 회수 매칭."""
  profile_id = _resolve_profile_id(call)
  return await check_user_medications_recall(profile_id=profile_id)


async def _run_manufacturer_recall(call: dict[str, Any]) -> dict[str, Any]:
  """Q2 — 제조사 회수 매칭."""
  profile_id = _resolve_profile_id(call)
  arguments = call.get("arguments") or {}
  manufacturer = arguments.get("manufacturer") or None
  return await check_manufacturer_recalls(profile_id=profile_id, manufacturer=manufacturer)

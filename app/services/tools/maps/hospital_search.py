"""사용자 입력 형태별로 갈라지는 두 개의 병원/약국 검색 함수.

기능적으로는 "병원·약국 위치 찾기" 한 가지지만 LLM 이 인지하는 인자
스키마는 두 갈래로 분리되어 있다:

- ``search_hospitals_by_location(lat, lng, radius_m, category)``
    → 사용자 GPS 좌표 기반. ``category_group_code`` 로 약국/병원만 필터.
- ``search_hospitals_by_keyword(query)``
    → 지명·랜드마크 등 자연어 키워드. 카카오가 카테고리를 자동 판단.

내부적으로는 두 함수 모두 Y-1 의 ``kakao_local_search`` 한 진입점을 통한다.
입력 → 카카오 파라미터 변환 단계만 다르고 호출/재시도/에러 정규화는 전부
Y-1 에서 처리.
"""

from enum import StrEnum

from app.dtos.tools import KakaoPlace
from app.services.tools.maps.kakao_client import kakao_local_search

DEFAULT_RADIUS_M = 1000


class HospitalCategory(StrEnum):
  """카카오 카테고리 그룹 코드 중 의료 도메인 두 가지.

  카카오 공식 코드:
      - PM9: 약국
      - HP8: 병원
  """

  PHARMACY = "PM9"
  HOSPITAL = "HP8"


_CATEGORY_LABEL: dict[HospitalCategory, str] = {
  HospitalCategory.PHARMACY: "약국",
  HospitalCategory.HOSPITAL: "병원",
}


async def search_hospitals_by_location(
  *,
  lat: float,
  lng: float,
  radius_m: int = DEFAULT_RADIUS_M,
  category: HospitalCategory = HospitalCategory.PHARMACY,
) -> list[KakaoPlace]:
  """사용자 좌표 주변에서 약국 또는 병원을 검색.

  Args:
      lat: 사용자 위도 (WGS84). 카카오의 ``y`` 로 매핑.
      lng: 사용자 경도 (WGS84). 카카오의 ``x`` 로 매핑.
      radius_m: 검색 반경 (m). 기본 1000m.
      category: ``HospitalCategory.PHARMACY`` 또는 ``HOSPITAL``.

  Returns:
      ``KakaoPlace`` 리스트. 결과 0건이면 빈 리스트.

  Raises:
      KakaoAPIError: Y-1 의 호출 규약을 그대로 전파.
  """
  return await kakao_local_search(
    query=_CATEGORY_LABEL[category],
    x=lng,
    y=lat,
    radius=radius_m,
    category_group_code=category.value,
  )


async def search_hospitals_by_keyword(*, query: str) -> list[KakaoPlace]:
  """지명/지역명/랜드마크 등 자연어 키워드로 약국·병원을 검색.

  좌표 인자도 카테고리 그룹도 강제하지 않으므로, 사용자 query 의 표현
  그대로 (예: "강남역 약국", "서울대병원") 카카오에 위임한다.

  Args:
      query: 검색 키워드. 공백 문자열은 ``ValueError``.

  Returns:
      ``KakaoPlace`` 리스트. 결과 0건이면 빈 리스트.

  Raises:
      ValueError: ``query`` 가 비었거나 공백뿐일 때.
      KakaoAPIError: Y-1 의 호출 규약을 그대로 전파.
  """
  if not query or not query.strip():
    raise ValueError("query must not be empty")

  return await kakao_local_search(query=query)

"""병원/약국 검색 두 함수 계약 테스트 (Y-2 Red).

`app/services/tools/maps/hospital_search.py` 의 두 공개 함수가 Y-1 의
``kakao_local_search`` 로 적절한 인자를 위임하는지만 락한다. 카카오 응답
정규화는 Y-1 에서 이미 검증했으므로 여기선 인자 변환에 집중.

Red 전제:
- ``HospitalCategory`` StrEnum 이 PHARMACY / HOSPITAL 두 멤버를 갖는다.
- ``search_hospitals_by_location(lat, lng, radius_m, category)`` 시그니처.
- ``search_hospitals_by_keyword(query)`` 시그니처.
- 두 함수 모두 ``kakao_local_search`` 를 호출하며 인자 매핑이 정확하다.
"""

from typing import Any
from unittest.mock import AsyncMock

import pytest

from app.dtos.tools import KakaoPlace
from app.services.tools.maps.hospital_search import (
  DEFAULT_RADIUS_M,
  HospitalCategory,
  search_hospitals_by_keyword,
  search_hospitals_by_location,
)

# ── 공용 ───────────────────────────────────────────────────────


def _make_place(name: str = "테스트약국") -> KakaoPlace:
  return KakaoPlace(
    id="1",
    place_name=name,
    address="서울 어딘가",
    road_address=None,
    phone=None,
    category_name=None,
    category_group_code="PM9",
    lat=37.5,
    lng=127.0,
  )


# ── Enum & 상수 ────────────────────────────────────────────────


class TestHospitalCategoryEnum:
  def test_has_pharmacy_member(self) -> None:
    assert HospitalCategory.PHARMACY.value == "PM9"

  def test_has_hospital_member(self) -> None:
    assert HospitalCategory.HOSPITAL.value == "HP8"

  def test_default_radius_is_1000m(self) -> None:
    assert DEFAULT_RADIUS_M == 1000


# ── search_hospitals_by_location ───────────────────────────────


class TestSearchHospitalsByLocation:
  @pytest.mark.asyncio
  async def test_passes_lat_lng_swapped_to_x_y(self, monkeypatch: pytest.MonkeyPatch) -> None:
    """Kakao 의 좌표 규약: x=경도, y=위도. 본 함수는 lat/lng 입력을 뒤집어서 전달."""
    captured: dict[str, Any] = {}

    async def fake_search(**kwargs: Any) -> list[KakaoPlace]:
      captured.update(kwargs)
      return [_make_place()]

    from app.services.tools.maps import hospital_search

    monkeypatch.setattr(hospital_search, "kakao_local_search", AsyncMock(side_effect=fake_search))

    await search_hospitals_by_location(lat=37.4978, lng=127.0286)

    assert captured["x"] == 127.0286
    assert captured["y"] == 37.4978

  @pytest.mark.asyncio
  async def test_default_category_is_pharmacy_with_pm9_code(self, monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, Any] = {}

    async def fake_search(**kwargs: Any) -> list[KakaoPlace]:
      captured.update(kwargs)
      return []

    from app.services.tools.maps import hospital_search

    monkeypatch.setattr(hospital_search, "kakao_local_search", AsyncMock(side_effect=fake_search))

    await search_hospitals_by_location(lat=37.5, lng=127.0)

    assert captured["category_group_code"] == "PM9"

  @pytest.mark.asyncio
  async def test_hospital_category_uses_hp8(self, monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, Any] = {}

    async def fake_search(**kwargs: Any) -> list[KakaoPlace]:
      captured.update(kwargs)
      return []

    from app.services.tools.maps import hospital_search

    monkeypatch.setattr(hospital_search, "kakao_local_search", AsyncMock(side_effect=fake_search))

    await search_hospitals_by_location(lat=37.5, lng=127.0, category=HospitalCategory.HOSPITAL)

    assert captured["category_group_code"] == "HP8"

  @pytest.mark.asyncio
  async def test_default_radius_is_forwarded(self, monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, Any] = {}

    async def fake_search(**kwargs: Any) -> list[KakaoPlace]:
      captured.update(kwargs)
      return []

    from app.services.tools.maps import hospital_search

    monkeypatch.setattr(hospital_search, "kakao_local_search", AsyncMock(side_effect=fake_search))

    await search_hospitals_by_location(lat=37.5, lng=127.0)

    assert captured["radius"] == DEFAULT_RADIUS_M

  @pytest.mark.asyncio
  async def test_custom_radius_is_forwarded(self, monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, Any] = {}

    async def fake_search(**kwargs: Any) -> list[KakaoPlace]:
      captured.update(kwargs)
      return []

    from app.services.tools.maps import hospital_search

    monkeypatch.setattr(hospital_search, "kakao_local_search", AsyncMock(side_effect=fake_search))

    await search_hospitals_by_location(lat=37.5, lng=127.0, radius_m=2500)

    assert captured["radius"] == 2500

  @pytest.mark.asyncio
  async def test_query_uses_korean_category_label(self, monkeypatch: pytest.MonkeyPatch) -> None:
    """카카오 권장: 좌표 검색에도 query 에 카테고리 단어를 함께 넘긴다."""
    captured: dict[str, Any] = {}

    async def fake_search(**kwargs: Any) -> list[KakaoPlace]:
      captured.update(kwargs)
      return []

    from app.services.tools.maps import hospital_search

    monkeypatch.setattr(hospital_search, "kakao_local_search", AsyncMock(side_effect=fake_search))

    await search_hospitals_by_location(lat=37.5, lng=127.0, category=HospitalCategory.PHARMACY)
    assert captured["query"] == "약국"

    await search_hospitals_by_location(lat=37.5, lng=127.0, category=HospitalCategory.HOSPITAL)
    assert captured["query"] == "병원"

  @pytest.mark.asyncio
  async def test_returns_list_of_kakao_place(self, monkeypatch: pytest.MonkeyPatch) -> None:
    place = _make_place("미진약국")

    from app.services.tools.maps import hospital_search

    monkeypatch.setattr(hospital_search, "kakao_local_search", AsyncMock(return_value=[place]))

    result = await search_hospitals_by_location(lat=37.5, lng=127.0)

    assert result == [place]


# ── search_hospitals_by_keyword ────────────────────────────────


class TestSearchHospitalsByKeyword:
  @pytest.mark.asyncio
  async def test_passes_query_through(self, monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, Any] = {}

    async def fake_search(**kwargs: Any) -> list[KakaoPlace]:
      captured.update(kwargs)
      return []

    from app.services.tools.maps import hospital_search

    monkeypatch.setattr(hospital_search, "kakao_local_search", AsyncMock(side_effect=fake_search))

    await search_hospitals_by_keyword(query="강남역 약국")

    assert captured["query"] == "강남역 약국"

  @pytest.mark.asyncio
  async def test_does_not_pass_x_y_or_radius(self, monkeypatch: pytest.MonkeyPatch) -> None:
    """키워드 단독 검색은 좌표 인자 없이 호출되어야 한다."""
    captured: dict[str, Any] = {}

    async def fake_search(**kwargs: Any) -> list[KakaoPlace]:
      captured.update(kwargs)
      return []

    from app.services.tools.maps import hospital_search

    monkeypatch.setattr(hospital_search, "kakao_local_search", AsyncMock(side_effect=fake_search))

    await search_hospitals_by_keyword(query="역삼동 병원")

    assert captured.get("x") is None
    assert captured.get("y") is None
    assert captured.get("radius") is None

  @pytest.mark.asyncio
  async def test_does_not_force_category_group_code(self, monkeypatch: pytest.MonkeyPatch) -> None:
    """키워드 검색은 사용자 query 에 따라 약국/병원이 섞일 수 있으므로 group code 미지정."""
    captured: dict[str, Any] = {}

    async def fake_search(**kwargs: Any) -> list[KakaoPlace]:
      captured.update(kwargs)
      return []

    from app.services.tools.maps import hospital_search

    monkeypatch.setattr(hospital_search, "kakao_local_search", AsyncMock(side_effect=fake_search))

    await search_hospitals_by_keyword(query="강남역 약국")

    assert captured.get("category_group_code") is None

  @pytest.mark.asyncio
  async def test_returns_list_of_kakao_place(self, monkeypatch: pytest.MonkeyPatch) -> None:
    place = _make_place("강남스퀘어약국")

    from app.services.tools.maps import hospital_search

    monkeypatch.setattr(hospital_search, "kakao_local_search", AsyncMock(return_value=[place]))

    result = await search_hospitals_by_keyword(query="강남역 약국")

    assert result == [place]

  @pytest.mark.asyncio
  async def test_empty_query_raises_value_error(self) -> None:
    """빈 쿼리는 카카오가 400 으로 거부하므로 함수 진입에서 미리 막는다."""
    with pytest.raises(ValueError, match="query"):
      await search_hospitals_by_keyword(query="")

  @pytest.mark.asyncio
  async def test_whitespace_query_raises_value_error(self) -> None:
    with pytest.raises(ValueError, match="query"):
      await search_hospitals_by_keyword(query="   ")

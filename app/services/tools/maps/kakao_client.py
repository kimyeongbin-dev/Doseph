"""Kakao Local API (키워드로 장소 검색) 단일 진입점.

두 종류의 호출을 하나의 함수로 처리한다:
- 키워드 전국 검색: ``query`` 만 전달
- 좌표 주변 검색: ``query`` + ``x`` + ``y`` + ``radius`` 전달

카카오 공식 문서 (2024-2025):
    https://developers.kakao.com/docs/latest/ko/local/dev-guide

Authorization 헤더는 ``KakaoAK <REST_API_KEY>`` 형태. REST API 키는
카카오 OAuth 2.0 의 ``client_id`` 와 동일한 값이므로 프로젝트 전역
설정 ``config.KAKAO_CLIENT_ID`` 를 그대로 재사용한다.

네트워크 정책:
- httpx ``AsyncClient`` 는 호출자에게 주입받을 수 있고 (테스트용),
  주입이 없으면 모듈 전역 싱글톤을 지연 초기화한다.
- 5xx 는 1회 재시도, 4xx 는 즉시 실패.
- 타임아웃/JSON 파싱 실패/스키마 위반은 모두 ``KakaoAPIError`` 로
  정규화하여 상위 계층이 한 지점만 다루면 되도록 한다.
"""

import json
import logging
from typing import Any

import httpx

from app.core.config import config
from app.dtos.tools import KakaoPlace

logger = logging.getLogger(__name__)

KAKAO_ENDPOINT = "https://dapi.kakao.com/v2/local/search/keyword.json"

_REQUEST_TIMEOUT = httpx.Timeout(5.0)
_MAX_ATTEMPTS = 2  # 최초 1회 + 5xx 재시도 1회

_shared_client: httpx.AsyncClient | None = None


class KakaoAPIError(Exception):
    """Raised for any unrecoverable failure while talking to Kakao Local API."""


def _get_shared_client() -> httpx.AsyncClient:
    """Lazily create (and reuse) a module-level ``AsyncClient``.

    Keeps connection pooling across calls in the same process.
    """
    global _shared_client
    if _shared_client is None:
        _shared_client = httpx.AsyncClient(timeout=_REQUEST_TIMEOUT)
    return _shared_client


def _build_params(
    *,
    query: str,
    x: float | None,
    y: float | None,
    radius: int | None,
    category_group_code: str | None,
    page: int,
    size: int,
) -> dict[str, Any]:
    """Assemble Kakao query-string parameters, omitting empty optionals."""
    params: dict[str, Any] = {"query": query, "page": page, "size": size}
    if x is not None:
        params["x"] = x
    if y is not None:
        params["y"] = y
    if radius is not None:
        params["radius"] = radius
    if category_group_code is not None:
        params["category_group_code"] = category_group_code
    return params


def _to_place(document: dict[str, Any]) -> KakaoPlace:
    """Map one raw Kakao ``documents[i]`` dict to the normalized DTO."""
    return KakaoPlace(
        id=document["id"],
        place_name=document["place_name"],
        address=document["address_name"],
        road_address=document.get("road_address_name") or None,
        phone=document.get("phone") or None,
        category_name=document.get("category_name") or None,
        category_group_code=document.get("category_group_code") or None,
        lat=float(document["y"]),
        lng=float(document["x"]),
    )


def _parse_response(response: httpx.Response) -> list[KakaoPlace]:
    """Decode JSON + normalize, raising ``KakaoAPIError`` on any malformed case."""
    try:
        payload = response.json()
    except (json.JSONDecodeError, ValueError) as exc:
        raise KakaoAPIError(f"Kakao response is not valid JSON: {exc}") from exc

    if not isinstance(payload, dict) or "documents" not in payload:
        raise KakaoAPIError("Kakao response missing 'documents' field")

    documents = payload.get("documents") or []
    try:
        return [_to_place(doc) for doc in documents]
    except (KeyError, TypeError, ValueError) as exc:
        raise KakaoAPIError(f"Kakao document normalization failed: {exc}") from exc


async def kakao_local_search(
    *,
    query: str,
    x: float | None = None,
    y: float | None = None,
    radius: int | None = None,
    category_group_code: str | None = None,
    page: int = 1,
    size: int = 15,
    client: httpx.AsyncClient | None = None,
    api_key: str | None = None,
) -> list[KakaoPlace]:
    """Call Kakao Local API 'search by keyword' and return normalized places.

    Args:
        query: 검색 키워드 (필수). 좌표 검색 시에도 ``"약국"`` 처럼 카테고리
            단어를 넣는 게 카카오 권장.
        x: 경도 (longitude). 좌표 주변 검색에만 사용.
        y: 위도 (latitude). 좌표 주변 검색에만 사용.
        radius: 좌표 기준 검색 반경 (m). 0..20000.
        category_group_code: 카카오 카테고리 그룹 코드. 예: ``PM9`` 약국,
            ``HP8`` 병원.
        page: 결과 페이지 (1..45).
        size: 페이지 크기 (1..15).
        client: 외부에서 주입할 ``AsyncClient``. 테스트에서 MockTransport
            로 대체할 때 사용한다. 없으면 모듈 전역 싱글톤을 사용.
        api_key: Authorization 헤더에 쓸 REST API 키. 없으면
            ``config.KAKAO_CLIENT_ID`` 로 폴백.

    Returns:
        ``KakaoPlace`` 리스트. 결과 0건이면 빈 리스트.

    Raises:
        KakaoAPIError: 4xx, 5xx 재시도 실패, 타임아웃, JSON/스키마 오류.
    """
    headers = {"Authorization": f"KakaoAK {api_key or config.KAKAO_CLIENT_ID}"}
    params = _build_params(
        query=query,
        x=x,
        y=y,
        radius=radius,
        category_group_code=category_group_code,
        page=page,
        size=size,
    )
    http_client = client or _get_shared_client()
    logger.debug("[ToolCalling] Kakao Local search query=%r has_coords=%s", query, x is not None and y is not None)
    response = await _request_with_retry(http_client, params, headers, query=query)
    places = _parse_response(response)
    logger.info("[ToolCalling] Kakao Local search hit=%d query=%r", len(places), query)
    return places


async def _request_with_retry(
    http_client: httpx.AsyncClient,
    params: dict[str, Any],
    headers: dict[str, str],
    *,
    query: str,
) -> httpx.Response:
    """GET ``KAKAO_ENDPOINT`` with single 5xx retry; 4xx/timeout raise immediately.

    Args:
        http_client: Reused ``AsyncClient``.
        params: Pre-built query parameters.
        headers: Authorization header dict.
        query: Original keyword (logged on failure paths).

    Returns:
        Successful (2xx) ``httpx.Response``.

    Raises:
        KakaoAPIError: Timeout / transport error / 4xx / exhausted 5xx retry.
    """
    last_error: Exception | None = None
    for attempt in range(1, _MAX_ATTEMPTS + 1):
        try:
            response = await http_client.get(KAKAO_ENDPOINT, params=params, headers=headers)
        # 🔒 예외 객체를 통째로 문자열화하지 않는다 — httpx 가 transport 예외 메시지에
        #    URL·헤더를 담는 경우가 있고, 이 요청 헤더에는 `KakaoAK <API 키>` 가 들어 있다.
        #    상위가 logger.exception 으로 흘리면 traceback locals 로도 샌다(CLAUDE.md §9.4).
        #    원인 규명에 필요한 것은 **예외 종류**지 문자열 본문이 아니다.
        except httpx.TimeoutException as exc:
            logger.warning("[ToolCalling] Kakao API timeout query=%r", query)
            raise KakaoAPIError(f"Kakao API timeout: {type(exc).__name__}") from exc
        except httpx.HTTPError as exc:
            logger.warning("[ToolCalling] Kakao API transport error query=%r err=%s", query, type(exc).__name__)
            raise KakaoAPIError(f"Kakao API transport error: {type(exc).__name__}") from exc

        status = response.status_code
        if status >= 500:
            last_error = KakaoAPIError(f"Kakao API {status}")
            if attempt < _MAX_ATTEMPTS:
                logger.warning("[ToolCalling] Kakao API %d (attempt %d/%d); retrying", status, attempt, _MAX_ATTEMPTS)
                continue
            logger.error("[ToolCalling] Kakao API %d exhausted retries query=%r", status, query)
            raise last_error

        if status >= 400:
            logger.error("[ToolCalling] Kakao API %d query=%r body=%r", status, query, response.text[:200])
            raise KakaoAPIError(f"Kakao API {status}: {response.text[:200]}")

        return response

    # 방어적: 위 루프가 항상 return/raise 로 끝나지만 mypy 안심용.
    raise KakaoAPIError("Kakao API exhausted retries") from last_error

"""Kakao Local API 클라이언트 계약 테스트 (Y-1 Red).

`app/services/tools/maps/kakao_client.py` 의 공개 API 와 호출 규약만 고정한다.
실제 카카오 서버를 때리지 않기 위해 ``httpx.MockTransport`` 로
요청/응답을 가로채고, ``kakao_local_search`` 는 ``client`` 주입을 허용해
프로덕션에서는 내부 싱글톤을, 테스트에서는 mock transport 를 쓸 수 있게 한다.

Red 전제:
- ``KAKAO_ENDPOINT`` 상수가 존재한다.
- ``KakaoAPIError`` 예외가 존재한다 (timeout/retry 초과/4xx 래핑).
- ``kakao_local_search`` 는 async 함수이고 kwargs-only 인터페이스.
- 응답 documents 는 ``KakaoPlace`` Pydantic 모델 리스트로 정규화된다.
- 5xx 에는 1회 retry, 4xx 에는 즉시 raise.
"""

import json
import logging

import httpx
import pytest

from app.dtos.tools import KakaoPlace
from app.services.tools.maps.kakao_client import (
    KAKAO_ENDPOINT,
    KakaoAPIError,
    kakao_local_search,
)

# ── 공용 헬퍼 ──────────────────────────────────────────────────


_SAMPLE_DOCUMENT = {
    "id": "10398128",
    "place_name": "미진약국",
    "category_name": "의료,건강 > 약국",
    "category_group_code": "PM9",
    "category_group_name": "약국",
    "phone": "02-566-1954",
    "address_name": "서울 강남구 역삼동 825",
    "road_address_name": "서울 강남구 강남대로 390",
    "x": "127.02864025575128",
    "y": "37.497849218691655",
    "place_url": "http://place.map.kakao.com/10398128",
    "distance": "",
}

_EMPTY_BODY = {"documents": [], "meta": {"total_count": 0, "pageable_count": 0, "is_end": True}}


def _make_client(handler: "callable[[httpx.Request], httpx.Response]") -> httpx.AsyncClient:
    """MockTransport 로 감싼 AsyncClient 를 반환."""
    transport = httpx.MockTransport(handler)
    return httpx.AsyncClient(transport=transport)


# ── 인터페이스 계약 ────────────────────────────────────────────


class TestPublicInterface:
    def test_endpoint_points_to_kakao_local_search(self) -> None:
        assert KAKAO_ENDPOINT.endswith("/v2/local/search/keyword.json")

    def test_kakao_api_error_is_exception(self) -> None:
        assert issubclass(KakaoAPIError, Exception)

    def test_kakao_local_search_is_async(self) -> None:
        import inspect

        assert inspect.iscoroutinefunction(kakao_local_search)


# ── 요청 파라미터 빌드 ─────────────────────────────────────────


class TestRequestBuilding:
    @pytest.mark.asyncio
    async def test_keyword_only_request_carries_authorization(self) -> None:
        captured: dict = {}

        def handler(request: httpx.Request) -> httpx.Response:
            captured["headers"] = dict(request.headers)
            captured["url"] = str(request.url)
            return httpx.Response(200, json=_EMPTY_BODY)

        async with _make_client(handler) as client:
            await kakao_local_search(query="강남역 약국", client=client, api_key="TESTKEY")

        assert captured["headers"].get("authorization") == "KakaoAK TESTKEY"
        assert "query=" in captured["url"]

    @pytest.mark.asyncio
    async def test_location_request_includes_x_y_radius(self) -> None:
        captured: dict = {}

        def handler(request: httpx.Request) -> httpx.Response:
            captured["url"] = str(request.url)
            return httpx.Response(200, json=_EMPTY_BODY)

        async with _make_client(handler) as client:
            await kakao_local_search(
                query="약국",
                x=127.0286,
                y=37.4978,
                radius=1000,
                client=client,
                api_key="TESTKEY",
            )

        url = captured["url"]
        assert "x=127.0286" in url
        assert "y=37.4978" in url
        assert "radius=1000" in url

    @pytest.mark.asyncio
    async def test_category_group_code_is_forwarded(self) -> None:
        captured: dict = {}

        def handler(request: httpx.Request) -> httpx.Response:
            captured["url"] = str(request.url)
            return httpx.Response(200, json=_EMPTY_BODY)

        async with _make_client(handler) as client:
            await kakao_local_search(
                query="약국",
                category_group_code="PM9",
                client=client,
                api_key="TESTKEY",
            )

        assert "category_group_code=PM9" in captured["url"]

    @pytest.mark.asyncio
    async def test_page_and_size_default_to_1_and_15(self) -> None:
        captured: dict = {}

        def handler(request: httpx.Request) -> httpx.Response:
            captured["url"] = str(request.url)
            return httpx.Response(200, json=_EMPTY_BODY)

        async with _make_client(handler) as client:
            await kakao_local_search(query="약국", client=client, api_key="TESTKEY")

        assert "page=1" in captured["url"]
        assert "size=15" in captured["url"]


# ── 응답 정규화 ────────────────────────────────────────────────


class TestResponseNormalization:
    @pytest.mark.asyncio
    async def test_returns_list_of_kakao_place(self) -> None:
        def handler(_request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"documents": [_SAMPLE_DOCUMENT], "meta": {}})

        async with _make_client(handler) as client:
            result = await kakao_local_search(query="강남역 약국", client=client, api_key="KEY")

        assert len(result) == 1
        place = result[0]
        assert isinstance(place, KakaoPlace)
        assert place.id == "10398128"
        assert place.place_name == "미진약국"
        assert place.address == "서울 강남구 역삼동 825"
        assert place.road_address == "서울 강남구 강남대로 390"
        assert place.phone == "02-566-1954"
        assert place.category_group_code == "PM9"
        assert place.lat == pytest.approx(37.497849218691655)
        assert place.lng == pytest.approx(127.02864025575128)

    @pytest.mark.asyncio
    async def test_empty_documents_returns_empty_list(self) -> None:
        def handler(_request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json=_EMPTY_BODY)

        async with _make_client(handler) as client:
            result = await kakao_local_search(query="없는가게", client=client, api_key="KEY")

        assert result == []

    @pytest.mark.asyncio
    async def test_optional_fields_missing_map_to_none(self) -> None:
        doc = {
            "id": "1",
            "place_name": "최소정보약국",
            "address_name": "서울 어딘가",
            "x": "127.0",
            "y": "37.5",
        }

        def handler(_request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"documents": [doc], "meta": {}})

        async with _make_client(handler) as client:
            result = await kakao_local_search(query="q", client=client, api_key="KEY")

        place = result[0]
        assert place.road_address is None
        assert place.phone is None
        assert place.category_group_code is None


# ── 에러 / 재시도 ──────────────────────────────────────────────


class TestRetryOn5xx:
    @pytest.mark.asyncio
    async def test_500_retried_once_then_succeeds(self) -> None:
        call_count = {"n": 0}

        def handler(_request: httpx.Request) -> httpx.Response:
            call_count["n"] += 1
            if call_count["n"] == 1:
                return httpx.Response(500, text="boom")
            return httpx.Response(200, json={"documents": [_SAMPLE_DOCUMENT], "meta": {}})

        async with _make_client(handler) as client:
            result = await kakao_local_search(query="q", client=client, api_key="KEY")

        assert call_count["n"] == 2
        assert len(result) == 1

    @pytest.mark.asyncio
    async def test_500_twice_raises_kakao_api_error(self) -> None:
        call_count = {"n": 0}

        def handler(_request: httpx.Request) -> httpx.Response:
            call_count["n"] += 1
            return httpx.Response(500, text="boom")

        async with _make_client(handler) as client:
            with pytest.raises(KakaoAPIError):
                await kakao_local_search(query="q", client=client, api_key="KEY")

        assert call_count["n"] == 2


class TestNoRetryOn4xx:
    @pytest.mark.asyncio
    async def test_401_raises_immediately_without_retry(self) -> None:
        call_count = {"n": 0}

        def handler(_request: httpx.Request) -> httpx.Response:
            call_count["n"] += 1
            return httpx.Response(401, json={"errorType": "AuthenticationError"})

        async with _make_client(handler) as client:
            with pytest.raises(KakaoAPIError):
                await kakao_local_search(query="q", client=client, api_key="BAD")

        assert call_count["n"] == 1

    @pytest.mark.asyncio
    async def test_400_raises_immediately_without_retry(self) -> None:
        call_count = {"n": 0}

        def handler(_request: httpx.Request) -> httpx.Response:
            call_count["n"] += 1
            return httpx.Response(400, text="invalid query")

        async with _make_client(handler) as client:
            with pytest.raises(KakaoAPIError):
                await kakao_local_search(query="", client=client, api_key="KEY")

        assert call_count["n"] == 1


class TestTimeoutWrapped:
    @pytest.mark.asyncio
    async def test_timeout_is_wrapped_as_kakao_api_error(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.TimeoutException("timed out", request=request)

        async with _make_client(handler) as client:
            with pytest.raises(KakaoAPIError):
                await kakao_local_search(query="q", client=client, api_key="KEY")


class TestApiKeyFallsBackToConfig:
    """api_key 를 명시하지 않으면 config.KAKAO_CLIENT_ID 를 사용한다.

    pydantic BaseSettings 인스턴스에 setattr 로 접근하면 전체 validation 이
    재실행되면서 주변 필드까지 건드리므로, 테스트에서는 ``kakao_client`` 모듈이
    import 해 둔 ``config`` 심볼 자체를 간단한 stub 으로 교체한다.
    """

    @pytest.mark.asyncio
    async def test_defaults_to_config_kakao_client_id(self, monkeypatch) -> None:
        from types import SimpleNamespace

        from app.services.tools.maps import kakao_client as kakao_client_module

        monkeypatch.setattr(
            kakao_client_module,
            "config",
            SimpleNamespace(KAKAO_CLIENT_ID="CONFIG_KEY"),
        )

        captured: dict = {}

        def handler(request: httpx.Request) -> httpx.Response:
            captured["auth"] = request.headers.get("authorization")
            return httpx.Response(200, json=_EMPTY_BODY)

        async with _make_client(handler) as client:
            await kakao_local_search(query="q", client=client)

        assert captured["auth"] == "KakaoAK CONFIG_KEY"


class TestMalformedResponse:
    @pytest.mark.asyncio
    async def test_non_json_response_raises_kakao_api_error(self) -> None:
        def handler(_request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, text="<html>nope</html>")

        async with _make_client(handler) as client:
            with pytest.raises(KakaoAPIError):
                await kakao_local_search(query="q", client=client, api_key="KEY")

    @pytest.mark.asyncio
    async def test_missing_documents_key_raises_kakao_api_error(self) -> None:
        def handler(_request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, content=json.dumps({"meta": {}}).encode("utf-8"))

        async with _make_client(handler) as client:
            with pytest.raises(KakaoAPIError):
                await kakao_local_search(query="q", client=client, api_key="KEY")


# ── 🔒 API 키 누설 방지 (S-1, 2026-09-20) ──────────────────────
# 흐름: transport 예외 메시지에 키가 박힌 상황을 만든다 -> 래핑된 예외·로그를 본다
#       -> 키 문자열이 어디에도 안 나와야 한다
#
# 왜 이 테스트가 있나: httpx 의 transport 예외는 요청 URL·헤더를 메시지에 담는 경우가
# 있고, 이 요청 헤더에는 `KakaoAK <API 키>` 가 들어 있다. 예외를 통째로 문자열화하면
# 그 키가 에러 응답·로그·traceback 으로 샌다(`_legacy/2026-04-24_REVIEW.md` S-1, High).
# 🔴 수정만 하고 이 단언이 없으면 **되돌려도 초록**이다 — 잠그는 것이 완료 조건이다.


_LEAKY_SECRET = "SECRET_KAKAO_KEY_ffff9999"


class TestApiKeyNeverLeaksIntoErrors:
    @pytest.mark.asyncio
    async def test_transport_error_message_omits_api_key(self) -> None:
        """transport 예외 메시지에 키가 박혀 있어도 래핑된 예외로 새지 않는다."""

        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError(
                f"failed to connect; headers={{'authorization': 'KakaoAK {_LEAKY_SECRET}'}}",
                request=request,
            )

        async with _make_client(handler) as client:
            with pytest.raises(KakaoAPIError) as excinfo:
                await kakao_local_search(query="q", client=client, api_key=_LEAKY_SECRET)

        assert _LEAKY_SECRET not in str(excinfo.value)

    @pytest.mark.asyncio
    async def test_timeout_message_omits_api_key(self) -> None:
        """타임아웃 경로도 같은 보장을 받는다."""

        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.TimeoutException(f"timed out KakaoAK {_LEAKY_SECRET}", request=request)

        async with _make_client(handler) as client:
            with pytest.raises(KakaoAPIError) as excinfo:
                await kakao_local_search(query="q", client=client, api_key=_LEAKY_SECRET)

        assert _LEAKY_SECRET not in str(excinfo.value)

    @pytest.mark.asyncio
    async def test_transport_error_log_omits_api_key(self) -> None:
        """로그에도 키가 남지 않는다 — 로그는 예외보다 오래 보관된다.

        🔴 ``caplog`` 를 쓰지 않는다. 이 모듈의 로거는 루트로 **전파되지 않아**
        ``caplog.text`` 가 빈 채로 통과한다(실측: 키가 stdout 에 찍히는데도 초록이었다).
        검사 대상 로거에 **핸들러를 직접 붙여** 실제로 나간 레코드를 본다.
        """

        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError(f"boom KakaoAK {_LEAKY_SECRET}", request=request)

        target = logging.getLogger("app.services.tools.maps.kakao_client")
        emitted: list[str] = []

        class _Capture(logging.Handler):
            def emit(self, record: logging.LogRecord) -> None:
                emitted.append(record.getMessage())

        probe = _Capture(level=logging.DEBUG)
        previous_level = target.level
        target.addHandler(probe)
        target.setLevel(logging.DEBUG)
        try:
            async with _make_client(handler) as client:
                with pytest.raises(KakaoAPIError):
                    await kakao_local_search(query="q", client=client, api_key=_LEAKY_SECRET)
        finally:
            target.removeHandler(probe)
            target.setLevel(previous_level)

        # 바닥값 — 레코드를 0건 봤다면 "안 샜다"가 아니라 "아무것도 못 봤다" 이다.
        assert emitted, "이 경로에서 로그가 한 건도 안 나왔다 — 검사가 무력화된 상태다"
        assert not any(_LEAKY_SECRET in line for line in emitted), emitted

    # ✅ 음성 대조 — 키를 가렸다고 **에러가 쓸모없어지면** 안 된다.
    #    실패 종류를 못 알아보는 메시지였다면 사람이 이 방어를 걷어낸다.
    @pytest.mark.asyncio
    async def test_error_message_still_names_the_failure_type(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("boom", request=request)

        async with _make_client(handler) as client:
            with pytest.raises(KakaoAPIError) as excinfo:
                await kakao_local_search(query="q", client=client, api_key=_LEAKY_SECRET)

        assert "ConnectError" in str(excinfo.value)

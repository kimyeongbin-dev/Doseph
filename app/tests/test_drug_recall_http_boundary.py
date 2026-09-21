"""`DrugRecallService` 의 **HTTP 경계** 계약 테스트 (B-8 S1 · QA-06).

지금까지 이 경로는 **한 번도 실행되지 않았다.** 기존 `test_drug_recall_service.py` 가
``patch.object(svc, "_fetch_all_pages", new=AsyncMock(...))`` 로 **페이징 메서드를 통째로**
바꿔 놓았기 때문이다. 그래서 다음이 전부 미검증이었다 —

- 페이징 루프 (``pageNo`` 증가 · ``totalCount`` 도달 판정 · 빈 ``items`` 종료)
- ``raise_for_status()`` 의 4xx/5xx 경로
- ``items`` 가 **dict 단건**으로 올 때 리스트로 감싸는 분기
- 타임아웃

왜 respx 인가 — **주입 지점이 없기 때문이다**
-----------------------------------------------
`kakao_client` 는 ``client: httpx.AsyncClient | None`` 을 받으므로 `httpx.MockTransport` 로
충분하고, `test_kakao_client.py` 가 이미 그렇게 한다(**그쪽은 고칠 게 없다**).
반면 여기는 ``async with httpx.AsyncClient(...)`` 로 **인라인 생성**한다 — 건네줄 자리가 없다.
`MockTransport` 를 쓰려면 **프로덕션 시그니처를 먼저 바꿔야** 하는데 그건
*테스트 없이 하는 설계 변경*이다. respx 는 httpx 를 전역에서 가로채므로
**프로덕션 코드를 한 줄도 안 고치고** 테스트를 먼저 세울 수 있다.

🔴 이 파일은 **현재 계약을 잠그는 것**이지 *"이게 옳다"* 고 말하는 게 아니다
-------------------------------------------------------------------------
아래 두 건은 `kakao_client` 와 **다르게 동작**한다. 고치지 않고 **잠그고 명시**한다
(`CLAUDE.md` §6-2 발견 ≠ 처리. 후속 = `QA-45` · `QA-46`):

===============  ==========================  ==============================
경계             `kakao_client`              `DrugRecallService`
===============  ==========================  ==============================
5xx              1회 재시도 후 실패          **재시도 없음** — 즉시 전파
타임아웃         `KakaoAPIError` 로 정규화   **raw `httpx` 예외가 그대로 샌다**
===============  ==========================  ==============================
"""

from typing import Any

import httpx
import pytest
import respx

from app.services.drug_recall_service import DrugRecallService

# ── 공용 헬퍼 ──────────────────────────────────────────────────────────

_HOST = "apis.data.go.kr"
_PATH = "/1471000/MdcinRtrvlSleStpgeInfoService04/getMdcinRtrvlSleStpgeList03"


def _body(items: object, total_count: int) -> dict[str, Any]:
    """MFDS 응답 봉투. 실제 API 가 `body.items` / `body.totalCount` 로 준다."""
    return {"body": {"items": items, "totalCount": total_count}}


def _item(seq: str) -> dict[str, str]:
    """페이징만 보는 테스트라 최소 필드만 채운다."""
    return {"ITEM_SEQ": seq, "ITEM_NAME": f"테스트약-{seq}"}


def _route() -> respx.Route:
    """목록 엔드포인트 라우트. 쿼리스트링은 매칭 조건에서 뺀다(페이지마다 달라진다)."""
    return respx.route(method="GET", host=_HOST, path=_PATH)


@pytest.fixture
def service() -> DrugRecallService:
    """실 키 없이 만든 서비스. `_fetch_all_pages` 는 저장소를 건드리지 않는다."""
    return DrugRecallService(api_key="TESTKEY")


# ── 페이징 루프 ────────────────────────────────────────────────────────
# 흐름: 1쪽 요청 -> totalCount 미달이면 pageNo+1 -> 도달하면 종료


class TestPagination:
    @respx.mock
    @pytest.mark.asyncio
    async def test_collects_every_page_until_total_count_reached(self, service: DrugRecallService) -> None:
        page1 = [_item(str(i)) for i in range(100)]
        page2 = [_item(str(i)) for i in range(100, 150)]
        route = _route().mock(
            side_effect=[
                httpx.Response(200, json=_body(page1, 150)),
                httpx.Response(200, json=_body(page2, 150)),
            ]
        )

        items = await service._fetch_all_pages()

        assert len(items) == 150, "두 쪽을 이어 붙여야 한다"
        assert route.call_count == 2, "totalCount 에 도달할 때까지만 요청한다"
        assert [call.request.url.params["pageNo"] for call in respx.calls] == ["1", "2"], (
            "pageNo 가 1 -> 2 로 증가해야 한다"
        )

    @respx.mock
    @pytest.mark.asyncio
    async def test_stops_immediately_when_first_page_is_empty(self, service: DrugRecallService) -> None:
        route = _route().mock(return_value=httpx.Response(200, json=_body([], 0)))

        items = await service._fetch_all_pages()

        assert items == []
        assert route.call_count == 1, "빈 쪽을 받으면 더 요청하지 않는다"

    @respx.mock
    @pytest.mark.asyncio
    async def test_service_key_and_page_size_are_sent(self, service: DrugRecallService) -> None:
        _route().mock(return_value=httpx.Response(200, json=_body([], 0)))

        await service._fetch_all_pages()

        params = respx.calls.last.request.url.params
        assert params["serviceKey"] == "TESTKEY"
        assert params["type"] == "json"
        assert params["numOfRows"] == "100", "_MAX_ROWS_PER_PAGE 계약"


# ── 응답 모양 방어 ─────────────────────────────────────────────────────
# 흐름: items 가 dict 단건이면 리스트로 감싼다 (MFDS 가 1건일 때 그렇게 준다)


class TestResponseShape:
    @respx.mock
    @pytest.mark.asyncio
    async def test_single_item_arriving_as_dict_is_wrapped(self, service: DrugRecallService) -> None:
        _route().mock(return_value=httpx.Response(200, json=_body(_item("999"), 1)))

        items = await service._fetch_all_pages()

        assert items == [_item("999")], "dict 단건은 1원소 리스트가 돼야 한다"


# ── 실패 경로 — 🔴 «옳다» 가 아니라 «지금 이렇다» 를 잠근다 ───────────
# 흐름: raise_for_status -> 호출자에게 전파. 아래 두 건은 kakao_client 와 다르다.


class TestFailurePaths:
    @respx.mock
    @pytest.mark.asyncio
    async def test_5xx_raises_without_retry(self, service: DrugRecallService) -> None:
        """🔒 **잠금-불일치**: `kakao_client` 는 5xx 를 1회 재시도하는데 여기는 안 한다.

        같은 저장소의 두 외부 경계가 **서로 다른 복원력 정책**을 갖는다는 사실을
        파일에 남긴다. 고칠지는 별도 결정 — 후속 `QA-45`.
        """
        route = _route().mock(return_value=httpx.Response(503))

        with pytest.raises(httpx.HTTPStatusError):
            await service._fetch_all_pages()

        assert route.call_count == 1, "재시도가 없다 — 이것이 현재 계약이다"

    @respx.mock
    @pytest.mark.asyncio
    async def test_4xx_raises_http_status_error(self, service: DrugRecallService) -> None:
        _route().mock(return_value=httpx.Response(401))

        with pytest.raises(httpx.HTTPStatusError):
            await service._fetch_all_pages()

    @respx.mock
    @pytest.mark.asyncio
    async def test_timeout_leaks_raw_httpx_exception(self, service: DrugRecallService) -> None:
        """🔒 **잠금-불일치**: 타임아웃이 `httpx` 예외 그대로 호출자에게 샌다.

        `kakao_client` 는 `KakaoAPIError` 로 정규화해 *"상위 계층이 한 지점만 다루면
        되도록"* 하는데 여기는 안 한다. 그래서 `sync()` 의 ``except httpx.HTTPStatusError``
        가 **타임아웃을 못 잡고**, 결과적으로 **`DataSyncLog` FAILED 행이 남지 않는다**
        (5xx 일 때는 남는다). 후속 `QA-46`.
        """
        _route().mock(side_effect=httpx.ConnectTimeout("timed out"))

        with pytest.raises(httpx.TimeoutException):
            await service._fetch_all_pages()

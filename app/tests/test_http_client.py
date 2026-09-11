"""Tests for the shared httpx client (커넥션 재사용, 흐름③).

httpx 공식 권장(Client 재사용=커넥션 풀링)에 따른 공유 AsyncClient.
- 싱글턴 재사용 / 명시적 timeout·limits / close 후 재생성.
"""

import asyncio

import httpx

from app.core.http_client import (
    _LIMITS,
    _TIMEOUT,
    close_http_client,
    get_http_client,
)


def test_get_http_client_returns_singleton() -> None:
    """get_http_client 는 같은 AsyncClient 인스턴스를 재사용(풀 유지)."""

    async def run() -> None:
        try:
            c1 = get_http_client()
            c2 = get_http_client()
            assert isinstance(c1, httpx.AsyncClient)
            assert c1 is c2
        finally:
            await close_http_client()

    asyncio.run(run())


def test_client_configured_timeout_and_limits() -> None:
    """명시적 timeout(연결/읽기)·풀 상한(limits) 설정 — 가용성·자원 가드."""
    assert _TIMEOUT.connect is not None
    assert _LIMITS.max_connections is not None
    assert _LIMITS.max_keepalive_connections is not None


def test_close_resets_singleton() -> None:
    """close 후 get 하면 새 인스턴스(라이프사이클 재시작 가능)."""

    async def run() -> None:
        c1 = get_http_client()
        await close_http_client()
        c2 = get_http_client()
        assert c1 is not c2
        await close_http_client()

    asyncio.run(run())

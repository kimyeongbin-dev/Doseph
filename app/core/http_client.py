"""공유 httpx.AsyncClient — keep-alive 커넥션 풀 재사용 (외부 API 지연↓).

httpx 공식 권장(Advanced/Clients): 일회성 스크립트가 아니면 **Client 인스턴스를
재사용**해 커넥션 풀링(핸드셰이크 생략·지연↓·자원↓). 매 호출 ``AsyncClient()`` 생성은
탑레벨 API 와 같은 안티패턴.

안전 규칙(docs-private/study/connection-pooling-security.md):
- ``verify=True``(기본) 유지 — TLS 검증 끄지 않음.
- 명시적 ``timeout``(연결/읽기) + ``limits``(풀 상한) — 가용성·자원 가드.
- **secret/토큰은 client 기본값에 넣지 않고 요청별로만 전달**(호스트 간 bleed 방지).
- FastAPI lifespan 종료 시 ``close_http_client`` 로 정리(누수 방지). 워커(프로세스)마다 자기 인스턴스.
"""

import httpx

# 연결 3s / 그 외 5s — 외부(카카오 등) 지연 시 무한 대기(hang) 방지.
_TIMEOUT = httpx.Timeout(5.0, connect=3.0)
# 동시 커넥션·keepalive 상한 — 폭주 시 자원 고갈(DoS 인접) 방지.
_LIMITS = httpx.Limits(max_connections=20, max_keepalive_connections=10)

_client: httpx.AsyncClient | None = None


# ── 공유 클라이언트 접근 (지연 초기화 + 싱글턴) ────────────────────────
# 흐름: 최초 호출 시 1회 생성 -> 이후 재사용(커넥션 풀 유지)
#       lifespan 없는 컨텍스트(테스트/워커)에서도 안전하게 동작.
def get_http_client() -> httpx.AsyncClient:
    """공유 ``AsyncClient`` 를 반환(없으면 생성). 재사용으로 커넥션 풀 유지.

    Returns:
        httpx.AsyncClient: 프로세스 공유 인스턴스(verify=True, timeout·limits 설정).
    """
    global _client
    if _client is None:
        _client = httpx.AsyncClient(timeout=_TIMEOUT, limits=_LIMITS)
    return _client


async def close_http_client() -> None:
    """공유 클라이언트를 닫고 초기화(라이프사이클 종료·누수 방지)."""
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None

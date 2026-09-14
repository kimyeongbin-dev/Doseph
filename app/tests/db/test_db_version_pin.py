"""Pin the database version so a silent image-tag drift fails loudly.

왜 이 테스트가 있나:
    2026-09-15 이전까지 로컬/CI 는 PostgreSQL 15, prod(Neon) 는 17.11 이었다.
    아무도 몰랐던 이유는 **어긋났다는 사실을 알려주는 장치가 없었기 때문**이다.
    이미지 태그는 코드에 적혀 있어도 그걸 읽는 사람만 알 수 있다.
    이 테스트는 그 값을 **실행 가능한 형태**로 바꿔, 태그가 바뀌면 빨개지게 한다.

무엇을 잠그고 무엇을 잠그지 않는가:
    - 메이저(17)와 pgvector(0.8.0)는 잠근다. prod 와 맞춰야 할 축이다.
    - 마이너(17.6 vs prod 17.11)는 잠그지 않는다. 고정 태그가 빌드된 시점에
      따라 달라지는 값이고, 여기에 걸면 이미지가 갱신될 때마다 거짓 실패가 난다.
"""

from typing import Any

import pytest
from tortoise import connections

pytestmark = [pytest.mark.db, pytest.mark.asyncio(loop_scope="session")]

#: prod(Neon) 실측값 — 2026-09-15.
#: 로컬/CI 이미지 태그 `pgvector/pgvector:0.8.0-pg17` 가 이 값을 맞추도록 골라졌다.
EXPECTED_POSTGRES_MAJOR = 17
EXPECTED_PGVECTOR_VERSION = "0.8.0"
EXPECTED_PG_TRGM_VERSION = "1.6"

#: 태그를 바꿀 때 함께 손봐야 하는 곳. 하나라도 빠지면 환경이 어긋난다.
PINNED_IN = (
    "docker-compose.yml",
    ".github/workflows/checks.yml",
    ".github/workflows/deploy.yml",
)


# ── Postgres 메이저 버전 핀 ───────────────────────────────────────────
# 흐름: 테스트 DB 연결 -> server_version_num 조회 -> 메이저만 비교
async def test_postgres_major_matches_prod(db: None) -> None:
    """The server major version must match the pinned prod major."""
    version_num = int(await _fetch_scalar("show server_version_num"))
    major = version_num // 10000

    assert major == EXPECTED_POSTGRES_MAJOR, (
        f"Postgres 메이저가 핀과 다르다: {major} != {EXPECTED_POSTGRES_MAJOR}. "
        f"이미지 태그를 되돌리거나, prod(Neon)가 올라갔다면 실측 후 이 상수와 "
        f"{', '.join(PINNED_IN)} 를 함께 갱신할 것."
    )


# ── 확장 버전 핀 ──────────────────────────────────────────────────────
# 흐름: pg_extension 조회 -> vector / pg_trgm 버전 비교
# pgvector 가 prod 보다 새로우면 0.8.1+ 기능이 여기서만 통과하고 prod 에서 깨진다.
# 패리티의 방향은 "최신"이 아니라 "prod 와 같게" 다.
async def test_extension_versions_match_prod(db: None) -> None:
    """Installed extension versions must match the pinned prod versions."""
    rows = await _fetch_rows("select extname, extversion from pg_extension")
    installed = {row["extname"]: row["extversion"] for row in rows}

    assert installed.get("vector") == EXPECTED_PGVECTOR_VERSION, (
        f"pgvector 버전이 핀과 다르다: {installed.get('vector')} != {EXPECTED_PGVECTOR_VERSION}"
    )
    assert installed.get("pg_trgm") == EXPECTED_PG_TRGM_VERSION, (
        f"pg_trgm 버전이 핀과 다르다: {installed.get('pg_trgm')} != {EXPECTED_PG_TRGM_VERSION}"
    )


async def _fetch_scalar(query: str) -> str:
    """Run a scalar query on the current Tortoise connection.

    Args:
        query: SQL returning a single row with a single column.

    Returns:
        The scalar value as a string.
    """
    _, rows = await connections.get("default").execute_query(query)
    return str(next(iter(rows[0].values())))


async def _fetch_rows(query: str) -> list[dict[str, Any]]:
    """Run a query on the current Tortoise connection and return all rows.

    Args:
        query: SQL to execute.

    Returns:
        All result rows as dictionaries.
    """
    _, rows = await connections.get("default").execute_query(query)
    return list(rows)

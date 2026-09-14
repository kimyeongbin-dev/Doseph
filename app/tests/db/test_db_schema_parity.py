"""Prove the migration chain still produces the schema the models describe.

이 테스트가 막으려는 사고:
    prod DB 가 코드보다 24 마이그레이션 뒤처져 있던 적이 있다. 드리프트는
    **조용히** 벌어지고, 터질 때는 런타임 500 으로 터진다. 스쿼시할 때
    "빈 DB 에 upgrade -> introspect -> 모델과 대조" 를 손으로 1회 했는데,
    그 검사를 여기서 **상시화**한다.

왜 ``aerich migrate`` 의 "No changes detected" 를 쓰지 않나:
    그건 마이그레이션 파일 안에 직렬화해 둔 ``MODELS_STATE`` 스냅샷을 비교할 뿐
    **실제 DB 를 보지 않는다**. 스냅샷이 틀어져 있으면 틀어진 채로 "변경 없음"
    이라고 답한다. 놓치는 축도 알려져 있다 — 복합 인덱스(aerich#193) ·
    FK 속성(aerich#262) · max_length(aerich#118).
    그래서 여기서는 **두 개의 스키마를 실제로 만들어** 정보 스키마를 대조한다.

        A = 마이그레이션 체인으로 만든 스키마 (배포가 실제로 만드는 것)
        B = 모델 정의로 만든 스키마          (코드가 뜻하는 것)

    B 를 만들 때 ``Tortoise.init`` 을 다시 부르지 않는다 — 전역 싱글턴이라
    A 쪽 연결이 끊긴다. 대신 이미 등록된 모델에서 **스키마 SQL 만 뽑아**
    빈 DB 에 그대로 실행한다.
"""

from collections.abc import AsyncGenerator
from typing import Any

import asyncpg
import pytest
import pytest_asyncio
from tortoise import connections
from tortoise.utils import get_schema_sql

from app.tests.db.conftest import (
    ADMIN_DATABASE,
    TEST_DATABASE,
    admin_execute,
    connect_kwargs,
)

pytestmark = [pytest.mark.db, pytest.mark.asyncio(loop_scope="session")]

#: 모델 정의(B)에는 없고 마이그레이션(A)에만 있는 컬럼.
#: 전부 init 마이그레이션 하단의 raw SQL 로 붙인 것이라 **차이가 나는 게 정상**이다.
#: 존재 여부와 실제 동작은 test_db_constraints 가 따로 잠근다.
#:
#: ⚠️ 여기에 항목을 추가할 때는 **반드시 사유를 적는다.** 사유 없이 늘어나면
#:    이 테스트는 아무것도 막지 못하는 통과 기계가 된다.
RAW_SQL_ONLY_COLUMNS: dict[str, dict[str, str]] = {
    "medicine_chunk": {
        # 모델은 text, 마이그레이션이 halfvec(3072) 로 교체한다(HNSW 인덱싱 전제).
        "embedding": "raw SQL 로 halfvec(3072) 로 교체됨",
        # 모델에 없는 파생 컬럼. 트리거가 content 로부터 채운다.
        "content_tsv": "raw SQL 로 추가된 tsvector 파생 컬럼",
        # 아래 3개는 RAG hybrid 검색이 **raw SQL 로만** 읽고 쓴다
        # (app/services/rag/retrievers/hybrid_metadata.py 의 `?|` 연산자 질의).
        # ORM 을 거치지 않기로 한 의도된 설계라 모델에 필드가 없다.
        "ingredients": "RAG hybrid 필터 전용 jsonb — ORM 밖에서만 사용",
        "target_conditions": "RAG hybrid 필터 전용 jsonb — ORM 밖에서만 사용",
        "target_lifestyle": "RAG hybrid 필터 전용 jsonb — ORM 밖에서만 사용",
    },
}

#: aerich 자신의 이력 테이블. `aerich.models` 가 TORTOISE_APP_MODELS 에 들어 있어
#: A·B 양쪽에 다 생긴다. 우리 도메인 모델이 아니므로 비교에서 뺀다.
AERICH_HISTORY_TABLE = "aerich"


# ── 모델 정의로 만든 비교용 스키마 (B) ────────────────────────────────
# 흐름: 임시 DB 생성 -> 등록된 모델에서 스키마 SQL 추출 -> 빈 DB 에 실행
#       -> 테스트에 이름 대여 -> 세션 끝나면 삭제
# generate_schemas 계열은 **비교 대상을 만들 때만** 쓴다. 테스트 본체의 스키마는
# 언제나 마이그레이션이 만든다(conftest 참조).
@pytest_asyncio.fixture(scope="session")
async def models_database(migrated_database: str) -> AsyncGenerator[str]:
    """Build a throwaway database from the model definitions.

    Yields:
        str: Name of the database created from model definitions.
    """
    database = f"{ADMIN_DATABASE}_models"
    await admin_execute(f'DROP DATABASE IF EXISTS "{database}"')
    await admin_execute(f'CREATE DATABASE "{database}"')

    schema_sql = get_schema_sql(connections.get("default"), safe=False)
    connection = await asyncpg.connect(**connect_kwargs(database))
    try:
        await connection.execute(schema_sql)
    finally:
        await connection.close()

    try:
        yield database
    finally:
        await admin_execute(f'DROP DATABASE IF EXISTS "{database}"')


# ── 테이블 집합 정합 ──────────────────────────────────────────────────
# 흐름: A introspect -> B introspect -> 집합 비교
async def test_migration_and_models_declare_the_same_tables(models_database: str) -> None:
    """The migration chain and the model definitions must agree on tables."""
    migrated = await _table_names(TEST_DATABASE)
    from_models = await _table_names(models_database)
    migrated.discard(AERICH_HISTORY_TABLE)
    from_models.discard(AERICH_HISTORY_TABLE)

    assert migrated == from_models, (
        "마이그레이션이 만든 테이블과 모델이 뜻하는 테이블이 다르다.\n"
        f"  마이그레이션에만: {sorted(migrated - from_models)}\n"
        f"  모델에만:         {sorted(from_models - migrated)}\n"
        "모델을 바꾸고 `aerich migrate` 를 빠뜨렸을 가능성이 가장 높다."
    )


# ── 컬럼 정합 (이름·타입·nullable) ───────────────────────────────────
# 흐름: 두 스키마의 information_schema.columns 대조
#       -> raw SQL 전용 항목만 허용목록으로 제외 -> 나머지는 완전 일치 요구
async def test_migration_and_models_declare_the_same_columns(models_database: str) -> None:
    """Every shared table must agree on columns, types and nullability."""
    migrated = await _column_map(TEST_DATABASE)
    from_models = await _column_map(models_database)
    migrated.pop(AERICH_HISTORY_TABLE, None)
    from_models.pop(AERICH_HISTORY_TABLE, None)

    differences: list[str] = []
    for table in sorted(set(migrated) & set(from_models)):
        allowed = RAW_SQL_ONLY_COLUMNS.get(table, {})
        migrated_columns = migrated[table]
        model_columns = from_models[table]

        for column in sorted(set(migrated_columns) | set(model_columns)):
            if column in allowed:
                continue
            if migrated_columns.get(column) != model_columns.get(column):
                differences.append(
                    f"  {table}.{column}: 마이그레이션={migrated_columns.get(column)} / "
                    f"모델={model_columns.get(column)}"
                )

    assert not differences, "마이그레이션 스키마와 모델 스키마가 컬럼 수준에서 다르다:\n" + "\n".join(differences)


# ── 허용목록 자체의 정직성 ────────────────────────────────────────────
# 흐름: 허용목록에 적힌 컬럼이 **실제로 마이그레이션 쪽에만** 있는지 확인
# 허용목록이 낡아서(이미 모델에 반영됐는데 남아 있어서) 진짜 차이를 덮는 것을 막는다.
async def test_allowlist_entries_are_still_migration_only(models_database: str) -> None:
    """Every allowlisted column must still be migration-only."""
    migrated = await _column_map(TEST_DATABASE)
    from_models = await _column_map(models_database)

    for table, columns in RAW_SQL_ONLY_COLUMNS.items():
        for column, reason in columns.items():
            migration_type = migrated.get(table, {}).get(column)
            model_type = from_models.get(table, {}).get(column)

            assert migration_type is not None, (
                f"허용목록의 {table}.{column} 이 마이그레이션 스키마에 없다 — "
                f"raw SQL 이 사라졌거나 허용목록이 낡았다 ({reason})"
            )
            assert migration_type != model_type, (
                f"허용목록의 {table}.{column} 이 이제 모델과 같다({migration_type}) — "
                f"허용목록에서 빼야 진짜 차이를 잡는다 ({reason})"
            )


async def _table_names(database: str) -> set[str]:
    """Return the set of public table names in ``database``.

    Args:
        database: Database to introspect.

    Returns:
        Table names.
    """
    rows = await _query(
        database,
        "select table_name from information_schema.tables where table_schema = 'public'",
    )
    return {row["table_name"] for row in rows}


async def _column_map(database: str) -> dict[str, dict[str, str]]:
    """Return ``{table: {column: "type/nullable"}}`` for ``database``.

    Args:
        database: Database to introspect.

    Returns:
        Nested mapping describing every public column.
    """
    rows = await _query(
        database,
        "select table_name, column_name, data_type, is_nullable "
        "from information_schema.columns where table_schema = 'public'",
    )
    columns: dict[str, dict[str, str]] = {}
    for row in rows:
        table = columns.setdefault(row["table_name"], {})
        table[row["column_name"]] = f"{row['data_type']}/{row['is_nullable']}"
    return columns


async def _query(database: str, sql: str) -> list[Any]:
    """Run a read-only query against ``database`` on a fresh connection.

    별도 연결을 쓰는 이유: 비교 대상 DB 는 Tortoise 가 붙어 있는 DB 가 아니다.

    Args:
        database: Database to connect to.
        sql: Query to run.

    Returns:
        Result rows (asyncpg records; asyncpg ships no type stubs).
    """
    connection = await asyncpg.connect(**connect_kwargs(database))
    try:
        rows: list[Any] = await connection.fetch(sql)
        return rows
    finally:
        await connection.close()

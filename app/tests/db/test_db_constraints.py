"""Lock the schema objects that live only in raw SQL.

마이그레이션 하단의 raw SQL 블록이 만드는 것들 — halfvec 컬럼 · tsvector 트리거 ·
GIN/trgm 인덱스 · 부분 인덱스 · DB 기본값 — 은 **모델 정의에 보이지 않는다.**
그래서 `test_db_schema_parity` 의 허용목록으로 빠져 있고, 누가 지워도 그쪽은
조용히 통과한다. 여기가 그 구멍을 막는 자리다.

가능하면 **존재가 아니라 동작을 단언한다.** "인덱스가 있다"보다 "제약이 실제로
위반을 막는다", "트리거가 실제로 값을 채운다"가 헛된 초록에 훨씬 강하다.
"""

from typing import Any

import pytest
from tortoise import connections
from tortoise.exceptions import IntegrityError

from app.models.accounts import AuthProvider
from app.tests.db.conftest import create_account

pytestmark = [pytest.mark.db, pytest.mark.asyncio(loop_scope="session")]

#: 마이그레이션 raw SQL 이 만드는 인덱스 — 없어지면 RAG·중복검사 경로가 조용히 느려진다.
EXPECTED_INDEXES = (
    "idx_medicine_chunk_content_tsv_gin",
    "idx_medicine_chunk_ingredients_gin",
    "idx_medicine_chunk_target_conditions_gin",
    "idx_medicine_chunk_target_lifestyle_gin",
    "idx_medicine_chunk_tags_gin",
    "idx_messages_metadata_gin",
    "idx_medicine_info_name_trgm",
    "idx_medicine_info_item_eng_name_trgm",
    "idx_ocr_drafts_dedup",
    "idx_ocr_drafts_profile_active",
    "idx_drug_recalls_command_date",
)


# ── 복합 유니크 제약이 실제로 막는가 ──────────────────────────────────
# 흐름: 같은 (auth_provider, provider_account_id) 로 2건 생성 시도 -> 두 번째가 거부
# "모델에 unique_together 라고 적혀 있다"가 아니라 "DB 가 실제로 막는다"를 본다.
async def test_account_provider_identity_is_unique(db: None) -> None:
    """The (auth_provider, provider_account_id) pair must be unique."""
    account = await create_account()

    with pytest.raises(IntegrityError):
        await create_account(
            auth_provider=AuthProvider.KAKAO,
            provider_account_id=account.provider_account_id,
        )


# ── raw SQL 인덱스가 전부 살아 있는가 ────────────────────────────────
# 흐름: pg_indexes 조회 -> 기대 목록과 대조
# ⚠️ information_schema 에는 인덱스가 없다(SQL 표준이 규정하지 않음) -> pg_indexes 사용.
async def test_raw_sql_indexes_exist(db: None) -> None:
    """Every index created by the raw SQL block must still exist."""
    rows = await _fetch("select indexname from pg_indexes where schemaname = 'public'")
    existing = {row["indexname"] for row in rows}

    missing = [name for name in EXPECTED_INDEXES if name not in existing]
    assert not missing, (
        f"마이그레이션 raw SQL 이 만드는 인덱스가 없다: {missing}\n"
        "모델 정의에 안 보이는 것들이라 스키마 정합 테스트로는 안 잡힌다."
    )


# ── 부분 인덱스의 조건절까지 맞는가 ──────────────────────────────────
# 흐름: indexdef 에서 WHERE 절 확인
# 부분 인덱스는 "있다"만으로 부족하다. 조건이 바뀌면 이름은 같은데 효과가 사라진다.
async def test_ocr_draft_partial_indexes_filter_on_unconsumed(db: None) -> None:
    """The ocr_drafts partial indexes must still filter on consumed_at IS NULL."""
    rows = await _fetch(
        "select indexname, indexdef from pg_indexes where schemaname = 'public' and indexname like 'idx_ocr_drafts_%'"
    )
    definitions = {row["indexname"]: row["indexdef"] for row in rows}

    for name in ("idx_ocr_drafts_dedup", "idx_ocr_drafts_profile_active"):
        definition = definitions.get(name, "")
        assert "WHERE" in definition.upper(), f"{name} 이 부분 인덱스가 아니게 됐다: {definition}"
        assert "consumed_at IS NULL" in definition, (
            f"{name} 의 조건절이 바뀌었다(활성 draft = consumed_at IS NULL): {definition}"
        )


# ── halfvec 컬럼 타입 ─────────────────────────────────────────────────
# 흐름: 컬럼의 실제 타입명 조회 -> halfvec 인지 확인
# text 로 되돌아가면 HNSW 인덱싱 자체가 불가능해진다(3072차원은 halfvec 라야 인덱싱된다).
async def test_embedding_column_is_halfvec(db: None) -> None:
    """medicine_chunk.embedding must stay a halfvec column."""
    rows = await _fetch(
        "select format_type(a.atttypid, a.atttypmod) as type_name "
        "from pg_attribute a "
        "where a.attrelid = 'medicine_chunk'::regclass and a.attname = 'embedding'"
    )

    assert rows, "medicine_chunk.embedding 컬럼이 없다"
    assert "halfvec" in rows[0]["type_name"], (
        f"embedding 이 halfvec 가 아니다: {rows[0]['type_name']} — HNSW 인덱싱이 불가능해진다"
    )


# ── ⭐ tsvector 트리거가 실제로 동작하는가 ───────────────────────────
# 흐름: medicine_chunk 행 삽입 -> content_tsv 가 자동으로 채워졌는지 확인
# "트리거가 존재한다"가 아니라 "값이 채워진다"를 본다. 트리거는 존재해도 함수가
# 비어 있거나 이벤트가 어긋나면 아무 일도 안 한다.
async def test_tsvector_trigger_fills_content_tsv(db: None) -> None:
    """Inserting content must populate content_tsv through the trigger."""
    connection = connections.get("default")
    # medicine_chunk.medicine_info_id 는 NOT NULL FK 라 부모 행이 먼저 필요하다.
    _, parent = await connection.execute_query(
        "insert into medicine_info (medicine_name) values ('트리거테스트약') returning id"
    )
    medicine_info_id = parent[0]["id"]

    await connection.execute_query(
        "insert into medicine_chunk (medicine_info_id, section, content, model_version) "
        "values ($1, 'EFFECT', '테스트 본문 내용', 'trigger-test')",
        [medicine_info_id],
    )

    rows = await _fetch("select content_tsv::text as tsv from medicine_chunk where model_version = 'trigger-test'")

    assert rows, "삽입한 행을 찾을 수 없다"
    assert rows[0]["tsv"], "content 를 넣었는데 content_tsv 가 비어 있다 — 트리거가 동작하지 않는다"


# ── 롤백 픽스처의 사각 확인 ───────────────────────────────────────────
# 흐름: DEFERRABLE 제약이 있는지 조회
# DEFERRABLE INITIALLY DEFERRED 제약은 commit 시점에만 발동하는데, 이 층의 격리
# 픽스처는 commit 을 하지 않는다. 즉 그런 제약의 위반은 **구조적으로 못 잡는다.**
# 지금은 없으므로 무해하지만, 생기는 순간 이 테스트가 알려준다.
async def test_no_deferrable_constraints_exist(db: None) -> None:
    """No deferrable constraints — the rollback fixture could not catch them."""
    rows = await _fetch(
        "select conname from pg_constraint c "
        "join pg_namespace n on n.oid = c.connamespace "
        "where n.nspname = 'public' and c.condeferrable"
    )

    assert not rows, (
        f"DEFERRABLE 제약이 생겼다: {[row['conname'] for row in rows]}\n"
        "이 층의 트랜잭션 롤백 픽스처는 commit 을 하지 않으므로 그 위반을 못 잡는다. "
        "해당 제약을 검증하려면 그 테스트만 커밋 기반으로 분리해야 한다."
    )


# ── ⭐ FK 삭제 정책 — cascade 를 FK 에 맡겼으므로 그 FK 를 잠근다 ───────────
# 흐름: pg_constraint 에서 삭제 정책을 읽어 CASCADE 인지 확인
# QA-01 에서 손으로 돌던 cascade 코드를 전부 제거하고 FK 에 위임했다.
# **위임한 대상이 바뀌면 조용히 고아 행이 남는다** — 그래서 정책 자체를 단언한다.
# (누가 SET NULL 이나 NO ACTION 으로 바꾸면 여기서 빨개진다)
async def test_account_and_profile_children_cascade_on_delete(db: None) -> None:
    """Every FK we rely on for cascade deletion must be ON DELETE CASCADE."""
    rows = await _fetch(
        "select c.conrelid::regclass::text as child, c.confrelid::regclass::text as parent, "
        "c.confdeltype as policy from pg_constraint c "
        "where c.contype = 'f' and c.confrelid in "
        "('accounts'::regclass, 'profiles'::regclass, 'chat_sessions'::regclass, "
        "'lifestyle_guides'::regclass)"
    )

    # ⚠️ asyncpg 는 `confdeltype`("char" 타입)을 **bytes** 로 준다(b"c"). str 비교하면
    #    전부 불일치로 보여 테스트가 항상 빨개진다 — 정규화해서 비교한다.
    def _policy(raw: Any) -> str:
        return raw.decode() if isinstance(raw, bytes) else str(raw)

    non_cascade = [
        f"{r['child']} -> {r['parent']} ({_policy(r['policy'])})" for r in rows if _policy(r["policy"]) != "c"
    ]

    assert not non_cascade, (
        "삭제 cascade 를 FK 에 맡겼는데 CASCADE 가 아닌 FK 가 있다 — 고아 행이 남는다: " + ", ".join(non_cascade)
    )
    assert len(rows) >= 11, f"기대보다 FK 가 적다({len(rows)}) — 위임 대상이 사라졌을 수 있다"


async def _fetch(query: str) -> list[dict[str, Any]]:
    """Run a query on the current Tortoise connection.

    Args:
        query: SQL to execute.

    Returns:
        Result rows as dictionaries.
    """
    _, rows = await connections.get("default").execute_query(query)
    return list(rows)

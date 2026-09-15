"""pgvector 벡터 경로를 진짜 DB 로 검증한다 (RAG 의 바닥).

이 파일의 내력 (QA-04):
    원래 `app/tests/test_vector_field.py` 에 `TestVectorDatabaseIntegration` 3건이
    **`@pytest.mark.skip("Requires database setup")` + 본문이 비어 있는 자리표시자**로
    있었다(2026-04-17~). `setup_test_db` 픽스처조차 주석뿐이었다.
    **5개월간 리포트에 `3 skipped` 로만 찍히며 초록이었다.**

    그 "database setup" 은 QA-23(C12-b)에서 만들었다. 전제가 사라졌으므로 채운다.

무엇을 잠그나:
    (1) halfvec 저장 -> 조회 왕복에서 값이 보존되는가
    (2) **3072차원 halfvec 에 HNSW 인덱스를 만들 수 있는가** — RAG 배포 선결 조건
    (3) 코사인 거리 정렬이 실제로 가까운 것부터 주는가

무엇을 잠그지 않나:
    - **성능.** 옛 이름은 `test_similarity_search_performance` 였으나 폐기했다.
      CI 에서 시간 단언은 러너 상태에 좌우돼 **flaky 공장**이 된다(안전망 규칙 R7).
      대신 *정확성*(정렬 순서)으로 바꿨다. 성능 기준선은 QA-17(RAG 골든셋)의 몫.
    - **인덱스가 실제로 배포돼 있는가.** 2026-09-15 현재 HNSW 인덱스는 **없고**
      RAG 는 seq scan 이다. "있다"로 단언하면 지금 Red 이고, "없다"로 단언하면
      **부재를 계약으로 잠그는 꼴**이라 나중에 추가하는 순간 Red 다.
      그래서 "만들 수 있는가"를 묻는다 — 선결 조건이 충족되는지가 관심사다.
"""

from typing import Any

import pytest
from tortoise import connections

pytestmark = [pytest.mark.db, pytest.mark.asyncio(loop_scope="session")]

#: medicine_chunk.embedding 의 차원. 마이그레이션 raw SQL 이 halfvec(3072) 로 심는다.
#: `vector` 타입은 인덱싱이 2000차원까지라 3072 를 못 넣는다 — halfvec 를 고른 이유.
EMBEDDING_DIM = 3072

#: halfvec 는 16-bit float 라 값이 반올림된다. fp16 으로 **정확히 표현되는 값**만 쓴다
#: (0.5·0.25·1.0 은 2의 거듭제곱 조합이라 오차가 없다). 안 그러면 왕복 비교가 흔들린다.
EXACT_FP16_VALUES = (1.0, 0.5, 0.25)


def _vector_literal(values: list[float]) -> str:
    """Build a pgvector literal like ``[1,0,0,...]``.

    Args:
        values: Component values; padded with zeros to ``EMBEDDING_DIM``.

    Returns:
        Literal string accepted by a halfvec cast.
    """
    padded = values + [0.0] * (EMBEDDING_DIM - len(values))
    return "[" + ",".join(str(v) for v in padded) + "]"


async def _fetch(query: str, params: list[Any] | None = None) -> list[dict[str, Any]]:
    """Run a query on the current Tortoise connection."""
    _, rows = await connections.get("default").execute_query(query, params or [])
    return list(rows)


async def _make_medicine_info(name: str = "벡터테스트약") -> int:
    """Create the parent row a medicine_chunk requires (NOT NULL FK)."""
    rows = await _fetch("insert into medicine_info (medicine_name) values ($1) returning id", [name])
    return int(rows[0]["id"])


async def _insert_chunk(medicine_info_id: int, embedding: list[float], content: str, chunk_index: int = 0) -> None:
    """Insert one medicine_chunk with an embedding.

    ⚠️ `(medicine_info_id, section, chunk_index)` 에 복합 유니크가 걸려 있다.
       같은 약·같은 섹션에 여러 chunk 를 넣으려면 `chunk_index` 를 달리해야 한다
       (실제로 이 제약 때문에 정렬 테스트가 처음에 IntegrityError 로 빨개졌다 —
        제약이 살아 있다는 증거이기도 하다).
    """
    await _fetch(
        "insert into medicine_chunk (medicine_info_id, section, chunk_index, content, model_version, embedding) "
        "values ($1, 'EFFECT', $2, $3, 'qa04', $4::halfvec)",
        [medicine_info_id, chunk_index, content, _vector_literal(embedding)],
    )


# ── (1) halfvec 왕복 — 저장한 값이 그대로 돌아오는가 ─────────────────────────
# 흐름: 부모 행 생성 -> halfvec 삽입 -> 조회 -> 앞쪽 성분 비교
# 이게 깨지면 임베딩이 조용히 변형된다는 뜻이라 RAG 전체가 무의미해진다.
async def test_halfvec_roundtrip_preserves_values(db: None) -> None:
    """A stored halfvec must come back with the same component values."""
    info_id = await _make_medicine_info()
    await _insert_chunk(info_id, list(EXACT_FP16_VALUES), "왕복 테스트")

    rows = await _fetch("select embedding::text as vec from medicine_chunk where model_version = 'qa04'")

    assert rows, "삽입한 chunk 를 찾을 수 없다"
    components = rows[0]["vec"].strip("[]").split(",")
    head = [float(c) for c in components[: len(EXACT_FP16_VALUES)]]

    assert len(components) == EMBEDDING_DIM, f"차원이 달라졌다: {len(components)} != {EMBEDDING_DIM}"
    assert head == list(EXACT_FP16_VALUES), f"halfvec 왕복에서 값이 변형됐다: {head} != {list(EXACT_FP16_VALUES)}"


# ── (2) ⭐ HNSW 인덱스를 만들 수 있는가 — RAG 배포 선결 조건 ─────────────────
# 흐름: 트랜잭션 안에서 CREATE INDEX -> 정의 확인 -> (픽스처가) 롤백
# "있는가"가 아니라 "만들 수 있는가"를 묻는다. 2026-09-15 현재 실제 인덱스는 없고
# RAG 는 seq scan 이다. 여기서 검증하는 건 **전제**다 —
#   · pgvector 가 halfvec 에 HNSW 를 지원하는가
#   · 3072차원이 인덱싱 한계 안인가 (vector 타입이면 2000 초과로 실패한다)
#   · 코사인 연산자 클래스가 있는가
# 이 중 하나라도 깨지면 "HNSW 를 붙이면 된다"는 계획 자체가 무너진다.
async def test_hnsw_index_can_be_created_on_halfvec_embedding(db: None) -> None:
    """HNSW must be creatable on the 3072-dim halfvec column."""
    await _fetch("create index idx_qa04_probe_hnsw on medicine_chunk using hnsw (embedding halfvec_cosine_ops)")

    rows = await _fetch(
        "select indexdef from pg_indexes where schemaname = 'public' and indexname = $1",
        ["idx_qa04_probe_hnsw"],
    )

    assert rows, "3072차원 halfvec 에 HNSW 인덱스를 만들지 못했다 — RAG 배포 선결 조건이 깨졌다"
    definition = rows[0]["indexdef"]
    assert "hnsw" in definition.lower(), f"HNSW 가 아닌 인덱스가 생성됐다: {definition}"
    assert "halfvec_cosine_ops" in definition, f"코사인 연산자 클래스가 반영되지 않았다: {definition}"
    # 인덱스는 이 테스트의 트랜잭션과 함께 롤백된다(CONCURRENTLY 가 아니라 가능).


# ── (3) 코사인 거리 정렬 — 가까운 것이 먼저 오는가 ───────────────────────────
# 흐름: 질의 벡터와 각각 동일/유사/직교인 chunk 3건 삽입 -> `<=>` 정렬 -> 순서 단언
# 옛 이름은 `test_similarity_search_performance` 였으나 시간 단언은 CI 에서 비결정적이라
# 폐기하고, RAG 가 실제로 의존하는 **정확성**으로 바꿨다.
async def test_cosine_distance_orders_nearest_first(db: None) -> None:
    """Ordering by cosine distance must return the closest chunk first."""
    info_id = await _make_medicine_info("정렬테스트약")
    query_vec = [1.0, 0.0, 0.0]

    await _insert_chunk(info_id, [1.0, 0.0, 0.0], "동일", chunk_index=0)
    await _insert_chunk(info_id, [1.0, 0.5, 0.0], "유사", chunk_index=1)
    await _insert_chunk(info_id, [0.0, 1.0, 0.0], "직교", chunk_index=2)

    rows = await _fetch(
        "select content from medicine_chunk where model_version = 'qa04' order by embedding <=> $1::halfvec",
        [_vector_literal(query_vec)],
    )

    assert [r["content"] for r in rows] == ["동일", "유사", "직교"], (
        f"코사인 거리 정렬이 가까운 순이 아니다: {[r['content'] for r in rows]}"
    )

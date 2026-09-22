"""Medicine chunk model module.

This module defines the MedicineChunk model storing section-level
text chunks and their dense vector embeddings (pgvector `halfvec(3072)`,
using OpenAI `text-embedding-3-large`) for RAG similarity search.

The actual `halfvec(3072)` column type is applied via manual SQL inside
the Aerich migration because Tortoise ORM does not natively understand
the pgvector extension type.

⚠️ **차원·모델의 정본은 `app.services.rag.config`** 다 — 여기 수치를 적을 때는 거기와 맞춘다.
2026-09-23 까지 **폐기된 임베딩 설정**(옛 차원·옛 모델)을 8곳에서 설명하고 있었다(`문서-5`).
🔴 **HNSW 인덱스는 아직 배포돼 있지 않다** — 있다고 적지 않는다(`문서-23` · `ROADMAP` v2.7).
"""

from enum import StrEnum

from tortoise import fields, models


class MedicineChunkSection(StrEnum):
    """RAG 청크 섹션 타입 (스키마 락 ②: 6종 고정, v2 수요자 중심 재설계).

    초기 v1은 공공데이터 API ARTICLE title 기반 13종이었으나, 실제 사용자
    질의 유형을 역설계하여 6종으로 축약했다. 세분화 필터는 `interaction_tags`
    JSONB 레이어가 담당한다.

    각 섹션이 커버하는 대표 사용자 질문 유형:
    - OVERVIEW              : "이 약 뭐야?", "두통에 뭐 먹어?"
    - INTAKE_GUIDE          : "공복?", "쪼개 먹어도?", "약 까먹었어"
    - DRUG_INTERACTION      : "홍삼이랑 먹어도?", "와파린 같이 먹어도?"
    - LIFESTYLE_INTERACTION : "커피?", "술?", "운전해도?"
    - ADVERSE_REACTION      : "두드러기 나는데?", "토했어"
    - SPECIAL_EVENT         : "레이저 시술?", "수술 앞두고?", "임신 중"

    팀원에게 공유되는 계약이므로 값 추가/변경 시 팀 공지 필수.
    """

    OVERVIEW = "overview"
    INTAKE_GUIDE = "intake_guide"
    DRUG_INTERACTION = "drug_interaction"
    LIFESTYLE_INTERACTION = "lifestyle_interaction"
    ADVERSE_REACTION = "adverse_reaction"
    SPECIAL_EVENT = "special_event"


class MedicineChunk(models.Model):
    """Section-level embedding chunk for a medicine_info record.

    One medicine_info row yields multiple chunks (one per section, or
    several when an ARTICLE exceeds the model context window). The
    embedding column is materialised as `halfvec(3072)` by a manual
    SQL migration step.

    Attributes:
        id: Auto-increment primary key.
        medicine_info: FK to parent drug (ON DELETE CASCADE).
        section: Chunk section tag (one of MedicineChunkSection).
        chunk_index: Sub-chunk order when an ARTICLE is split by token limit.
        content: Final embedding-target string with header prefix applied.
        token_count: Token count for monitoring and chunk-size tuning.
        embedding: pgvector `halfvec(3072)` dense embedding (managed via raw SQL).
        model_version: Embedding model identifier for re-embedding tracking.
        created_at: Record creation timestamp.
        updated_at: Record update timestamp.
    """

    # ── 기본 식별자 ────────────────────────────────────────────────────
    id = fields.BigIntField(pk=True)

    # ── 부모 약품 참조 (ON DELETE CASCADE) ────────────────────────────
    # medicine_info 삭제 시 연결된 청크도 전부 제거되어야 함
    medicine_info = fields.ForeignKeyField(
        "models.MedicineInfo",
        related_name="chunks",
        on_delete=fields.CASCADE,
        description="Parent medicine_info reference",
    )

    # ── 섹션 분류 및 분할 순번 ─────────────────────────────────────────
    # section: ARTICLE title 기반 섹션 enum (스키마 락)
    # chunk_index: ARTICLE이 128토큰 초과로 분할될 때 순번 (기본 0)
    section = fields.CharField(
        max_length=48,
        description="Chunk section tag (MedicineChunkSection)",
    )
    chunk_index = fields.IntField(
        default=0,
        description="Sub-chunk order when ARTICLE is split by token limit",
    )

    # ── 청크 본문 및 임베딩 ────────────────────────────────────────────
    # content: 헤더 프리픽스 포함 최종 임베딩 대상 텍스트
    # embedding: 실제 타입은 halfvec(3072), Aerich 수동 SQL로 적용
    content = fields.TextField(
        description="Final embedding-target text with header prefix",
    )
    token_count = fields.IntField(
        null=True,
        description="Token count for monitoring",
    )
    embedding = fields.TextField(
        null=True,
        description="pgvector halfvec(3072) - materialised via manual SQL",
    )

    # ── 재임베딩 추적용 모델 버전 ──────────────────────────────────────
    # model 교체/업그레이드 시 부분 재임베딩의 기준이 되는 컬럼
    model_version = fields.CharField(
        max_length=64,
        description="Embedding model version (e.g. text-embedding-3-large)",
    )

    # ── 상호작용 태그 JSONB (스키마 락 ④, v2) ─────────────────────────
    # 청크의 세분화 필터 태그. 예: ["alcohol", "condition:liver"]
    # 태그 값 사전은 ai_worker/data/interaction_tags.json에서 관리하며
    # GIN 인덱스로 @> 연산자 매칭을 가속한다.
    interaction_tags = fields.JSONField(
        default=list,
        description="JSONB array of interaction tags (see interaction_tags.json)",
    )

    # ── 타임스탬프 ─────────────────────────────────────────────────────
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    class Meta:
        table = "medicine_chunk"
        table_description = "Section-level embedding chunks for RAG similarity search"
        unique_together = (("medicine_info", "section", "chunk_index"),)
        indexes = (
            ("medicine_info_id",),
            ("section",),
            ("model_version",),
        )

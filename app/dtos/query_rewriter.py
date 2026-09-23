"""Query Rewriter (1st LLM) Pydantic schema — Structured Output.

`plan/2026-08-11_rag-query-rewriter-plan.md` (PR-B) — 사용자 raw 질의 + medical_context (DB 자동 prepend)
를 입력받아 단일 호출로 다음을 모두 산출:

1. intent 분류 (greeting / out_of_scope / domain_question / ambiguous)
2. greeting/out_of_scope/ambiguous → direct_answer 텍스트
3. domain_question → rewritten_query + metadata (ingredients/conditions/
   sections/drugs/interactions)
4. 대명사 풀이 referent_resolution

이전 IntentClassifier 의 책임을 흡수하면서, fanout_queries (cap=10) 분산
대신 *재작성된 단일 질의 + 메타데이터* 로 hybrid retrieval 입력 단순화.
의약품 도메인 본질 (병용금기/부작용/주의사항이 활성성분 단위로 정의됨) 에
부합 — 메타데이터 필터 + 임베딩 cosine 의 hybrid 전략 가능.
"""

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class IntentType(StrEnum):
    """6가지 의도 카테고리.

    ⚠️ 이 수는 **손으로 적혀 있어 늘어날 때 따라오지 않는다** — 실제로 `location_search`·
    `recall_check` 가 나중에 들어왔는데 이 줄은 *5가지* 인 채로 남아 있었다(2026-09-21 정독에서 발견).
    세려면 `len(IntentType)` 를 쓴다.
    """

    GREETING = "greeting"
    """단순 인사 — direct_answer 즉시 응답."""

    OUT_OF_SCOPE = "out_of_scope"
    """도메인 외 (정치/시사/잡담/욕설/날씨 등) — direct_answer 가이드 메시지."""

    DOMAIN_QUESTION = "domain_question"
    """의학/약학 도메인 질문 — rewritten_query + metadata 로 RAG 검색 진입."""

    AMBIGUOUS = "ambiguous"
    """대명사가 있는데 history 에서 referent 를 못 찾음 — direct_answer 명확화."""

    LOCATION_SEARCH = "location_search"
    """약국·병원 위치 검색 — location_query 로 카카오 Local API 진입."""

    RECALL_CHECK = "recall_check"
    """약품 회수·판매중지·리콜 조회 — recall_query 로 식약처 회수 매칭 진입."""


class LocationMode(StrEnum):
    """카카오 위치 검색 모드."""

    GPS = "gps"
    """'내 주변', '근처', '가까운' — 사용자 좌표 콜백 필요 (PendingTurn)."""

    KEYWORD = "keyword"
    """'강남역 약국', '서울대병원' — 즉시 카카오 keyword 검색."""


class LocationCategory(StrEnum):
    """카카오 카테고리 그룹 코드 매핑 (mode=gps 전용)."""

    PHARMACY = "약국"
    HOSPITAL = "병원"


class LocationQuery(BaseModel):
    """intent=location_search 일 때만 채워지는 카카오 검색 파라미터."""

    model_config = ConfigDict(extra="forbid")

    mode: LocationMode = Field(..., description="gps (좌표 필요) 또는 keyword (즉시 호출).")
    category: LocationCategory | None = Field(
        None,
        description="mode=gps 필수. '약국' 또는 '병원'. mode=keyword 면 None 허용.",
    )
    radius_m: int = Field(
        default=1000,
        description="mode=gps 검색 반경 (m). 기본 1000m.",
    )
    query: str | None = Field(
        None,
        description="mode=keyword 검색어. 예: '강남역 약국', '서울대병원'. mode=gps 면 None.",
    )


class RecallMode(StrEnum):
    """식약처 회수 조회 모드."""

    USER = "user"
    """사용자 복용약 전체 회수 매칭 (check_user_medications_recall)."""

    MANUFACTURER = "manufacturer"
    """제조사 단위 회수 이력 조회 (check_manufacturer_recalls)."""


class RecallQuery(BaseModel):
    """intent=recall_check 일 때만 채워지는 회수 조회 파라미터."""

    model_config = ConfigDict(extra="forbid")

    mode: RecallMode = Field(..., description="user (복용약 전체) 또는 manufacturer (제조사 단위).")
    manufacturer: str | None = Field(
        None,
        description=(
            "mode=manufacturer 일 때 특정 제조사명 (예: '동국제약', '한미약품'). "
            "비우면 사용자 복용약의 제조사 셋 자동 추출. mode=user 면 None."
        ),
    )


class QueryMetadata(BaseModel):
    """RAG hybrid retrieval 의 메타필터 입력 (intent=domain_question 일 때만)."""

    model_config = ConfigDict(extra="forbid")

    target_drugs: list[str] = Field(
        default_factory=list,
        description=(
            "사용자 질의에 등장한 brand 이름 (raw query 또는 referent_resolution 결과). "
            "예: ['타이레놀']. 답변 시 brand 그대로 표기에 사용."
        ),
    )
    target_ingredients: list[str] = Field(
        default_factory=list,
        description=(
            "검색 대상 활성성분명 (medicine_ingredient.mtral_name 와 매칭). "
            "target_drugs 의 활성성분 + medical_context 활성성분 중 검색 의도 약. "
            "예: ['아세트아미노펜']."
        ),
    )
    target_conditions: list[str] = Field(
        default_factory=list,
        description=(
            "환자상태 controlled vocab. medical_context 의 conditions + raw query 의 "
            "환자상태 표현을 controlled term 으로 변환. "
            "예: 'liver_disease', 'kidney_disease', 'diabetes', 'hypertension', "
            "'pregnancy', 'breastfeeding', 'allergy_penicillin' 등. 빈 list 가능."
        ),
    )
    target_sections: list[str] = Field(
        default_factory=list,
        description=(
            "검색할 chunk section list (MedicineChunkSection enum value). "
            "값: 'overview', 'intake_guide', 'drug_interaction', "
            "'lifestyle_interaction', 'adverse_reaction', 'special_event'. "
            "질문 의도에 맞는 섹션만 (예: 부작용 질문 → ['adverse_reaction', "
            "'drug_interaction']). 빈 list 면 모든 섹션 검색."
        ),
    )
    interaction_concerns: list[str] = Field(
        default_factory=list,
        description=(
            "사용자 복용약의 활성성분 list — 상호작용 검사 대상. "
            "medical_context 의 [용어 매핑] 의 brand → 성분 변환 결과를 활용. "
            "검색 시 target_ingredients 와 함께 ingredient 메타필터의 union. "
            "예: ['와파린나트륨', '메트포르민염산염']."
        ),
    )


class QueryRewriterOutput(BaseModel):
    """1st LLM (gpt-4o-mini Structured Output) 의 통합 결과 schema.

    Structured Outputs 강제 — schema 위반 자체 차단. fanout_queries (cap=10)
    대신 단일 rewritten_query + metadata 로 hybrid retrieval 입력 단순화.
    """

    model_config = ConfigDict(extra="forbid")

    intent: IntentType = Field(..., description="질의 의도 카테고리")
    direct_answer: str | None = Field(
        None,
        description=(
            "intent 가 greeting/out_of_scope/ambiguous 일 때 즉시 응답할 텍스트. "
            "domain_question 일 때는 None (rewritten_query + metadata 로 RAG 진입)."
        ),
    )
    rewritten_query: str | None = Field(
        None,
        description=(
            "intent 가 domain_question 일 때 medical_context 를 prepend 한 self-"
            "contained 검색 질의. 약 이름 옆에 (성분) 함께 표기 권장. "
            "예: '간 질환 환자가 와파린(쿠마딘정) 복용 중 아세트아미노펜(타이레놀) "
            "병용 시 출혈 위험과 간 손상 주의사항'. 다른 intent 일 때 None."
        ),
    )
    metadata: QueryMetadata | None = Field(
        None,
        description=(
            "intent 가 domain_question 일 때 retrieval 메타필터 입력. "
            "target_ingredients + interaction_concerns 가 ingredient 필터 source, "
            "target_conditions 가 환자상태 필터, target_sections 가 섹션 필터. "
            "다른 intent 일 때 None."
        ),
    )
    location_query: LocationQuery | None = Field(
        None,
        description=(
            "intent 가 location_search 일 때 카카오 Local API 검색 파라미터. "
            "mode=gps 면 category 필수 + 사용자 좌표 콜백 대기, "
            "mode=keyword 면 query 필수 + 즉시 검색. 다른 intent 일 때 None."
        ),
    )
    recall_query: RecallQuery | None = Field(
        None,
        description=(
            "intent 가 recall_check 일 때 식약처 회수 조회 파라미터. "
            "mode=user 면 사용자 복용약 전체 매칭, "
            "mode=manufacturer 면 제조사 단위 (manufacturer 필드 선택적). "
            "다른 intent 일 때 None."
        ),
    )
    referent_resolution: dict[str, str] | None = Field(
        None,
        description=(
            "대명사 → 명사 매핑. 예: {'그거': '타이레놀'}. "
            "history 에 명시된 referent 만 인정 (hallucination 방지). 없으면 None."
        ),
    )

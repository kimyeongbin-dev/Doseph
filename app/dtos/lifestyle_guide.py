"""Lifestyle guide DTO models module.

This module contains data transfer objects for lifestyle guide operations
including LLM response parsing, async-pipeline status payloads, and API
request/response serialization.
"""

from datetime import date, datetime
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class LifestyleGuideStatus(StrEnum):
    """Lifecycle status used by the SSE / poll API (DTO-level alias).

    Mirrors ``LifestyleGuideStatusValue`` in the model layer so router/service
    can stay framework-agnostic without importing Tortoise.
    """

    PENDING = "pending"
    READY = "ready"
    NO_ACTIVE_MEDS = "no_active_meds"
    FAILED = "failed"


# ── LLM response parsing schemas ───────────────────────────────────────────


class RecommendedChallenge(BaseModel):
    """Single LLM-recommended challenge item.

    Attributes:
        category: Lifestyle category (diet/sleep/exercise/symptom/interaction).
        title: Short challenge title (max 64 chars).
        description: Optional detailed description.
        target_days: Target number of days.
        difficulty: Difficulty label.
    """

    category: str
    title: str = Field(..., max_length=64)
    description: str | None = None
    target_days: int
    difficulty: str | None = None


class LlmGuideResponse(BaseModel):
    """Validated structure of the GPT guide JSON response.

    Used to parse and validate the raw JSON string returned by the LLM.
    Each category field holds the guide text for that category.
    recommended_challenges holds challenges to bulk-create in the DB.

    Attributes:
        diet: Diet and nutrition guidance.
        sleep: Sleep and circadian rhythm guidance.
        exercise: Exercise and activity guidance.
        symptom: Symptom monitoring guidance.
        interaction: Drug-lifestyle interaction guidance.
        recommended_challenges: List of recommended challenges.
    """

    diet: str
    sleep: str
    exercise: str
    symptom: str
    interaction: str
    # 정확히 15개 강제 — prompt builder 의 "정확히 15개" 룰 (5개 set x 3 = 15)
    # 을 schema 단계에서 검증. LLM 응답이 길이 위반 시 ValidationError →
    # generate_guide_payload 의 retry loop 가 자동 재시도.
    recommended_challenges: list[RecommendedChallenge] = Field(default_factory=list, min_length=15, max_length=15)


# ── API response schemas ────────────────────────────────────────────────────


class LifestyleGuideResponse(BaseModel):
    """Lifestyle guide API response model.

    Attributes:
        id: Guide UUID.
        profile_id: Owner profile UUID.
        status: Async generation status (pending/ready/...).
        content: GPT-generated guide content (5 categories — empty until ready).
        medication_snapshot: Active medication list at generation time.
        created_at: Guide creation timestamp.
        processed_at: Terminal-status set time (None while pending).
    """

    model_config = ConfigDict(from_attributes=True)

    id: UUID = Field(..., description="가이드 ID")
    profile_id: UUID = Field(..., description="프로필 ID")
    status: LifestyleGuideStatus = Field(..., description="비동기 생성 상태")
    content: dict = Field(default_factory=dict, description="5개 카테고리 가이드 내용 (pending 일 때 빈 dict)")
    medication_snapshot: list = Field(default_factory=list, description="가이드 생성 시점 활성 약물 목록")
    revealed_challenge_count: int = Field(
        5,
        description="현재까지 사용자에게 노출된 챌린지 수 (5/10/15) — '추천 챌린지 더 보기' 한도 안내용",
    )
    created_at: datetime = Field(..., description="가이드 생성 일시 (= enqueue 시점)")
    processed_at: datetime | None = Field(None, description="ai-worker 가 terminal status 로 진입한 시점")


class LifestyleGuidePendingResponse(BaseModel):
    """Lifestyle guide enqueue response — pending row id + status.

    POST /lifestyle-guides/generate 가 즉시 반환하는 thin payload. 프론트는
    이 ``id`` 로 GET ``/{id}/stream`` SSE 를 연결한다.
    """

    id: UUID = Field(..., description="생성된 pending 가이드 ID")
    status: LifestyleGuideStatus = Field(LifestyleGuideStatus.PENDING, description="enqueue 직후 상태 (=pending)")


class GuideDeleteImpactResponse(BaseModel):
    """가이드를 지우면 무엇이 함께 사라지는지 — 삭제 **전** 고지용.

    가이드 삭제는 ``challenges.guide_id`` 의 ``ON DELETE CASCADE`` 로 진행 중·
    완료 챌린지까지 함께 지운다(QA-01 결정). 사용자가 누르기 전에 잃을 것을
    보여주기 위한 페이로드다.

    최소 노출: **건수만** 담는다. 챌린지 목록은 이미 전용 엔드포인트가 있고,
    확인 다이얼로그에 필요한 것은 숫자뿐이다(DTO 설계 규칙).
    """

    in_progress_count: int = Field(..., description="함께 삭제될 진행 중 챌린지 수")
    completed_count: int = Field(..., description="함께 삭제될 완료 챌린지 수 (완료 기록이 사라진다)")
    not_started_count: int = Field(..., description="함께 삭제될 미시작 챌린지 수")
    total_count: int = Field(..., description="함께 삭제될 챌린지 총 수")


# ── Daily symptom log schemas ───────────────────────────────────────────────


class DailySymptomLogCreate(BaseModel):
    """Daily symptom log creation request model.

    Attributes:
        profile_id: Owner profile UUID.
        log_date: Date of the symptom report.
        symptoms: List of reported symptom strings.
        note: Optional free-text note.
    """

    profile_id: UUID = Field(..., description="프로필 ID")
    log_date: date = Field(..., description="증상 기록 날짜")
    symptoms: list[str] = Field(default_factory=list, description="증상 목록")
    note: str | None = Field(None, max_length=512, description="자유 메모")


class DailySymptomLogResponse(BaseModel):
    """Daily symptom log API response model.

    Attributes:
        id: Log UUID.
        profile_id: Owner profile UUID.
        log_date: Date of the symptom report.
        symptoms: List of reported symptom strings.
        note: Optional free-text note.
        created_at: Record creation timestamp.
    """

    model_config = ConfigDict(from_attributes=True)

    id: UUID = Field(..., description="기록 ID")
    profile_id: UUID = Field(..., description="프로필 ID")
    log_date: date = Field(..., description="증상 기록 날짜")
    symptoms: list[str] = Field(..., description="증상 목록")
    note: str | None = Field(None, description="자유 메모")
    created_at: datetime = Field(..., description="생성 일시")

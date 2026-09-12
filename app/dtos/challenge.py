"""Challenge DTO models module.

This module contains data transfer objects for challenge-related operations
including creation, updates, and response serialization.
"""

from datetime import date, datetime
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ChallengeStatus(StrEnum):
    """챌린지 진행 상태 — 서버가 단독으로 계산/전환한다 (클라 입력 불가).

    IN_PROGRESS: 진행 중. COMPLETED: target_days 달성으로 완료.
    """

    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"


class ChallengeCreate(BaseModel):
    """Challenge creation request model.

    Used for creating new challenges with required fields
    and optional configuration.
    """

    profile_id: UUID = Field(..., description="연결된 프로필 ID")
    title: str = Field(..., max_length=64, description="챌린지 제목")
    description: str | None = Field(None, max_length=256, description="상세 설명")
    target_days: int = Field(..., description="목표 달성 일수")
    difficulty: str | None = Field(None, max_length=16, description="난이도 (쉬움/보통/어려움)")
    started_date: date | None = Field(None, description="챌린지 시작 날짜 (미입력 시 오늘)")


class ChallengeStartRequest(BaseModel):
    """Challenge start customization request model.

    Allows users to override AI-suggested difficulty and target_days
    when activating a challenge. Both fields are optional — omitting
    them preserves the LLM-generated defaults.
    """

    difficulty: str | None = Field(None, max_length=16, description="난이도 (쉬움/보통/어려움)")
    target_days: int | None = Field(None, ge=1, le=365, description="목표 달성 일수 (1~365)")


class ChallengeUpdate(BaseModel):
    """Challenge update request model (메타데이터 전용).

    사용자가 편집 가능한 메타데이터만 받는다. 진행 상태(challenge_status)·완료
    날짜(completed_dates)는 서버가 단독 관리하므로 요청에서 제외 — 체크오프는
    전용 엔드포인트(POST /challenges/{id}/check)로만 이뤄진다 (완료/스트릭 위조
    방지). 활성화(is_active)는 '시작하기' PATCH 호환을 위해 유지하되, 전용
    엔드포인트 PATCH /start 가 정식 경로다.
    """

    title: str | None = Field(None, max_length=64, description="챌린지 제목")
    description: str | None = Field(None, max_length=256, description="상세 설명")
    target_days: int | None = Field(None, description="목표 달성 일수")
    difficulty: str | None = Field(None, max_length=16, description="난이도 (쉬움/보통/어려움)")
    started_date: date | None = Field(None, description="챌린지 시작 날짜")
    is_active: bool | None = Field(None, description="챌린지 활성화 여부")


class ChallengeResponse(BaseModel):
    """Challenge response model.

    Used for serializing challenge data in API responses.
    Includes all challenge fields and metadata.
    """

    model_config = ConfigDict(from_attributes=True)

    id: UUID = Field(..., description="챌린지 레코드 ID")
    profile_id: UUID = Field(..., description="연결된 프로필 ID")
    guide_id: UUID | None = Field(
        None,
        description="원본 LifestyleGuide ID (LLM 생성 시 set, 사용자 수동 생성 시 None)",
    )
    # [추가] 생활습관 가이드 탭(diet/sleep/exercise/symptom/interaction)과 챌린지를 매핑하는 키
    # → 프론트에서 현재 탭에 해당하는 챌린지만 필터링할 때 사용
    category: str | None = Field(None, description="생활습관 카테고리 (diet/sleep/exercise/symptom/interaction)")
    title: str = Field(..., description="챌린지 제목")
    description: str | None = Field(None, description="상세 설명")
    target_days: int = Field(..., description="목표 달성 일수")
    difficulty: str | None = Field(None, description="난이도 (쉬움/보통/어려움)")
    completed_dates: list[date] = Field(default_factory=list, description="달성 완료 날짜 목록")
    challenge_status: ChallengeStatus = Field(..., description="진행 상태 (서버 단독 관리)")
    # [추가] 챌린지 3-상태 패턴을 위해 응답에 노출
    # False → "시작하기" 버튼 / True + IN_PROGRESS → "오늘 완료 체크" / COMPLETED → 완료 뱃지
    is_active: bool = Field(..., description="사용자가 챌린지를 시작했는지 여부")
    started_date: date = Field(..., description="챌린지 시작 날짜")
    created_at: datetime = Field(..., description="생성 일시")
    updated_at: datetime = Field(..., description="수정 일시")

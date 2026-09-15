"""Challenge model module.

This module defines the Challenge model for storing user challenge information
including progress tracking and completion status.
"""

from tortoise import fields, models


class Challenge(models.Model):
    """Challenge model for tracking user health challenges.

    This model stores challenge information including title, description,
    target days, completion tracking, and status.

    Challenges can be LLM-generated (guide is set) or manually created
    by the user (guide is None).

    Attributes:
        id: Primary key UUID.
        profile: Foreign key to Profile model.
        guide: Nullable FK to LifestyleGuide — set when LLM-generated, None when manual.
        category: Lifestyle category (diet/sleep/exercise/symptom/interaction).
        title: Challenge title (max 64 characters).
        description: Optional detailed description (max 256 characters).
        target_days: Target number of days to complete.
        completed_dates: JSON array of completion dates.
        difficulty: Challenge difficulty level.
        challenge_status: Current status (default: IN_PROGRESS).
        is_active: Whether the user has started this challenge.
        started_at: Datetime when user activated the challenge.
        completed_at: Datetime when the challenge was fully completed.
        started_date: Challenge start date.
        created_at: Record creation timestamp.
        updated_at: Last update timestamp.
    """

    id = fields.UUIDField(pk=True)
    profile = fields.ForeignKeyField("models.Profile", related_name="challenges")

    # Nullable FK: populated for LLM-generated challenges, None for manual ones
    guide = fields.ForeignKeyField(
        "models.LifestyleGuide",
        related_name="challenges",
        null=True,
        description="Source guide — None means user-created challenge",
    )

    # 처방전 그룹 — 가이드와 함께 처방전 단위로 묶이는 컨텍스트.
    # 옛 row (마이그레이션 #24 시점 이전) 는 NULL.
    prescription_group = fields.ForeignKeyField(
        "models.PrescriptionGroup",
        related_name="challenges",
        null=True,
        description="소속 처방전 그룹 (신규부터 set)",
    )

    # Lifestyle category — matches GuideCategory enum values
    category = fields.CharField(
        max_length=16,
        null=True,
        description="Lifestyle category (diet/sleep/exercise/symptom/interaction)",
    )

    title = fields.CharField(max_length=64, description="Challenge title")
    description = fields.CharField(max_length=256, null=True, description="Detailed description")
    target_days = fields.IntField(description="Target completion days")

    # Store completion dates as JSON array instead of separate ChallengeLog table
    completed_dates = fields.JSONField(default=list, description="List of completion dates")

    difficulty = fields.CharField(max_length=16, null=True, description="난이도 (쉬움/보통/어려움)")
    challenge_status = fields.CharField(max_length=16, default="IN_PROGRESS", description="진행 상태")

    # Activation lifecycle fields
    is_active = fields.BooleanField(default=False, description="User has started this challenge")
    started_at = fields.DatetimeField(null=True, description="Datetime when user activated challenge")
    completed_at = fields.DatetimeField(null=True, description="Datetime when challenge was completed")

    started_date = fields.DateField(description="챌린지 시작 날짜")

    # 가이드 1개당 LLM 이 한 번에 만든 15개 챌린지를 5개씩 점진 노출하기 위한
    # 정렬 키. 0~4 = 첫 노출 set, 5~9 = "더 보기" 1회, 10~14 = "더 보기" 2회.
    # 각 set 안에는 1일 1개 / 7일 1개 / 14일 2개 / 21일 1개 분배가 함께 들어가
    # 사용자가 매 노출마다 동일 기간 분포를 받는다. 옛 row(마이그레이션 #27 이전)
    # 는 NULL — 이전 정렬 (target_days asc) 으로 fallback.
    slot_index = fields.IntField(
        null=True,
        description="가이드 내 챌린지 노출 순서 (0~14, NULL = legacy)",
    )

    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    class Meta:
        table = "challenges"
        indexes = (("profile_id", "challenge_status"),)

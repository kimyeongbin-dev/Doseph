"""Profile model module.

This module defines the Profile model for storing user profile information
including family relationships and health survey data.
"""

from enum import StrEnum

from tortoise import fields, models


class RelationType(StrEnum):
    """가족 관계 enum — 8종 단일 management.

    SELF 는 카카오 콜백이 자동 생성하는 본인 프로필.
    FATHER ~ WIFE 는 명시적 가족 관계 (성별이 의미적으로 결정됨).
    OTHER 는 자유 매핑 (예: 친척, 지인) — gender 입력 선택.
    """

    SELF = "SELF"
    FATHER = "FATHER"
    MOTHER = "MOTHER"
    SON = "SON"
    DAUGHTER = "DAUGHTER"
    HUSBAND = "HUSBAND"
    WIFE = "WIFE"
    OTHER = "OTHER"


class Gender(StrEnum):
    """프로필 성별 — 약품 추천 / 건강정보 표시용."""

    MALE = "MALE"
    FEMALE = "FEMALE"


# ── relation → 기본 gender 매핑 ────────────────────────────────────
# SELF / OTHER 는 사용자 입력 (관계가 성별을 강제하지 않음).
# 본 매핑은 service 레이어가 가족 row 생성 / 갱신 시 default 로 사용.
# 사용자가 명시적으로 다른 성별을 보내면 그 값이 우선.
RELATION_DEFAULT_GENDER: dict[RelationType, Gender] = {
    RelationType.FATHER: Gender.MALE,
    RelationType.MOTHER: Gender.FEMALE,
    RelationType.SON: Gender.MALE,
    RelationType.DAUGHTER: Gender.FEMALE,
    RelationType.HUSBAND: Gender.MALE,
    RelationType.WIFE: Gender.FEMALE,
}


class Profile(models.Model):
    """Profile model for storing user and family member information.

    Attributes:
        id: Primary key UUID.
        account: Foreign key to Account model.
        relation_type: 가족 관계 (SELF / FATHER / MOTHER / SON / DAUGHTER /
            HUSBAND / WIFE / OTHER) 단일 enum 으로 일원화.
        gender: 프로필 보유자 성별 (MALE / FEMALE). 명시적 가족 관계 6종은
            service 가 default 자동 채움. 사용자 수정 가능. SELF / OTHER 는
            사용자 입력에 의존.
        name: Profile display name.
        health_survey: JSON field for health survey data (age, height, weight,
            conditions, allergies 등). gender 는 본 컬럼에서 분리됨.
        created_at: Profile creation timestamp.
        updated_at: Last update timestamp.
    """

    id = fields.UUIDField(primary_key=True)
    account = fields.ForeignKeyField("models.Account", related_name="profiles")
    relation_type = fields.CharEnumField(enum_type=RelationType, max_length=16)
    gender = fields.CharEnumField(enum_type=Gender, max_length=8, null=True)
    name = fields.CharField(max_length=32)
    health_survey = fields.JSONField(null=True)
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    class Meta:
        table = "profiles"
        indexes = (("account_id", "relation_type"),)

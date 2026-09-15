"""Profile repository module.

This module provides data access layer for the profiles table,
handling user and family member profile management operations.
"""

from datetime import datetime
from uuid import UUID, uuid4

from app.core import config
from app.models.profiles import Gender, Profile, RelationType


class ProfileRepository:
    """Profile database repository for user profile management."""

    async def get_by_id(self, profile_id: UUID) -> Profile | None:
        """Get profile by ID (excluding soft deleted).

        Args:
            profile_id: Profile UUID.

        Returns:
            Profile | None: Profile if found, None otherwise.
        """
        return await Profile.filter(
            id=profile_id,
        ).first()

    async def get_all_by_account(self, account_id: UUID) -> list[Profile]:
        """Get all profiles for an account.

        Args:
            account_id: Account UUID.

        Returns:
            list[Profile]: List of profiles.
        """
        return await Profile.filter(
            account_id=account_id,
        ).all()

    async def get_self_profile(self, account_id: UUID) -> Profile | None:
        """Get account's self profile.

        Args:
            account_id: Account UUID.

        Returns:
            Profile | None: Self profile if found, None otherwise.
        """
        return await Profile.filter(
            account_id=account_id,
            relation_type=RelationType.SELF,
        ).first()

    async def create(
        self,
        account_id: UUID,
        name: str,
        relation_type: RelationType,
        gender: Gender | None = None,
        health_survey: dict | None = None,
    ) -> Profile:
        """Create new profile.

        Args:
            account_id: Account UUID.
            name: Profile name.
            relation_type: Relationship type.
            gender: 성별 (MALE / FEMALE / None). 명시적 가족 관계는 service
                레이어에서 default 자동 채움.
            health_survey: Optional health survey data.

        Returns:
            Profile: Created profile.
        """
        return await Profile.create(
            id=uuid4(),
            account_id=account_id,
            name=name,
            relation_type=relation_type,
            gender=gender,
            health_survey=health_survey,
        )

    async def update(self, profile: Profile, **kwargs) -> Profile:
        """Update profile information.

        Args:
            profile: Profile to update.
            **kwargs: Fields to update.

        Returns:
            Profile: Updated profile.
        """
        await profile.update_from_dict(kwargs).save()
        return profile

    async def soft_delete(self, profile: Profile) -> Profile:
        """Delete a profile row — 자식은 FK CASCADE 가 함께 지운다.

        ⚠️ 이름은 ``soft_delete`` 지만 **물리 삭제**다(QA-01, 2026-09-15).
        ``profiles`` 를 참조하는 FK 8개(medications · challenges · chat_sessions ·
        prescription_groups · intake_logs · daily_symptom_logs · lifestyle_guides ·
        ocr_drafts)가 전부 ``ON DELETE CASCADE`` 라, 이 한 줄이 자식 전부를 정리한다
        (messages 는 chat_sessions 를 통해 연쇄).

        Args:
            profile: Profile to delete.

        Returns:
            Profile: The (now deleted) instance.
        """
        await Profile.filter(id=profile.id).delete()
        return profile

    async def bulk_soft_delete_by_account(self, account_id: UUID) -> int:
        """계정 소유의 모든 active profile 을 일괄 soft delete.

        회원탈퇴(account cascade soft-delete) 흐름의 1단계로 호출되며, 이미
        deleted_at 이 set 된 row 는 자연스럽게 제외된다 (idempotent).

        Args:
            account_id: 대상 계정 UUID.

        Returns:
            새로 deleted_at 이 채워진 row 수 (이미 삭제된 행은 카운트 X).
        """
        return await Profile.filter(
            account_id=account_id,
        ).update(deleted_at=datetime.now(tz=config.TIMEZONE))

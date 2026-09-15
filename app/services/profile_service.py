"""Profile service module.

This module provides business logic for user profile management operations
including creation, updates, and ownership verification.
"""

from uuid import UUID

from fastapi import HTTPException, status

from app.dtos.profile import ProfileCreate, ProfileUpdate
from app.models.profiles import RELATION_DEFAULT_GENDER, Gender, Profile, RelationType
from app.repositories.challenge_repository import ChallengeRepository
from app.repositories.chat_session_repository import ChatSessionRepository
from app.repositories.daily_symptom_log_repository import DailySymptomLogRepository
from app.repositories.intake_log_repository import IntakeLogRepository
from app.repositories.lifestyle_guide_repository import LifestyleGuideRepository
from app.repositories.medication_repository import MedicationRepository
from app.repositories.message_repository import MessageRepository
from app.repositories.ocr_draft_repository import OcrDraftRepository
from app.repositories.profile_repository import ProfileRepository


class ProfileService:
    """Profile business logic service for user profile management."""

    def __init__(self) -> None:
        self.repository = ProfileRepository()
        self.medication_repository = MedicationRepository()
        self.challenge_repository = ChallengeRepository()
        self.chat_session_repository = ChatSessionRepository()
        self.message_repository = MessageRepository()
        self.intake_log_repository = IntakeLogRepository()
        self.daily_symptom_log_repository = DailySymptomLogRepository()
        self.lifestyle_guide_repository = LifestyleGuideRepository()
        self.ocr_draft_repository = OcrDraftRepository()

    async def get_profile(self, profile_id: UUID) -> Profile:
        """Get profile by ID.

        Args:
            profile_id: Profile UUID.

        Returns:
            Profile: Profile object.

        Raises:
            HTTPException: If profile not found.
        """
        profile = await self.repository.get_by_id(profile_id)
        if not profile:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Profile not found.",
            )
        return profile

    async def get_profile_with_owner_check(self, profile_id: UUID, account_id: UUID) -> Profile:
        """Get profile with ownership verification.

        Args:
            profile_id: Profile UUID.
            account_id: Account UUID for ownership check.

        Returns:
            Profile: Profile if owned by account.

        Raises:
            HTTPException: If access denied to profile.
        """
        profile = await self.get_profile(profile_id)
        if profile.account_id != account_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied to this profile.",
            )
        return profile

    async def get_profiles_by_account(self, account_id: UUID) -> list[Profile]:
        """Get all profiles for an account.

        Args:
            account_id: Account UUID.

        Returns:
            list[Profile]: List of profiles.
        """
        return await self.repository.get_all_by_account(account_id)

    async def get_self_profile(self, account_id: UUID) -> Profile | None:
        """Get account's self profile.

        Args:
            account_id: Account UUID.

        Returns:
            Profile | None: Self profile if found, None otherwise.
        """
        return await self.repository.get_self_profile(account_id)

    @staticmethod
    def _resolve_gender(relation_type: RelationType, requested_gender: Gender | None) -> Gender | None:
        """relation_type 기반 gender default 결정.

        - 사용자가 명시적으로 gender 보내면(``requested_gender`` 가 not None)
          그 값을 우선 사용 (특수 케이스 대응).
        - 그렇지 않으면 6 가지 명시적 가족 관계는 자동 매핑, SELF / OTHER 는 None.

        Args:
            relation_type: 가족 관계.
            requested_gender: 사용자 요청에서 받은 gender 값 (없으면 None).

        Returns:
            최종 적용할 Gender 값 또는 None.
        """
        if requested_gender is not None:
            return requested_gender
        return RELATION_DEFAULT_GENDER.get(relation_type)

    async def create_profile(
        self,
        account_id: UUID,
        data: ProfileCreate,
    ) -> Profile:
        """Create new profile.

        Args:
            account_id: Account UUID.
            data: Profile creation data.

        Returns:
            Profile: Created profile.

        Raises:
            HTTPException: If SELF profile already exists for account.
        """
        relation_type = RelationType(data.relation_type)

        # Only one SELF profile allowed per account
        if relation_type == RelationType.SELF:
            existing_self = await self.repository.get_self_profile(account_id)
            if existing_self:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Self profile already exists.",
                )

        gender = self._resolve_gender(relation_type, data.gender)

        return await self.repository.create(
            account_id=account_id,
            name=data.name,
            relation_type=relation_type,
            gender=gender,
            health_survey=data.health_survey,
        )

    @staticmethod
    def _apply_gender_default_on_relation_change(update_data: dict) -> None:
        """relation_type 변경 시 gender 도 default 자동 갱신 (사용자 명시 없을 때).

        ``update_data`` 에 ``relation_type`` 이 들어있는데 ``gender`` 가
        명시되지 않았다면, 새 relation_type 의 default gender 로 자동 set.
        SELF / OTHER 는 default 없음 → 기존 값 유지 (update_data 에 추가 안 함).

        Args:
            update_data: model_dump 결과 dict — 본 함수가 gender 키를 추가할 수 있음.
        """
        if "relation_type" not in update_data or "gender" in update_data:
            return
        new_relation = RelationType(update_data["relation_type"])
        default_gender = RELATION_DEFAULT_GENDER.get(new_relation)
        if default_gender is not None:
            update_data["gender"] = default_gender

    async def update_profile(
        self,
        profile_id: UUID,
        data: ProfileUpdate,
    ) -> Profile:
        """Update profile.

        Args:
            profile_id: Profile UUID.
            data: Profile update data.

        Returns:
            Profile: Updated profile.
        """
        profile = await self.get_profile(profile_id)
        update_data = data.model_dump(exclude_unset=True)
        self._apply_gender_default_on_relation_change(update_data)
        return await self.repository.update(profile, **update_data)

    async def update_profile_with_owner_check(
        self,
        profile_id: UUID,
        account_id: UUID,
        data: ProfileUpdate,
    ) -> Profile:
        """Update profile with ownership verification.

        Args:
            profile_id: Profile UUID.
            account_id: Account UUID for ownership check.
            data: Profile update data.

        Returns:
            Profile: Updated profile if owned by account.
        """
        profile = await self.get_profile_with_owner_check(profile_id, account_id)
        update_data = data.model_dump(exclude_unset=True)
        self._apply_gender_default_on_relation_change(update_data)
        return await self.repository.update(profile, **update_data)

    # ── 프로필 삭제 (cascade — 전부 물리 삭제) ──────────────────────────
    # 흐름: profile 행 삭제 -> FK ON DELETE CASCADE 가 자식 8종을 함께 정리
    #       (medication/challenge/chat_session/intake_log/lifestyle_guide/
    #        ocr_draft/daily_symptom_log, messages 는 chat_session 을 통해 연쇄)
    # 단일 DELETE 라 원자적. 회원탈퇴(oauth) 도 이 helper 를 호출.

    async def cascade_delete_profile(self, profile: Profile) -> None:
        """Profile 삭제 — 자식 row 는 FK CASCADE 가 함께 정리한다.

        ⚠️ 2026-09-15(QA-01): 자식을 손수 지우던 **8번의 호출을 제거**했다.
        ``profiles`` 를 참조하는 FK 8개가 전부 ``ON DELETE CASCADE`` 이므로
        DB 가 같은 일을 이미 원자적으로 한다(messages 는 chat_sessions 를 통해 연쇄).

        같은 일을 두 곳에서 하면 두 경로가 어긋날 때 **조용한 불일치**가 생긴다 —
        그게 QA-01 의 형태였다(soft delete 를 걸어놓고 FK cascade 가 덮음).
        트랜잭션으로 묶던 것도 불필요해졌다(단일 DELETE 라 원자적).

        SELF guard 는 호출자(public delete_*)가 책임. 본 helper 는 가드 통과
        가정 — 회원탈퇴(oauth)는 SELF 도 통과시켜야 하므로 본 메서드를
        직접 호출한다 (router 에서는 호출 금지).

        Args:
            profile: 삭제 대상 Profile 인스턴스.
        """
        await self.repository.soft_delete(profile)

    async def delete_profile(self, profile_id: UUID) -> None:
        """Delete profile (행을 물리 삭제) — 자식은 FK cascade.

        Args:
            profile_id: Profile UUID to delete.
        """
        profile = await self.get_profile(profile_id)
        await self.cascade_delete_profile(profile)

    async def delete_profile_with_owner_check(self, profile_id: UUID, account_id: UUID) -> None:
        """Delete profile with ownership verification — 자식 cascade.

        SELF 프로필은 계정 자체와 묶여 있어 삭제 금지 — 계정 탈퇴 흐름으로만 제거.

        Args:
            profile_id: Profile UUID to delete.
            account_id: Account UUID for ownership check.

        Raises:
            HTTPException: 403 if profile is SELF.
        """
        profile = await self.get_profile_with_owner_check(profile_id, account_id)
        if profile.relation_type == RelationType.SELF:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Cannot delete SELF profile. Use account withdrawal instead.",
            )
        await self.cascade_delete_profile(profile)

"""Prescription group service — CRUD + 입력값 검증.

BE 책임 원칙 (사용자 합의): 정렬 / 필터 / 탭 같은 표시 정책은 모두 FE 가
처리. 본 service 는 단순 list / detail / update / complete / delete + 약품 검색만 담당.

검색은 medication 테이블 join 이 필요해 BE 가 처리 (FE 가 약품 list 를 들고 있지 않음).
"""

from uuid import UUID

from fastapi import HTTPException, status
from tortoise.transactions import in_transaction

from app.dtos.prescription_group import (
    MedicationListItem,
    PrescriptionGroupCard,
    PrescriptionGroupDetail,
    PrescriptionGroupUpdate,
)
from app.models.medication import Medication
from app.models.prescription_group import PrescriptionGroup
from app.repositories.prescription_group_repository import PrescriptionGroupRepository
from app.repositories.profile_repository import ProfileRepository
from app.services.lifestyle_guide_service import LifestyleGuideService


class PrescriptionGroupService:
    """처방전 그룹 list / drill-down / mutation 서비스."""

    def __init__(self) -> None:
        self.repository = PrescriptionGroupRepository()
        self.profile_repository = ProfileRepository()
        self.lifestyle_guide_service = LifestyleGuideService()

    async def _verify_profile_ownership(self, profile_id: UUID, account_id: UUID) -> None:
        profile = await self.profile_repository.get_by_id(profile_id)
        if not profile:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Profile not found.")
        if profile.account_id != account_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied to this profile.")

    # ── 처방전 카드 list ─────────────────────────────────────────────────
    # 흐름: ownership 검증 -> 약품 검색 (선택) -> 약 수 + active 여부 집계
    #       -> PrescriptionGroupCard list 반환 (정렬 / 탭 필터는 FE 책임)
    async def list_groups_with_owner_check(
        self,
        profile_id: UUID,
        account_id: UUID,
        *,
        search: str | None = None,
    ) -> list[PrescriptionGroupCard]:
        """처방전 카드 list — ownership 검증 + (선택) 약품 검색.

        Args:
            profile_id: 조회 대상 프로필 UUID.
            account_id: 요청 계정 UUID (ownership 검증).
            search: 약품 이름 검색 — 이 약을 포함하는 그룹만 반환.

        Returns:
            검색 적용된 처방전 카드 list. 정렬 / 탭 필터는 FE derived 로 처리.
        """
        await self._verify_profile_ownership(profile_id, account_id)
        groups = await self._fetch_groups(profile_id, search)
        return [await self._build_card(g) for g in groups]

    async def _fetch_groups(
        self,
        profile_id: UUID,
        search: str | None,
    ) -> list[PrescriptionGroup]:
        """약품 검색이 적용된 그룹 query 결과 (created_at desc 단일 default).

        BE 는 응답을 단순 created_at 내림차순으로만 반환. FE 가 사용자 의도에
        따라 정렬 / 탭 필터를 derived 로 적용한다.
        """
        query = PrescriptionGroup.filter(profile_id=profile_id)
        if search:
            # 약품 이름 검색 — 그 약을 포함하는 group 만 필터 (medication join 필요).
            # ILIKE 부분일치 (대소문자 무시), 한글도 정상 매칭.
            matching_group_ids = (
                await Medication
                .filter(
                    profile_id=profile_id,
                    medicine_name__icontains=search,
                )
                .distinct()
                .values_list("prescription_group_id", flat=True)
            )
            matching_ids = [gid for gid in matching_group_ids if gid is not None]
            if not matching_ids:
                return []
            query = query.filter(id__in=matching_ids)
        return await query.order_by("-created_at").all()

    async def _build_card(self, group: PrescriptionGroup) -> PrescriptionGroupCard:
        """그룹 한 개의 카드 view 빌드 — medication 수 + active 여부 집계."""
        meds_count = await Medication.filter(prescription_group_id=group.id).count()
        active_count = await Medication.filter(
            prescription_group_id=group.id,
            is_active=True,
        ).count()
        return PrescriptionGroupCard(
            id=group.id,
            hospital_name=group.hospital_name,
            department=group.department,
            dispensed_date=group.dispensed_date,
            source=group.source,
            created_at=group.created_at,
            medications_count=meds_count,
            active_medications_count=active_count,
            has_active_medication=active_count > 0,
        )

    # ── drill-down: 단일 그룹 + 약 list ──────────────────────────────────
    async def get_group_with_owner_check(
        self,
        group_id: UUID,
        account_id: UUID,
    ) -> PrescriptionGroupDetail:
        """단일 그룹 + 그 안의 medication list (medicine_name 가나다 정렬).

        Args:
            group_id: 처방전 그룹 UUID.
            account_id: 요청 계정 UUID (그룹의 profile 이 이 계정 소속인지 검증).

        Returns:
            그룹 메타 + medication list.

        Raises:
            HTTPException: 404/403.
        """
        group = await self.repository.get_by_id(group_id)
        if not group:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Prescription group not found.")
        await self._verify_profile_ownership(group.profile_id, account_id)
        meds = await Medication.filter(prescription_group_id=group.id).order_by("medicine_name", "id").all()
        return PrescriptionGroupDetail(
            id=group.id,
            hospital_name=group.hospital_name,
            department=group.department,
            dispensed_date=group.dispensed_date,
            source=group.source,
            created_at=group.created_at,
            medications=[MedicationListItem.model_validate(m) for m in meds],
        )

    # ── 그룹 메타 update (department / hospital_name) ───────────────────
    async def update_group_with_owner_check(
        self,
        group_id: UUID,
        account_id: UUID,
        data: PrescriptionGroupUpdate,
    ) -> PrescriptionGroupDetail:
        """그룹 메타 부분 수정 (department / hospital_name).

        Pydantic ``model_fields_set`` 으로 사용자가 명시한 필드만 sentinel
        ``...`` 가 아닌 실제 값으로 repository 에 전달 → 부분 수정 보장.
        """
        group = await self.repository.get_by_id(group_id)
        if not group:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Prescription group not found.")
        await self._verify_profile_ownership(group.profile_id, account_id)
        kwargs: dict = {}
        kwargs["department"] = data.department if "department" in data.model_fields_set else ...
        kwargs["hospital_name"] = data.hospital_name if "hospital_name" in data.model_fields_set else ...
        await self.repository.update(group, **kwargs)
        return await self.get_group_with_owner_check(group_id, account_id)

    # ── 그룹 단위 "복용 완료" 처리 ─────────────────────────────────────
    # 흐름: 그룹 안 모든 medication.is_active=False -> 그룹 카드가 자동으로
    #       "복용 완료" 라벨 + 탭으로 분류 (has_active_medication derived).
    async def mark_completed_with_owner_check(
        self,
        group_id: UUID,
        account_id: UUID,
    ) -> PrescriptionGroupDetail:
        """사용자가 "이 처방전 복용 완료" 명시 시 호출 — 그룹 내 모든 medication 비활성화."""
        group = await self.repository.get_by_id(group_id)
        if not group:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Prescription group not found.")
        await self._verify_profile_ownership(group.profile_id, account_id)
        await Medication.filter(prescription_group_id=group.id).update(is_active=False)
        return await self.get_group_with_owner_check(group_id, account_id)

    # ── 그룹 단위 삭제 (cascade) ───────────────────────────────────────
    # 흐름: 그룹 행 삭제 -> medications.prescription_group_id 의 ON DELETE CASCADE
    #       가 약을 함께 삭제 -> 그 프로필의 active 가이드 cascade
    # medication 을 손으로 지우던 단계는 QA-01 에서 제거했다 — DB 가 이미 한다.
    async def delete_group_with_owner_check(
        self,
        group_id: UUID,
        account_id: UUID,
    ) -> None:
        """그룹 + 그 안 medication + 그 프로필의 active 가이드 cascade 삭제."""
        group = await self.repository.get_by_id(group_id)
        if not group:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Prescription group not found.")
        await self._verify_profile_ownership(group.profile_id, account_id)

        # 가이드는 별도 테이블 계보(profile -> lifestyle_guides)라 FK 로 안 따라온다.
        # 그룹 삭제와 가이드 삭제가 따로 놀지 않도록 한 트랜잭션에 묶는다.
        async with in_transaction():
            await self.repository.soft_delete(group)
            await self.lifestyle_guide_service.cascade_delete_active_guides_by_profile(group.profile_id)

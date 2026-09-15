"""Prescription group repository module.

Tortoise ORM 기반 처방전 그룹 CRUD. 그룹 자체는 OCR confirm / 수동 등록
시점에 자동 생성되며, 본 Repository 는 그 단순 INSERT 와 조회/소프트 삭제만
제공한다. medication / lifestyle_guide / challenge 의 FK 처리 로직은 각
도메인 service 가 책임.
"""

from datetime import date
from uuid import UUID, uuid4

from app.models.prescription_group import PrescriptionGroup, PrescriptionGroupSource


class PrescriptionGroupRepository:
    """Prescription group database repository."""

    async def create(
        self,
        profile_id: UUID | str,
        *,
        dispensed_date: date | None,
        department: str | None,
        hospital_name: str | None = None,
        source: PrescriptionGroupSource = PrescriptionGroupSource.OCR,
    ) -> PrescriptionGroup:
        """Create a new prescription group.

        Args:
            profile_id: 그룹 소유 프로필 UUID.
            dispensed_date: 처방 조제일 (없으면 NULL).
            department: 진료과 (없으면 NULL).
            hospital_name: 처방전 발행 병원 이름 (없으면 NULL).
            source: 생성 경로 — OCR / MANUAL / MIGRATED.

        Returns:
            Created PrescriptionGroup instance.
        """
        return await PrescriptionGroup.create(
            id=uuid4(),
            profile_id=str(profile_id),
            dispensed_date=dispensed_date,
            department=department,
            hospital_name=hospital_name,
            source=source.value,
        )

    async def get_by_id(self, group_id: UUID) -> PrescriptionGroup | None:
        """Get group by ID (excluding soft deleted)."""
        return await PrescriptionGroup.filter(
            id=group_id,
        ).first()

    async def get_all_by_profile(self, profile_id: UUID) -> list[PrescriptionGroup]:
        """Profile 의 모든 active 처방전 그룹 — 최근 처방일 기준 내림차순.

        dispensed_date NULL row 는 created_at 기준 정렬되도록 NULLS LAST.
        """
        return (
            await PrescriptionGroup
            .filter(
                profile_id=profile_id,
            )
            .order_by("-dispensed_date", "-created_at")
            .all()
        )

    async def update(
        self,
        group: PrescriptionGroup,
        *,
        department: str | None | type(...) = ...,
        hospital_name: str | None | type(...) = ...,
    ) -> PrescriptionGroup:
        """그룹 메타 부분 수정. ``...`` 인자는 미설정 (변경 안함).

        Args:
            group: 대상 그룹 인스턴스 (이미 로드됨).
            department: 새 진료과 값. ``None`` 으로 명시하면 NULL 로 set,
                생략(기본값 ``...``) 하면 변경 안함.
            hospital_name: 새 병원 이름. None=NULL, ... = 변경 안함.

        Returns:
            업데이트된 그룹.
        """
        if department is not ...:
            group.department = department  # type: ignore[assignment]
        if hospital_name is not ...:
            group.hospital_name = hospital_name  # type: ignore[assignment]
        await group.save()
        return group

    async def soft_delete(self, group: PrescriptionGroup) -> PrescriptionGroup:
        """Delete a prescription group row.

        ⚠️ 이름은 ``soft_delete`` 지만 **물리 삭제**다(QA-01, 2026-09-15).

        Args:
            group: Prescription group to delete.

        Returns:
            PrescriptionGroup: The (now deleted) instance.
        """
        await PrescriptionGroup.filter(id=group.id).delete()
        return group

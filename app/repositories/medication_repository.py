"""Medication repository module.

This module provides data access layer for the medications table,
handling prescription medication management operations.
"""

from collections import defaultdict
from datetime import date, datetime
from typing import cast
from uuid import UUID, uuid4

from tortoise.expressions import Q

from app.core import config
from app.dtos.medication import PrescriptionDateItem
from app.models.medication import Medication


class MedicationRepository:
    """Medication database repository for prescription management."""

    async def get_by_id(self, medication_id: UUID) -> Medication | None:
        """Get medication by ID.

        Args:
            medication_id: Medication UUID.

        Returns:
            Medication | None: Medication if found, None otherwise.
        """
        return await Medication.filter(
            id=medication_id,
        ).first()

    async def get_all_by_profile(self, profile_id: UUID) -> list[Medication]:
        """Get all medications for a profile.

        Args:
            profile_id: Profile UUID.

        Returns:
            list[Medication]: List of medications.
        """
        return await Medication.filter(
            profile_id=profile_id,
        ).all()

    async def get_all_by_profiles(self, profile_ids: list[UUID]) -> list[Medication]:
        """Get all medications for multiple profiles.

        Args:
            profile_ids: List of profile UUIDs.

        Returns:
            list[Medication]: List of medications.
        """
        if not profile_ids:
            return []
        return await Medication.filter(
            profile_id__in=profile_ids,
        ).all()

    async def get_active_by_prescription_group(self, group_id: UUID) -> list[Medication]:
        """Get currently active medications for a prescription group.

        그룹 단위 가이드 생성에서 사용 — 사용자가 선택한 처방전의 약물만 LLM
        프롬프트 입력으로 사용한다. 정렬은 ``get_active_by_profile`` 과 동일
        하게 medicine_name → id 안정 순서로 fingerprint 결정성 보장.

        Args:
            group_id: 처방전 그룹 UUID.

        Returns:
            list[Medication]: ordered active medications in this group.
        """
        today = datetime.now(tz=config.TIMEZONE).date()
        return (
            await Medication
            .filter(
                prescription_group_id=group_id,
                is_active=True,
            )
            .filter(Q(end_date__isnull=True) | Q(end_date__gte=today))
            .order_by("medicine_name", "id")
            .all()
        )

    async def get_active_by_profile(self, profile_id: UUID) -> list[Medication]:
        """Get currently active medications for a profile.

        Returned order is stable (medicine_name -> id tiebreak) so downstream
        consumers (특히 lifestyle-guide LLM 프롬프트) 가 같은 약 set 에 대해
        매번 같은 입력 텍스트를 받는다. ORDER BY 없는 쿼리는 PostgreSQL 에서
        결과 순서가 undefined 라 동일 입력에 대한 LLM 결정성을 깨뜨린다.

        Args:
            profile_id: Profile UUID.

        Returns:
            list[Medication]: List of active medications, ordered by
                medicine_name then id.
        """
        today = datetime.now(tz=config.TIMEZONE).date()
        return (
            await Medication
            .filter(
                profile_id=profile_id,
                is_active=True,
            )
            .filter(Q(end_date__isnull=True) | Q(end_date__gte=today))
            .order_by("medicine_name", "id")
            .all()
        )

    async def get_inactive_by_profile(self, profile_id: UUID) -> list[Medication]:
        """Get completed or expired medications for a profile.

        Args:
            profile_id: Profile UUID.

        Returns:
            list[Medication]: List of inactive medications (manually completed or past end_date).
        """
        today = datetime.now(tz=config.TIMEZONE).date()
        return (
            await Medication
            .filter(
                profile_id=profile_id,
            )
            .filter(Q(is_active=False) | Q(end_date__lt=today, end_date__isnull=False))
            .all()
        )

    async def get_prescription_dates_by_profile(self, profile_id: UUID) -> list[PrescriptionDateItem]:
        """Get prescription date summary grouped by date and department for a profile.

        Uses dispensed_date if available, falls back to start_date.
        Results are sorted by date descending.

        Args:
            profile_id: Profile UUID.

        Returns:
            list[PrescriptionDateItem]: Grouped and sorted prescription date items.
        """
        medications = await Medication.filter(
            profile_id=profile_id,
        ).all()

        counts: defaultdict[tuple[date, str | None], int] = defaultdict(int)
        for med in medications:
            key_date = med.dispensed_date or med.start_date
            counts[(key_date, med.department)] += 1

        return sorted(
            [
                PrescriptionDateItem(prescription_date=key_date, department=dept, count=cnt)
                for (key_date, dept), cnt in counts.items()
            ],
            key=lambda item: item.prescription_date,
            reverse=True,
        )

    async def create(
        self,
        profile_id: UUID,
        medicine_name: str,
        intake_times: list[str],
        total_intake_count: int,
        remaining_intake_count: int,
        start_date: date,
        dose_per_intake: str | None = None,
        intake_instruction: str | None = None,
        end_date: date | None = None,
        dispensed_date: date | None = None,
        expiration_date: date | None = None,
        prescription_group_id: UUID | None = None,
    ) -> Medication:
        """Create new medication.

        Args:
            profile_id: Profile UUID.
            medicine_name: Name of medication.
            intake_times: List of daily intake times.
            total_intake_count: Total prescribed intake count.
            remaining_intake_count: Remaining intake count.
            start_date: Medication start date.
            dose_per_intake: Optional dosage per intake.
            intake_instruction: Optional intake instructions.
            end_date: Optional expected end date.
            dispensed_date: Optional dispensing date.
            expiration_date: Optional expiration date.
            prescription_group_id: 소속 처방전 그룹 UUID — 호출 측 service 가
                OCR/MANUAL 흐름에서 그룹을 먼저 만든 뒤 전달한다.

        Returns:
            Medication: Created medication.
        """
        return await Medication.create(
            id=uuid4(),
            profile_id=profile_id,
            prescription_group_id=prescription_group_id,
            medicine_name=medicine_name,
            dose_per_intake=dose_per_intake,
            intake_instruction=intake_instruction,
            intake_times=intake_times,
            total_intake_count=total_intake_count,
            remaining_intake_count=remaining_intake_count,
            start_date=start_date,
            end_date=end_date,
            dispensed_date=dispensed_date,
            expiration_date=expiration_date,
            is_active=True,
        )

    async def decrement_remaining_count(self, medication: Medication) -> Medication:
        """Decrement remaining intake count by one (minimum 0).

        Args:
            medication: Medication to update.

        Returns:
            Medication: Updated medication.
        """
        if medication.remaining_intake_count <= 0:
            return medication
        medication.remaining_intake_count -= 1
        await medication.save()
        return medication

    async def update(self, medication: Medication, **kwargs) -> Medication:
        """Update medication information.

        Args:
            medication: Medication to update.
            **kwargs: Fields to update.

        Returns:
            Medication: Updated medication.
        """
        await medication.update_from_dict(kwargs).save()
        return medication

    async def soft_delete(self, medication: Medication) -> Medication:
        """Delete a medication row.

        ⚠️ 이름은 ``soft_delete`` 지만 **물리 삭제**다(QA-01, 2026-09-15).
        호출처가 많아 이름만 남기고 동작을 통일했다.

        Args:
            medication: Medication to delete.

        Returns:
            Medication: The (now deleted) instance.
        """
        await Medication.filter(id=medication.id).delete()
        return medication

    async def bulk_soft_delete(
        self,
        ids: list[UUID],
        profile_ids: list[UUID],
    ) -> int:
        """다건 삭제 — 단일 DELETE 로 처리하고 삭제된 row 수를 반환.

        ⚠️ 이름과 달리 **물리 삭제**다(QA-01). ownership 은 ``profile_ids`` 로 좁혀
        강제한다(호출자가 계정 소유 프로필 목록을 미리 계산해 전달).

        Args:
            ids: 삭제할 medication ID 목록.
            profile_ids: 계정이 소유한 프로필 ID 목록 (ownership scope).

        Returns:
            삭제된 row 수.
        """
        if not ids or not profile_ids:
            return 0
        return await Medication.filter(id__in=ids, profile_id__in=profile_ids).delete()

    async def find_deletable_ids(self, ids: list[UUID], profile_ids: list[UUID]) -> list[UUID]:
        """삭제 가능한(존재 + 본인 소유) id 만 골라 돌려준다.

        hard delete 로 바뀌면서 필요해졌다. 전에는 삭제 **후** ``deleted_at IS NOT NULL``
        로 "방금 지운 것"을 되짚었는데, **행이 사라지면 사후에 알아낼 수 없다.**
        그래서 지우기 **전에** 대상을 확정한다(QA-01).

        Args:
            ids: 요청된 medication ID 목록.
            profile_ids: 요청자가 소유한 프로필 ID 목록.

        Returns:
            실제로 지울 수 있는 ID 목록.
        """
        if not ids or not profile_ids:
            return []
        rows = await Medication.filter(id__in=ids, profile_id__in=profile_ids).values_list("id", flat=True)
        # flat=True 라 실제로는 UUID 의 평평한 목록이지만, Tortoise 의 반환 타입은
        # tuple 목록으로 선언돼 있어 그대로는 타입이 맞지 않는다.
        return [cast("UUID", row) for row in rows]

    async def bulk_soft_delete_by_profile(self, profile_id: UUID) -> int:
        """프로필의 모든 medication 을 일괄 삭제한다.

        ⚠️ 이름과 달리 **물리 삭제**다(QA-01). 멱등하다 — 이미 없는 행은 0건으로 센다.

        Args:
            profile_id: 대상 프로필 UUID.

        Returns:
            삭제된 row 수.
        """
        return await Medication.filter(profile_id=profile_id).delete()

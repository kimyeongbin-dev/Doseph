"""Lifestyle guide repository module.

This module provides data access layer for the lifestyle_guides table,
handling guide creation, async-pipeline state transitions and retrieval.
"""

from datetime import datetime
from uuid import UUID, uuid4

from app.core import config
from app.models.lifestyle_guide import LifestyleGuide, LifestyleGuideStatusValue


class LifestyleGuideRepository:
    """Lifestyle guide database repository for guide management."""

    async def create(
        self,
        profile_id: UUID,
        content: dict,
        medication_snapshot: list[dict],
    ) -> LifestyleGuide:
        """Create a new ready-state lifestyle guide record (legacy/sync path).

        Kept for callers that already have GPT content in hand. The async
        pipeline uses ``create_pending`` + ``mark_ready`` instead.

        Args:
            profile_id: Owner profile UUID.
            content: GPT-generated guide content dict (5 categories).
            medication_snapshot: Active medication list serialized as dicts.

        Returns:
            LifestyleGuide: Created guide instance.
        """
        return await LifestyleGuide.create(
            id=uuid4(),
            profile_id=profile_id,
            content=content,
            medication_snapshot=medication_snapshot,
            status=LifestyleGuideStatusValue.READY.value,
            processed_at=datetime.now(tz=config.TIMEZONE),
        )

    async def create_pending(
        self,
        profile_id: UUID,
        medication_snapshot: list[dict],
        input_fingerprint: str | None = None,
        prescription_group_id: UUID | None = None,
    ) -> LifestyleGuide:
        """Insert a pending guide row — RQ producer 진입점.

        Status='pending', content={} 로 행을 만든다. ai-worker 가
        ``mark_ready`` 또는 ``mark_terminal`` 로 마무리한다.

        Args:
            profile_id: Owner profile UUID.
            medication_snapshot: Snapshot of active meds (이후 LLM 입력).
            input_fingerprint: 동일 입력 dedupe 용 SHA-256 hex (Phase B).
            prescription_group_id: 가이드를 만들 처방전 그룹 UUID (v3 — 처방전
                단위 가이드). 기존 호출자(테스트 등) 호환 위해 nullable.

        Returns:
            새로 INSERT 된 ``LifestyleGuide`` 인스턴스.
        """
        return await LifestyleGuide.create(
            id=uuid4(),
            profile_id=profile_id,
            content={},
            medication_snapshot=medication_snapshot,
            status=LifestyleGuideStatusValue.PENDING.value,
            input_fingerprint=input_fingerprint,
            prescription_group_id=prescription_group_id,
        )

    async def get_ready_by_fingerprint(
        self,
        profile_id: UUID,
        input_fingerprint: str,
    ) -> LifestyleGuide | None:
        """동일 입력 fingerprint 의 ready 가이드를 찾아 반환 (Phase B dedupe).

        Args:
            profile_id: Owner profile UUID.
            input_fingerprint: SHA-256 hex of canonical input.

        Returns:
            매칭되는 ready 가이드 (가장 최근). 없으면 None.
        """
        return (
            await LifestyleGuide
            .filter(
                profile_id=profile_id,
                input_fingerprint=input_fingerprint,
                status=LifestyleGuideStatusValue.READY.value,
            )
            .order_by("-created_at")
            .first()
        )

    async def mark_ready(self, guide_id: UUID | str, content: dict) -> int:
        """ai-worker — content 채우고 status='ready' + processed_at 기록.

        Args:
            guide_id: Pending 가이드 ID.
            content: ``LlmGuideResponse.model_dump(exclude={'recommended_challenges'})``.

        Returns:
            UPDATE 된 row 수 (정상 1, 사용자가 사이에 삭제했으면 0).
        """
        return await LifestyleGuide.filter(id=guide_id).update(
            status=LifestyleGuideStatusValue.READY.value,
            content=content,
            processed_at=datetime.now(tz=config.TIMEZONE),
        )

    async def set_revealed_challenge_count(
        self,
        guide_id: UUID | str,
        new_count: int,
    ) -> int:
        """노출 챌린지 수를 *절대값* 으로 set (단일 UPDATE).

        호출자가 사전에 한도(15) 검증 + min(15) 클램핑한 뒤 호출. atomic UPDATE
        라 동시 클릭이 와도 race-free.

        Args:
            guide_id: 대상 가이드 UUID.
            new_count: 새 노출 카운트 (5 / 10 / 15 중 하나).

        Returns:
            UPDATE 된 row 수 (정상 1).
        """
        return await LifestyleGuide.filter(id=guide_id).update(
            revealed_challenge_count=new_count,
        )

    async def mark_terminal(
        self,
        guide_id: UUID | str,
        status: LifestyleGuideStatusValue,
    ) -> int:
        """ai-worker — terminal status (no_active_meds / failed) 로 마감.

        ``ready`` 는 ``mark_ready`` 가 content 와 함께 처리하므로 여기 들어오면 안 된다.

        Args:
            guide_id: Pending 가이드 ID.
            status: terminal status.

        Returns:
            UPDATE 된 row 수.
        """
        return await LifestyleGuide.filter(id=guide_id).update(
            status=status.value,
            processed_at=datetime.now(tz=config.TIMEZONE),
        )

    async def get_by_id(self, guide_id: UUID) -> LifestyleGuide | None:
        """Get guide by primary key.

        Args:
            guide_id: Guide UUID.

        Returns:
            LifestyleGuide | None: Guide if found, None otherwise.
        """
        return await LifestyleGuide.filter(id=guide_id).first()

    async def get_latest_by_profile(self, profile_id: UUID) -> LifestyleGuide | None:
        """Get most recently created guide for a profile.

        Args:
            profile_id: Profile UUID.

        Returns:
            LifestyleGuide | None: Latest guide or None.
        """
        return await LifestyleGuide.filter(profile_id=profile_id).order_by("-created_at").first()

    async def get_all_by_profile(self, profile_id: UUID) -> list[LifestyleGuide]:
        """Get all guides for a profile ordered by newest first.

        Args:
            profile_id: Profile UUID.

        Returns:
            list[LifestyleGuide]: List of guides newest first.
        """
        return await LifestyleGuide.filter(profile_id=profile_id).order_by("-created_at").all()

    async def delete_by_id(self, guide_id: UUID) -> None:
        """Hard-delete a lifestyle guide by ID.

        Args:
            guide_id: Guide UUID to delete.
        """
        await LifestyleGuide.filter(id=guide_id).delete()

    async def bulk_delete_by_profile(self, profile_id: UUID) -> int:
        """프로필의 모든 lifestyle guide 일괄 hard-delete.

        Profile cascade 삭제 흐름의 일부로 호출된다.

        Args:
            profile_id: 대상 프로필 UUID.

        Returns:
            삭제된 row 수.
        """
        return await LifestyleGuide.filter(profile_id=profile_id).delete()

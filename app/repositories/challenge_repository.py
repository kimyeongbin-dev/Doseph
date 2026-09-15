"""Challenge repository module.

This module provides data access layer for the challenges table,
handling user health challenge tracking operations.
"""

from datetime import date, datetime
from uuid import UUID, uuid4

from app.core import config
from app.dtos.lifestyle_guide import RecommendedChallenge
from app.models.challenge import Challenge

# 한 set 의 target_days 분배 (1·7·14·14·21). 사용자 노출 단위.
_SLOT_PATTERN = (1, 7, 14, 14, 21)
_SLOTS_PER_SET = len(_SLOT_PATTERN)


def _assign_slot_order(
    challenges: list[RecommendedChallenge],
) -> list[RecommendedChallenge]:
    """LLM 의 15개 챌린지를 set 단위 round-robin 으로 재배열.

    각 set 의 노출 순서는 ``_SLOT_PATTERN`` (1·7·14·14·21) 을 따른다.
    LLM 이 분배 규칙을 어겼으면(=각 target_days bucket 의 개수가 패턴과 다름)
    안전하게 입력 순서를 그대로 반환 (fallback).

    Args:
        challenges: LLM 응답의 RecommendedChallenge 리스트.

    Returns:
        slot_index 순서로 재배열된 동일 객체 리스트.
    """
    if not challenges:
        return []

    # target_days 별 buckets — FIFO. LLM 출력 순서 그대로 보존.
    buckets: dict[int, list[RecommendedChallenge]] = {}
    for ch in challenges:
        buckets.setdefault(ch.target_days, []).append(ch)

    # 패턴 검증 — 각 day 마다 패턴이 요구하는 개수의 N배(=set 수) 가 있어야 함.
    from collections import Counter

    required_per_set = Counter(_SLOT_PATTERN)
    sets_needed = len(challenges) // _SLOTS_PER_SET
    if len(challenges) % _SLOTS_PER_SET != 0:
        return list(challenges)
    for day, count in required_per_set.items():
        if len(buckets.get(day, [])) != count * sets_needed:
            return list(challenges)

    ordered: list[RecommendedChallenge] = []
    for _ in range(sets_needed):
        ordered.extend(buckets[day].pop(0) for day in _SLOT_PATTERN)
    return ordered


class ChallengeRepository:
    """Challenge database repository for health challenge management."""

    async def get_by_id(self, challenge_id: UUID) -> Challenge | None:
        """Get challenge by ID.

        Args:
            challenge_id: Challenge UUID.

        Returns:
            Challenge | None: Challenge if found, None otherwise.
        """
        return await Challenge.filter(
            id=challenge_id,
        ).first()

    async def get_all_by_profile(self, profile_id: UUID) -> list[Challenge]:
        """Get all challenges for a profile.

        ORDER BY target_days -> title 가나다 -> id 로 안정 정렬 (사용자 합의).
        FE store 의 base list 가 매번 같은 순서가 되어 challengesByGuide /
        activeChallenges 등 모든 selector 결과가 결정적이 된다.

        Args:
            profile_id: Profile UUID.

        Returns:
            list[Challenge]: 기간 짧은 순 → 제목 가나다 → id tiebreak.
        """
        return (
            await Challenge
            .filter(
                profile_id=profile_id,
            )
            .order_by("target_days", "title", "id")
            .all()
        )

    async def get_all_by_profiles(self, profile_ids: list[UUID]) -> list[Challenge]:
        """Get all challenges for multiple profiles.

        Args:
            profile_ids: List of profile UUIDs.

        Returns:
            list[Challenge]: List of challenges.
        """
        if not profile_ids:
            return []
        return await Challenge.filter(
            profile_id__in=profile_ids,
        ).all()

    async def get_by_guide_id(
        self,
        guide_id: UUID,
        limit: int | None = None,
    ) -> list[Challenge]:
        """Get challenges linked to a specific lifestyle guide.

        Returned order:
          1순위 ``slot_index`` asc (15개 챌린지 set 단위 round-robin 으로 미리 부여 —
            5개씩 잘라도 1·7·14·14·21 분배가 항상 같은 비율).
          2순위 (slot_index 가 NULL 인 legacy row 호환): target_days asc.
          3·4순위 안정 정렬용 title 가나다 → id tiebreak.

        Args:
            guide_id: LifestyleGuide UUID.
            limit: 가이드의 ``revealed_challenge_count`` 만큼만 반환하기 위한
                옵션. None 이면 전체 (가이드 삭제 cascade / 관리 용도).

        Returns:
            list[Challenge]: 정렬된 챌린지 (limit 적용 시 앞 N 개 — 5개씩 set 단위).
        """
        # PostgreSQL 은 ORDER BY 컬럼이 NULL 일 때 기본 ASC NULLS LAST. legacy row
        # 가 항상 신규 row(0~14) 뒤로 가게 두고, 그 안에서 target_days 로 보조 정렬.
        query = Challenge.filter(
            guide_id=guide_id,
        ).order_by("slot_index", "target_days", "title", "id")
        if limit is not None:
            query = query.limit(limit)
        return await query.all()

    async def get_active_by_profile(self, profile_id: UUID) -> list[Challenge]:
        """Get active challenges for a profile.

        Args:
            profile_id: Profile UUID.

        Returns:
            list[Challenge]: List of active challenges.
        """
        return await Challenge.filter(
            profile_id=profile_id,
            challenge_status="IN_PROGRESS",
        ).all()

    async def create(
        self,
        profile_id: UUID,
        title: str,
        target_days: int,
        started_date: date,
        description: str | None = None,
        difficulty: str | None = None,
    ) -> Challenge:
        """Create new challenge.

        Args:
            profile_id: Profile UUID.
            title: Challenge title.
            target_days: Target completion days.
            started_date: Challenge start date.
            description: Optional challenge description.
            difficulty: Optional difficulty level (쉬움/보통/어려움).

        Returns:
            Challenge: Created challenge.
        """
        return await Challenge.create(
            id=uuid4(),
            profile_id=profile_id,
            title=title,
            description=description,
            target_days=target_days,
            difficulty=difficulty,
            started_date=started_date,
            completed_dates=[],
            challenge_status="IN_PROGRESS",
        )

    async def bulk_create_from_guide(
        self,
        guide_id: UUID,
        profile_id: UUID,
        challenges: list[RecommendedChallenge],
        prescription_group_id: UUID | None = None,
    ) -> list[Challenge]:
        """Bulk create LLM-recommended challenges tied to a guide.

        All created challenges start with is_active=False (pending user activation).

        ``slot_index`` 부여 정책 — "추천 챌린지 더 보기" 5개씩 노출 시에도 1·7·14·
        14·21 기간 분배가 항상 같은 비율로 보이도록 set 단위 round-robin:
          - target_days 로 buckets 분리 (1, 7, 14, 14, 21 의 멀티셋 가정).
          - bucket 내 챌린지를 5개씩 묶어 set #0/#1/#2 로 분배.
          - 각 set 안에서 1일·7일·14일·14일·21일 5개를 ``slot_index`` 0~4 로 부여.
          - 다음 set 은 5~9, 그다음 set 은 10~14.
        LLM 이 prompt 규칙을 어겨 분배가 비대칭이면 fallback 으로 입력 순서를 그대로 사용.

        Args:
            guide_id: Source LifestyleGuide UUID.
            profile_id: Owner profile UUID.
            challenges: Parsed recommended challenge list from LLM response.
            prescription_group_id: 가이드와 함께 묶인 처방전 그룹 UUID (v3+).
                ``/challenge`` 페이지에서 처방전 별 분류 view 를 위해 챌린지에도
                동시에 기록한다. legacy 호환 위해 nullable.

        Returns:
            list[Challenge]: List of created challenge instances (slot_index 순).
        """
        today = datetime.now(tz=config.TIMEZONE).date()
        ordered = _assign_slot_order(challenges)
        created: list[Challenge] = []
        for slot_index, ch in enumerate(ordered):
            challenge = await Challenge.create(
                id=uuid4(),
                profile_id=profile_id,
                guide_id=guide_id,
                prescription_group_id=prescription_group_id,
                category=ch.category,
                title=ch.title,
                description=ch.description,
                target_days=ch.target_days,
                difficulty=ch.difficulty,
                started_date=today,
                completed_dates=[],
                challenge_status="IN_PROGRESS",
                is_active=False,
                slot_index=slot_index,
            )
            created.append(challenge)
        return created

    async def update(self, challenge: Challenge, **kwargs) -> Challenge:
        """Update challenge information.

        Args:
            challenge: Challenge to update.
            **kwargs: Fields to update.

        Returns:
            Challenge: Updated challenge.
        """
        await challenge.update_from_dict(kwargs).save()
        return challenge

    async def soft_delete(self, challenge: Challenge) -> Challenge:
        """Delete a challenge row.

        ⚠️ 이름은 ``soft_delete`` 지만 **행을 물리 삭제한다**(QA-01, 2026-09-15).
        호출처가 많아 이름은 남기고 동작만 통일했다 — 이름 정리는 별건으로 둔다.

        왜 hard delete 인가:
            `challenges.guide_id` 의 FK 가 ``ON DELETE CASCADE`` 라, 가이드를 지우면
            어차피 행이 물리 삭제됐다. soft delete 는 **한 줄 뒤에 덮이는 장부**였고
            주석과 실제가 달랐다. 삭제 의미론을 hard delete 로 통일한다.

        Args:
            challenge: Challenge to delete.

        Returns:
            Challenge: The (now deleted) challenge instance.
        """
        await Challenge.filter(id=challenge.id).delete()
        return challenge

    async def bulk_soft_delete_by_profile(self, profile_id: UUID) -> int:
        """프로필의 모든 challenge 를 일괄 삭제한다.

        ⚠️ 이름과 달리 **물리 삭제**다(QA-01). 멱등하다 — 이미 없는 행은 0건으로 센다.

        Args:
            profile_id: 대상 프로필 UUID.

        Returns:
            삭제된 row 수.
        """
        return await Challenge.filter(profile_id=profile_id).delete()

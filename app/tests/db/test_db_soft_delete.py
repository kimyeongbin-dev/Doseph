"""Prove the soft-delete filters actually hide deleted rows.

``app/CLAUDE.md`` 의 코드리뷰 체크리스트가 **"Soft delete 필터 적용 여부"** 를
필수 항목으로 못 박고 있는데, 지금까지 그걸 검사하는 수단은 **사람 눈뿐**이었다.
리포지토리 메서드가 늘어날수록 ``deleted_at__isnull=True`` 를 **하나만 빠뜨려도**
삭제된 데이터가 다시 노출된다. 그리고 그건 조용히 일어난다.

이 파일은 "필터가 코드에 적혀 있는가"가 아니라 **"삭제한 행이 실제로 안 나오는가"** 를
묻는다. 전자는 grep 으로 되지만 후자는 행을 만들어 지워봐야만 알 수 있다.
"""

from datetime import UTC, datetime

import pytest

from app.repositories.challenge_repository import ChallengeRepository
from app.repositories.chat_session_repository import ChatSessionRepository
from app.repositories.medication_repository import MedicationRepository
from app.repositories.prescription_group_repository import PrescriptionGroupRepository
from app.tests.db.conftest import (
    create_account,
    create_challenge,
    create_chat_session,
    create_medication,
    create_prescription_group,
    create_profile,
)

pytestmark = [pytest.mark.db, pytest.mark.asyncio(loop_scope="session")]


# ── 처방전 그룹 ───────────────────────────────────────────────────────
# 흐름: 2건 생성 -> 1건 soft delete -> 목록 조회에 살아 있는 1건만
async def test_deleted_prescription_group_disappears_from_list(db: None) -> None:
    """A soft-deleted prescription group must not appear in listings."""
    account = await create_account()
    profile = await create_profile(account)
    kept = await create_prescription_group(profile, hospital_name="살아있는의원")
    removed = await create_prescription_group(profile, hospital_name="지워진의원")

    removed.deleted_at = datetime.now(UTC)
    await removed.save()

    groups = await PrescriptionGroupRepository().get_all_by_profile(profile.id)
    ids = {group.id for group in groups}

    assert kept.id in ids, "삭제하지 않은 처방전은 계속 보여야 한다"
    assert removed.id not in ids, "soft delete 한 처방전이 목록에 남아 있다 — 필터가 빠졌다"


# ── 복약 ──────────────────────────────────────────────────────────────
async def test_deleted_medication_disappears_from_list(db: None) -> None:
    """A soft-deleted medication must not appear in listings."""
    account = await create_account()
    profile = await create_profile(account)
    group = await create_prescription_group(profile)
    kept = await create_medication(profile, group, medicine_name="살아있는정")
    removed = await create_medication(profile, group, medicine_name="지워진정")

    removed.deleted_at = datetime.now(UTC)
    await removed.save()

    medications = await MedicationRepository().get_all_by_profile(profile.id)
    ids = {medication.id for medication in medications}

    assert kept.id in ids
    assert removed.id not in ids, "soft delete 한 복약이 목록에 남아 있다 — 필터가 빠졌다"


# ── 챌린지 ────────────────────────────────────────────────────────────
async def test_deleted_challenge_disappears_from_list(db: None) -> None:
    """A soft-deleted challenge must not appear in listings."""
    account = await create_account()
    profile = await create_profile(account)
    kept = await create_challenge(profile, title="살아있는챌린지")
    removed = await create_challenge(profile, title="지워진챌린지")

    removed.deleted_at = datetime.now(UTC)
    await removed.save()

    challenges = await ChallengeRepository().get_all_by_profile(profile.id)
    ids = {challenge.id for challenge in challenges}

    assert kept.id in ids
    assert removed.id not in ids, "soft delete 한 챌린지가 목록에 남아 있다 — 필터가 빠졌다"


# ── 대화 세션 ─────────────────────────────────────────────────────────
async def test_deleted_chat_session_disappears_from_list(db: None) -> None:
    """A soft-deleted chat session must not appear in listings."""
    account = await create_account()
    profile = await create_profile(account)
    kept = await create_chat_session(account, profile, title="살아있는대화")
    removed = await create_chat_session(account, profile, title="지워진대화")

    removed.deleted_at = datetime.now(UTC)
    await removed.save()

    sessions = await ChatSessionRepository().get_by_profile(profile.id)
    ids = {session.id for session in sessions}

    assert kept.id in ids
    assert removed.id not in ids, "soft delete 한 세션이 목록에 남아 있다 — 필터가 빠졌다"


# ── 단건 조회도 같은 규칙을 따르는가 ──────────────────────────────────
# 흐름: 목록만 거르고 단건 조회는 안 거르는 경우가 실제로 흔하다
#       -> 삭제한 행을 id 로 직접 집어도 안 나와야 한다
async def test_deleted_rows_are_not_reachable_by_id(db: None) -> None:
    """Fetching a soft-deleted row by id must not return it either."""
    account = await create_account()
    profile = await create_profile(account)
    group = await create_prescription_group(profile)
    medication = await create_medication(profile, group)

    medication.deleted_at = datetime.now(UTC)
    await medication.save()

    found = await MedicationRepository().get_by_id(medication.id)

    assert found is None, "삭제한 복약이 id 직접 조회로 되살아난다 — 단건 경로에 필터가 빠졌다"

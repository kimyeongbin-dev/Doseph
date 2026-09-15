"""Prove that deleting a row actually removes it.

QA-01(2026-09-15)로 삭제 의미론이 **hard delete 로 통일**되면서 이 파일의 질문도 바뀌었다.

    전: "soft delete 필터가 지워진 행을 가리는가"
    후: **"삭제한 행이 정말 사라졌는가"**

왜 바뀌었나: FK 20개가 전부 ``ON DELETE CASCADE`` 라 부모를 지우면 자식은 DB 가
물리 삭제했다. 그 위에 얹힌 soft delete 장부는 **한 줄 뒤에 덮이는** 반쪽이었고,
주석과 실제가 달랐다(잠금-불일치).

여전히 grep 으로는 알 수 없다 — 행을 만들어 지워봐야 한다.
"""

import pytest

from app.models.challenge import Challenge
from app.models.chat_sessions import ChatSession
from app.models.medication import Medication
from app.models.prescription_group import PrescriptionGroup
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
async def test_deleted_prescription_group_row_is_gone(db: None) -> None:
    """A deleted prescription group must be physically removed."""
    account = await create_account()
    profile = await create_profile(account)
    kept = await create_prescription_group(profile, hospital_name="살아있는의원")
    removed = await create_prescription_group(profile, hospital_name="지워진의원")

    await PrescriptionGroupRepository().soft_delete(removed)

    groups = await PrescriptionGroupRepository().get_all_by_profile(profile.id)
    ids = {group.id for group in groups}

    assert kept.id in ids, "삭제하지 않은 처방전은 계속 보여야 한다"
    assert removed.id not in ids, "삭제한 처방전이 목록에 남아 있다"
    assert await PrescriptionGroup.filter(id=removed.id).count() == 0, "행이 남아 있다"


# ── 복약 ──────────────────────────────────────────────────────────────
async def test_deleted_medication_row_is_gone(db: None) -> None:
    """A deleted medication must be physically removed."""
    account = await create_account()
    profile = await create_profile(account)
    group = await create_prescription_group(profile)
    kept = await create_medication(profile, group, medicine_name="살아있는정")
    removed = await create_medication(profile, group, medicine_name="지워진정")

    await MedicationRepository().soft_delete(removed)

    medications = await MedicationRepository().get_all_by_profile(profile.id)
    ids = {medication.id for medication in medications}

    assert kept.id in ids
    assert removed.id not in ids, "삭제한 복약이 목록에 남아 있다"
    assert await Medication.filter(id=removed.id).count() == 0, "행이 남아 있다"


# ── 챌린지 — hard delete 로 전환됨 (QA-01, 2026-09-15) ────────────────
# 흐름: 2건 생성 -> 1건 삭제 -> 목록에 없고 **행 자체가 사라졌는지**까지 확인
# soft delete 를 폐지했으므로 "필터가 거르는가"가 아니라 "정말 없는가"를 묻는다.
async def test_deleted_challenge_row_is_gone(db: None) -> None:
    """A deleted challenge must be physically removed, not just filtered."""
    account = await create_account()
    profile = await create_profile(account)
    kept = await create_challenge(profile, title="살아있는챌린지")
    removed = await create_challenge(profile, title="지워진챌린지")

    await ChallengeRepository().soft_delete(removed)

    challenges = await ChallengeRepository().get_all_by_profile(profile.id)
    ids = {challenge.id for challenge in challenges}

    assert kept.id in ids, "삭제하지 않은 챌린지는 계속 보여야 한다"
    assert removed.id not in ids, "삭제한 챌린지가 목록에 남아 있다"
    assert await Challenge.filter(id=removed.id).count() == 0, (
        "행이 남아 있다 — soft delete 가 아직 살아 있다(QA-01 은 hard delete 통일)"
    )


# ── 대화 세션 ─────────────────────────────────────────────────────────
async def test_deleted_chat_session_row_is_gone(db: None) -> None:
    """A deleted chat session must be physically removed."""
    account = await create_account()
    profile = await create_profile(account)
    kept = await create_chat_session(account, profile, title="살아있는대화")
    removed = await create_chat_session(account, profile, title="지워진대화")

    await ChatSessionRepository().soft_delete(removed)

    sessions = await ChatSessionRepository().get_by_profile(profile.id)
    ids = {session.id for session in sessions}

    assert kept.id in ids
    assert removed.id not in ids, "삭제한 세션이 목록에 남아 있다"
    assert await ChatSession.filter(id=removed.id).count() == 0, "행이 남아 있다"


# ── 단건 조회도 같은 규칙을 따르는가 ──────────────────────────────────
# 흐름: 목록만 거르고 단건 조회는 안 거르는 경우가 실제로 흔하다
#       -> 삭제한 행을 id 로 직접 집어도 안 나와야 한다
async def test_deleted_rows_are_not_reachable_by_id(db: None) -> None:
    """Fetching a deleted row by id must not return it either."""
    account = await create_account()
    profile = await create_profile(account)
    group = await create_prescription_group(profile)
    medication = await create_medication(profile, group)

    await MedicationRepository().soft_delete(medication)

    found = await MedicationRepository().get_by_id(medication.id)

    assert found is None, "삭제한 복약이 id 직접 조회로 되살아난다"

"""Prove the cascade policy on real rows, not on mock call counts.

지금까지 cascade 검증은 ``app/tests/test_soft_delete_cascade.py`` 가 전부였는데,
그건 리포지토리를 통째로 ``AsyncMock`` 으로 바꿔 놓고 **"그 메서드가 호출됐는가"**
만 본다. 구현을 복사한 tautological 테스트라, 정책이 틀려도 호출 순서만 같으면
초록이다.

정책이 **조건부**라 이게 특히 위험하다:

    처방전 그룹 삭제
      -> 그 프로필의 활성 가이드 정리
         -> 미시작 챌린지(is_active=False)  : soft delete
         -> 활성/완료 챌린지(is_active=True): guide_id 만 끊고 **보존**

"사용자가 이미 진행한 것은 남긴다"는 제품 결정이고, 코드만 읽어선 확신이 안 선다.
게다가 FE 가 이 동작에 기대어 캐시를 invalidate 한다.

여기서는 행을 실제로 만들고 지운 뒤 **남았는가/사라졌는가**를 본다.
"""

from datetime import UTC, datetime

import pytest

from app.models.challenge import Challenge
from app.models.lifestyle_guide import LifestyleGuide
from app.models.medication import Medication
from app.services.medication_service import MedicationService
from app.tests.db.conftest import (
    create_account,
    create_challenge,
    create_lifestyle_guide,
    create_medication,
    create_prescription_group,
    create_profile,
)

pytestmark = [pytest.mark.db, pytest.mark.asyncio(loop_scope="session")]


# ── 처방전 그룹 삭제 -> 약이 함께 정리되는가 ─────────────────────────
# 흐름: 계정/프로필/그룹/약 생성 -> 그룹 삭제 -> 약이 soft delete 됐는지 직접 확인
async def test_deleting_prescription_group_soft_deletes_its_medications(db: None) -> None:
    """Deleting a prescription group must soft-delete its medications."""
    account = await create_account()
    profile = await create_profile(account)
    group = await create_prescription_group(profile)
    medication = await create_medication(profile, group)

    await MedicationService().delete_prescription_group_with_owner_check(
        ids=[medication.id],
        profile_id=profile.id,
        account_id=account.id,
    )

    refreshed = await Medication.filter(id=medication.id).first()
    assert refreshed is not None, "hard delete 되면 안 된다 — soft delete 정책이다"
    assert refreshed.deleted_at is not None, "처방전 그룹을 지웠는데 약이 살아 있다"


# ── ⭐ 조건부 보존 정책 — 이 파일의 핵심 ─────────────────────────────
# 흐름: 같은 가이드에 미시작 챌린지와 활성 챌린지를 하나씩 매달고 그룹을 삭제
#       -> 미시작만 사라지고 활성은 남아야 한다
# 두 갈래를 **한 테스트 안에서** 본다. 따로 두면 "전부 삭제" 구현이 한쪽만 통과시킨다.
async def test_cascade_removes_unstarted_challenges_but_keeps_started_ones(db: None) -> None:
    """Unstarted challenges are removed; started ones survive with guide detached."""
    account = await create_account()
    profile = await create_profile(account)
    group = await create_prescription_group(profile)
    medication = await create_medication(profile, group)
    guide = await create_lifestyle_guide(profile)

    unstarted = await create_challenge(profile, guide=guide, is_active=False, title="아직 시작 안 함")
    started = await create_challenge(
        profile,
        guide=guide,
        is_active=True,
        started_at=datetime.now(UTC),
        title="진행 중",
    )

    await MedicationService().delete_prescription_group_with_owner_check(
        ids=[medication.id],
        profile_id=profile.id,
        account_id=account.id,
    )

    unstarted_rows = await Challenge.filter(id=unstarted.id).values("deleted_at", "guide_id")
    started_rows = await Challenge.filter(id=started.id).values("deleted_at", "guide_id")

    # 사용자가 신경 쓰는 계약: 미시작 챌린지는 더 이상 조회되지 않는다.
    #
    # ⚠️ 실측된 메커니즘은 코드 주석과 다르다(2026-09-15 발견, 후속 큐 1-i).
    #    `_cascade_delete_guide` 는 미시작 챌린지에 soft_delete 를 걸지만, 바로 다음 줄에서
    #    가이드를 **hard delete** 하고 `challenges.guide_id` 가 ON DELETE CASCADE 라
    #    그 행이 **물리적으로 사라진다**. 즉 soft delete 는 한 줄 뒤에 덮인다.
    #    그래서 여기서는 `deleted_at is not None` 이 아니라 "행이 없다"로 단언한다.
    #    정책을 진짜 soft delete 로 바꾸기로 하면 이 단언도 함께 조여야 한다.
    assert unstarted_rows == [], "미시작 챌린지는 정리돼야 한다"

    assert len(started_rows) == 1, "사용자가 이미 시작한 챌린지가 지워졌다 — 진행분 보존 정책이 깨졌다"
    assert started_rows[0]["deleted_at"] is None, "보존된 챌린지가 soft delete 됐다"
    assert started_rows[0]["guide_id"] is None, "보존된 챌린지는 가이드와의 연결만 끊겨야 한다"


# ── 가이드 자체는 정리되는가 ──────────────────────────────────────────
async def test_cascade_removes_the_guide_itself(db: None) -> None:
    """The guide is removed once its prescription group is deleted."""
    account = await create_account()
    profile = await create_profile(account)
    group = await create_prescription_group(profile)
    medication = await create_medication(profile, group)
    guide = await create_lifestyle_guide(profile)

    await MedicationService().delete_prescription_group_with_owner_check(
        ids=[medication.id],
        profile_id=profile.id,
        account_id=account.id,
    )

    assert await LifestyleGuide.filter(id=guide.id).first() is None, "가이드가 정리되지 않았다"


# ── 남의 프로필 데이터까지 쓸어가지 않는가 ───────────────────────────
# 흐름: cascade 의 범위(scope)가 profile 로 제한되는지 확인
# 범위를 넓게 잡은 cascade 는 "동작은 하는데 남의 것도 지우는" 최악의 형태다.
async def test_cascade_does_not_touch_another_profile(db: None) -> None:
    """Cascade must stay inside the target profile."""
    account = await create_account()
    profile = await create_profile(account)
    other_profile = await create_profile(account, name="가족")

    group = await create_prescription_group(profile)
    medication = await create_medication(profile, group)

    other_guide = await create_lifestyle_guide(other_profile)
    other_challenge = await create_challenge(other_profile, guide=other_guide, is_active=False)

    await MedicationService().delete_prescription_group_with_owner_check(
        ids=[medication.id],
        profile_id=profile.id,
        account_id=account.id,
    )

    assert await LifestyleGuide.filter(id=other_guide.id).first() is not None, (
        "다른 프로필의 가이드까지 지워졌다 — cascade 범위가 너무 넓다"
    )
    survivors = await Challenge.filter(id=other_challenge.id).values("deleted_at")
    assert len(survivors) == 1, "다른 프로필의 챌린지가 사라졌다 — cascade 범위가 너무 넓다"
    assert survivors[0]["deleted_at"] is None, "다른 프로필의 챌린지가 삭제 표시됐다"

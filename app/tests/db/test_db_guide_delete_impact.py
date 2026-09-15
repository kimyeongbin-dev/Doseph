"""가이드 삭제가 무엇을 함께 지우는지 미리 알려주는 계약 (QA-29 S3).

가이드를 지우면 ``challenges.guide_id`` 의 ``ON DELETE CASCADE`` 로 **그 가이드에서
나온 챌린지가 진행 중·완료분까지 함께** 사라진다. 사용자는 "가이드를 지운다"고
생각하지만 실제로는 자기가 쌓은 완료 날짜와 streak 을 잃는다.

QA-01 에서 사용자는 *"진행분까지 지운다"* 를 결정했다. QA-29 는 그 정책을
뒤집지 않는다 — **누르기 전에 무엇을 잃는지 보여줄 뿐**이다.

왜 삭제 응답이 아니라 별도 조회인가:
    ``DELETE`` 는 204 다. 거기에 본문을 실으면 **이미 지운 뒤에** 무엇을 잃었는지
    알려주는 꼴이라 고지가 아니다.

왜 진짜 DB 인가:
    집계는 "몇 건인가"가 전부다. mock 은 자기가 넣어준 숫자를 돌려줄 뿐이고,
    guide_id 범위나 상태 분류가 틀려도 통과한다.
"""

from uuid import uuid4

from fastapi import HTTPException
import pytest

from app.services.lifestyle_guide_service import LifestyleGuideService
from app.tests.db.conftest import (
    create_account,
    create_challenge,
    create_lifestyle_guide,
    create_profile,
)

pytestmark = [pytest.mark.db, pytest.mark.asyncio(loop_scope="session")]

#: 이 파일이 만든 챌린지임을 한눈에 알 수 있는 고유 제목(헛된 초록 V-B 예방).
SENTINEL = "영향집계_QX7"


# ── 상태별 집계 ───────────────────────────────────────────────────────
# 흐름: 진행 중 2 · 완료 1 · 미시작 3 생성 -> 집계 조회 -> 상태별 수가 맞아야 한다
async def test_delete_impact_counts_challenges_by_state(db: None) -> None:
    """동반 삭제될 챌린지를 진행 중·완료·미시작으로 나눠 센다."""
    account = await create_account()
    profile = await create_profile(account)
    guide = await create_lifestyle_guide(profile)

    for _ in range(2):
        await create_challenge(profile, guide=guide, title=SENTINEL, is_active=True, challenge_status="IN_PROGRESS")
    await create_challenge(profile, guide=guide, title=SENTINEL, is_active=True, challenge_status="COMPLETED")
    for _ in range(3):
        await create_challenge(profile, guide=guide, title=SENTINEL, is_active=False)

    impact = await LifestyleGuideService().get_delete_impact_with_owner_check(guide.id, account.id)

    assert impact.in_progress_count == 2
    assert impact.completed_count == 1
    assert impact.not_started_count == 3
    assert impact.total_count == 6


# ── 남의 가이드 챌린지는 세지 않는다 ──────────────────────────────────
# 흐름: 가이드 2개에 각각 챌린지 -> 한쪽 집계 -> 자기 것만 세야 한다
async def test_delete_impact_counts_only_this_guide(db: None) -> None:
    """집계 범위는 **그 가이드**다 — 프로필 전체가 아니다.

    범위를 넓게 잡으면 숫자는 그럴듯한데 전부 틀린다(헛된 초록 V-B).
    """
    account = await create_account()
    profile = await create_profile(account)
    target_guide = await create_lifestyle_guide(profile)
    other_guide = await create_lifestyle_guide(profile)

    await create_challenge(profile, guide=target_guide, title=SENTINEL, is_active=True)
    await create_challenge(profile, guide=other_guide, title=SENTINEL, is_active=True)

    impact = await LifestyleGuideService().get_delete_impact_with_owner_check(target_guide.id, account.id)

    assert impact.total_count == 1, "다른 가이드의 챌린지까지 셌다"


# ── 사용자가 직접 만든 챌린지는 영향받지 않는다 ───────────────────────
# 흐름: guide=None 챌린지 생성 -> 집계 -> 포함되면 안 된다
async def test_delete_impact_excludes_user_created_challenges(db: None) -> None:
    """``guide_id`` 가 NULL 인 사용자 생성 챌린지는 가이드 삭제와 무관하다."""
    account = await create_account()
    profile = await create_profile(account)
    guide = await create_lifestyle_guide(profile)

    await create_challenge(profile, guide=None, title=SENTINEL, is_active=True)

    impact = await LifestyleGuideService().get_delete_impact_with_owner_check(guide.id, account.id)

    assert impact.total_count == 0, "사용자가 직접 만든 챌린지를 삭제 대상으로 셌다"


# ── 소유권 ────────────────────────────────────────────────────────────
# 흐름: 남의 계정으로 조회 -> 403
async def test_delete_impact_rejects_other_accounts(db: None) -> None:
    """남의 가이드 영향은 볼 수 없다 — 조회도 소유권 검증 대상이다."""
    owner = await create_account()
    profile = await create_profile(owner)
    guide = await create_lifestyle_guide(profile)
    intruder = await create_account()

    with pytest.raises(HTTPException) as exc_info:
        await LifestyleGuideService().get_delete_impact_with_owner_check(guide.id, intruder.id)

    assert exc_info.value.status_code in {403, 404}


# ── 없는 가이드 ───────────────────────────────────────────────────────
# 흐름: 존재하지 않는 id -> 404
async def test_delete_impact_missing_guide_is_404(db: None) -> None:
    """존재하지 않는 가이드는 404 다."""
    account = await create_account()

    with pytest.raises(HTTPException) as exc_info:
        await LifestyleGuideService().get_delete_impact_with_owner_check(uuid4(), account.id)

    assert exc_info.value.status_code == 404

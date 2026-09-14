"""Prove that one account cannot reach another account's rows.

**이 파일이 이 층에서 가장 값비싼 테스트다.** 나머지는 기능이 깨지면 화면이
이상해지지만, 여기가 깨지면 **남의 건강 데이터가 조용히 노출된다.** 증상이 없다.

``app/CLAUDE.md`` 는 "소유권 검증 누락 여부"를 코드리뷰 필수로 못 박고 있었지만
검사 수단은 사람 눈뿐이었다. 소유권은 **쿼리를 실제로 돌려야만** 확인된다 —
``_with_owner_check`` 라는 이름이 붙어 있다고 그 안이 실제로 거른다는 보장은 없다.

각 테스트는 **두 계정을 만들고, B 가 A 의 것을 집으려 시도한다.**
기대는 "빈 결과"가 아니라 **명시적 거부(403/404)** 다.
"""

from uuid import uuid4

from fastapi import HTTPException
import pytest

from app.services.challenge_service import ChallengeService
from app.services.chat_session_service import ChatSessionService
from app.tests.db.conftest import (
    create_account,
    create_challenge,
    create_chat_session,
    create_profile,
)

pytestmark = [pytest.mark.db, pytest.mark.asyncio(loop_scope="session")]


# ── 남의 챌린지 단건 조회 ─────────────────────────────────────────────
# 흐름: A 계정이 챌린지 생성 -> B 계정이 그 id 로 조회 -> 403
async def test_other_account_cannot_read_challenge(db: None) -> None:
    """Reading another account's challenge must be refused."""
    owner = await create_account()
    owner_profile = await create_profile(owner)
    challenge = await create_challenge(owner_profile, title="주인의 챌린지")

    intruder = await create_account()

    with pytest.raises(HTTPException) as raised:
        await ChallengeService().get_challenge_with_owner_check(challenge.id, intruder.id)

    assert raised.value.status_code == 403, "남의 챌린지 조회가 거부되지 않았다 — 소유권 검증이 뚫렸다"


# ── 주인은 자기 것을 볼 수 있어야 한다 ────────────────────────────────
# 흐름: 거부만 단언하면 "전부 거부"로 구현해도 통과한다 -> 허용 경로도 함께 잠근다
async def test_owner_can_read_own_challenge(db: None) -> None:
    """The owning account must still be able to read its own challenge."""
    owner = await create_account()
    owner_profile = await create_profile(owner)
    challenge = await create_challenge(owner_profile, title="주인의 챌린지")

    found = await ChallengeService().get_challenge_with_owner_check(challenge.id, owner.id)

    assert found.id == challenge.id, "주인이 자기 챌린지를 못 본다 — 검증이 과하게 막고 있다"


# ── 남의 프로필로 목록 조회 ───────────────────────────────────────────
# 흐름: B 가 A 의 profile_id 를 알아내 목록을 요청 -> 403
# 목록 경로는 단건과 다른 코드를 타므로 따로 잠근다.
async def test_other_account_cannot_list_challenges_of_foreign_profile(db: None) -> None:
    """Listing challenges of another account's profile must be refused."""
    owner = await create_account()
    owner_profile = await create_profile(owner)
    await create_challenge(owner_profile)

    intruder = await create_account()

    with pytest.raises(HTTPException) as raised:
        await ChallengeService().get_challenges_by_profile_with_owner_check(owner_profile.id, intruder.id)

    assert raised.value.status_code == 403, "남의 프로필 챌린지 목록이 노출됐다"


# ── 남의 챌린지 삭제 ──────────────────────────────────────────────────
# 흐름: 읽기만 막고 쓰기를 안 막는 경우가 실제로 흔하다 -> 변경 경로도 잠근다
async def test_other_account_cannot_delete_challenge(db: None) -> None:
    """Deleting another account's challenge must be refused."""
    owner = await create_account()
    owner_profile = await create_profile(owner)
    challenge = await create_challenge(owner_profile)

    intruder = await create_account()

    with pytest.raises(HTTPException) as raised:
        await ChallengeService().delete_challenge_with_owner_check(challenge.id, intruder.id)

    assert raised.value.status_code == 403, "남의 챌린지를 삭제할 수 있다 — 쓰기 경로가 뚫렸다"


# ── 남의 대화 세션 ────────────────────────────────────────────────────
# 흐름: 다른 도메인도 같은 규칙을 지키는지 (도메인마다 따로 구현돼 있다)
async def test_other_account_cannot_read_chat_session(db: None) -> None:
    """Reading another account's chat session must be refused."""
    owner = await create_account()
    owner_profile = await create_profile(owner)
    session = await create_chat_session(owner, owner_profile)

    intruder = await create_account()

    with pytest.raises(HTTPException) as raised:
        await ChatSessionService().get_session_with_owner_check(session.id, intruder.id)

    assert raised.value.status_code == 403, "남의 대화 세션이 노출됐다"


# ── 존재하지 않는 id ──────────────────────────────────────────────────
# 흐름: 없는 id 는 404 여야 한다. 403 과 404 가 뒤섞이면 존재 여부가 새어나간다
#       (남의 것을 403, 없는 것을 404 로 답하면 "그 id 가 존재한다"는 정보가 노출된다)
async def test_unknown_challenge_id_is_not_found(db: None) -> None:
    """An unknown challenge id must raise 404, not leak existence."""
    account = await create_account()

    with pytest.raises(HTTPException) as raised:
        await ChallengeService().get_challenge_with_owner_check(uuid4(), account.id)

    assert raised.value.status_code == 404

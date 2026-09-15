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

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

from fastapi import HTTPException
import pytest
from tortoise import connections
from tortoise.models import Model

from app.models.accounts import Account
from app.models.challenge import Challenge
from app.models.chat_sessions import ChatSession
from app.models.lifestyle_guide import LifestyleGuide
from app.models.medication import Medication
from app.models.messages import ChatMessage, SenderType
from app.models.prescription_group import PrescriptionGroup
from app.models.profiles import Profile, RelationType
from app.models.refresh_tokens import RefreshToken
from app.services.chat_session_service import ChatSessionService
from app.services.medication_service import MedicationService
from app.services.oauth import OAuthService
from app.services.profile_service import ProfileService
from app.tests.db.conftest import (
    create_account,
    create_challenge,
    create_chat_session,
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

    # QA-01: soft delete 폐지 — "삭제 표시"가 아니라 **행이 없는가**를 본다.
    assert await Medication.filter(id=medication.id).count() == 0, "처방전 그룹을 지웠는데 약 행이 남아 있다"


# ── ⭐ 가이드 삭제 -> 그 가이드의 챌린지 전부 삭제 ──────────────────────────
# 흐름: 같은 가이드에 미시작/활성 챌린지를 하나씩 매달고 그룹을 삭제 -> 둘 다 사라진다
#
# ⚠️ 2026-09-15 정책 변경(QA-01): 이전에는 **활성·완료 챌린지를 guide_id=None 으로
#    분리 보존**했다(사용자 진행분 유지). 사용자 결정으로 **진행분까지 삭제**하는 것으로
#    바꿨다 — 삭제 의미론을 hard delete 로 통일하는 흐름의 일부다.
#    되돌릴 수 없는 방향이므로, 단계적 삭제(유예기간)를 도입할 때 이 지점을 가장 먼저 본다.
#
# 구현은 FK 에 맡긴다: `challenges.guide_id` 가 ON DELETE CASCADE 라 가이드를 지우면
# 그 가이드에서 나온 챌린지는 DB 가 함께 지운다. 손으로 도는 루프가 필요 없다.
# (사용자가 직접 만든 챌린지는 guide_id 가 NULL 이라 영향받지 않는다)
async def test_deleting_guide_removes_all_its_challenges(db: None) -> None:
    """Every challenge of a deleted guide is removed — started ones included."""
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

    assert await Challenge.filter(id=unstarted.id).count() == 0, "미시작 챌린지가 남아 있다"
    assert await Challenge.filter(id=started.id).count() == 0, (
        "진행 중이던 챌린지가 남아 있다 — 진행분까지 삭제하는 정책이다(QA-01)"
    )


# ── 사용자가 직접 만든 챌린지는 영향받지 않는가 ─────────────────────────────
# 흐름: guide_id 가 NULL 인 챌린지는 가이드 삭제와 무관해야 한다
# FK CASCADE 에 맡긴 뒤 "너무 많이 지우지 않는가"를 확인하는 짝 테스트다.
async def test_deleting_guide_does_not_touch_user_created_challenges(db: None) -> None:
    """A challenge with no source guide must survive guide deletion."""
    account = await create_account()
    profile = await create_profile(account)
    group = await create_prescription_group(profile)
    medication = await create_medication(profile, group)
    await create_lifestyle_guide(profile)

    standalone = await create_challenge(profile, guide=None, title="직접 만든 챌린지")

    await MedicationService().delete_prescription_group_with_owner_check(
        ids=[medication.id],
        profile_id=profile.id,
        account_id=account.id,
    )

    assert await Challenge.filter(id=standalone.id).count() == 1, (
        "가이드에서 나오지 않은 챌린지까지 지워졌다 — cascade 범위가 너무 넓다"
    )


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


# ── ⭐ 프로필 삭제 -> 자식 8종 전부 (FK CASCADE 에 위임) ────────────────────
# 흐름: 가족 프로필에 자식을 8종 다 매달고 삭제 -> 프로필 행과 자식 전부가 사라진다
#
# ⚠️ 왜 8종을 **전수** 확인하나: QA-01 S4 에서 손수 돌던 cascade 호출 8개를 지우고
#    FK 에 맡겼다. 수동 호출을 지우는 만큼 **검증 범위를 넓혀야** 한다 —
#    "하나라도 FK 가 안 닿으면 고아 행이 남는다"가 이 변경의 유일한 위험이다.
#    (실측 2026-09-15: profiles 를 참조하는 FK 8개가 전부 ON DELETE CASCADE,
#     messages 는 chat_sessions 를 통해 연쇄)
#
# 팩토리가 없는 3종(intake_log · daily_symptom_log · ocr_draft)은 raw SQL 로 최소 행만 만든다.
async def test_deleting_profile_removes_every_child_row(db: None) -> None:
    """Deleting a profile must remove the row and every child row."""
    account = await create_account()
    await create_profile(account)  # SELF — 삭제 대상이 아님
    family = await create_profile(account, relation_type=RelationType.MOTHER, name="가족")

    group = await create_prescription_group(family)
    medication = await create_medication(family, group)
    challenge = await create_challenge(family)
    session = await create_chat_session(account, family)
    message = await ChatMessage.create(session=session, sender_type=SenderType.USER, content="안녕")
    guide = await create_lifestyle_guide(family)

    connection = connections.get("default")
    await connection.execute_query(
        "insert into intake_logs (id, scheduled_date, scheduled_time, medication_id, profile_id) "
        "values (gen_random_uuid(), '2026-09-01', '08:00+00', $1, $2)",
        [medication.id, family.id],
    )
    await connection.execute_query(
        "insert into daily_symptom_logs (id, log_date, symptoms, profile_id) "
        "values (gen_random_uuid(), '2026-09-01', '[]'::jsonb, $1)",
        [family.id],
    )
    await connection.execute_query(
        "insert into ocr_drafts (id, image_hash, profile_id) values (gen_random_uuid(), 'qa01-hash', $1)",
        [family.id],
    )

    await ProfileService().delete_profile_with_owner_check(family.id, account.id)

    assert await Profile.filter(id=family.id).count() == 0, "프로필 행이 남아 있다"
    assert await PrescriptionGroup.filter(id=group.id).count() == 0, "처방전 그룹이 남아 있다"
    assert await Medication.filter(id=medication.id).count() == 0, "약이 남아 있다"
    assert await Challenge.filter(id=challenge.id).count() == 0, "챌린지가 남아 있다"
    assert await ChatSession.filter(id=session.id).count() == 0, "세션이 남아 있다"
    assert await ChatMessage.filter(id=message.id).count() == 0, "메시지가 남아 있다"
    assert await LifestyleGuide.filter(id=guide.id).count() == 0, "가이드가 남아 있다"

    # 팩토리 없는 3종 — profile_id 로 직접 센다.
    # 테이블명을 f-string 으로 끼워넣지 않는다(정적 분석이 SQL 주입으로 본다).
    orphan_counts = {
        "intake_logs": (await _count_by_profile(connection, "intake_logs", family.id)),
        "daily_symptom_logs": (await _count_by_profile(connection, "daily_symptom_logs", family.id)),
        "ocr_drafts": (await _count_by_profile(connection, "ocr_drafts", family.id)),
    }
    assert orphan_counts == {"intake_logs": 0, "daily_symptom_logs": 0, "ocr_drafts": 0}, (
        f"FK 가 닿지 않아 고아 행이 남았다: {orphan_counts}"
    )


# ── SELF 프로필은 일반 삭제로 지워지지 않는다 ────────────────────────
# 흐름: SELF 는 계정과 묶여 있어 탈퇴 흐름으로만 제거돼야 한다
async def test_self_profile_cannot_be_deleted_directly(db: None) -> None:
    """The SELF profile must be refused by the normal delete path."""
    account = await create_account()
    self_profile = await create_profile(account)

    with pytest.raises(HTTPException) as raised:
        await ProfileService().delete_profile_with_owner_check(self_profile.id, account.id)

    assert raised.value.status_code == 403


# ── 세션 삭제 -> 메시지 ───────────────────────────────────────────────
async def test_deleting_chat_session_cascades_to_messages(db: None) -> None:
    """Deleting a chat session must soft-delete its messages."""
    account = await create_account()
    profile = await create_profile(account)
    session = await create_chat_session(account, profile)
    message = await ChatMessage.create(session=session, sender_type=SenderType.USER, content="안녕")

    await ChatSessionService().delete_session_with_owner_check(session.id, account.id)

    # 메시지는 FK(messages.session_id ON DELETE CASCADE)가 지운다 — 손으로 돌지 않는다.
    assert await ChatMessage.filter(id=message.id).count() == 0, "세션을 지웠는데 메시지 행이 남아 있다"


# ── 계정 탈퇴 -> 전부 ─────────────────────────────────────────────────
# 흐름: refresh token hard delete + 모든 프로필(SELF 포함) cascade + 계정 비활성화
# 탈퇴는 되돌릴 수 없는 경로라 "무엇이 남는가"를 행으로 확인하는 값이 가장 크다.
async def test_account_withdrawal_cascades_everything(db: None) -> None:
    """Account withdrawal must revoke tokens, cascade profiles and deactivate."""
    account = await create_account()
    self_profile = await create_profile(account)
    group = await create_prescription_group(self_profile)
    medication = await create_medication(self_profile, group)
    await RefreshToken.create(
        account=account,
        token_hash=uuid4().hex,
        expires_at=datetime.now(UTC) + timedelta(days=7),
        is_revoked=False,
    )
    # 계정 직속 세션 — 프로필 cascade 가 아니라 탈퇴 흐름이 따로 처리하는 경로
    session = await create_chat_session(account, self_profile)
    message = await ChatMessage.create(session=session, sender_type=SenderType.USER, content="탈퇴 전 대화")

    await OAuthService().delete_account(account)

    # QA-02 해소(2026-09-15): 전에는 is_revoked=True 로 표시만 해서 탈퇴 계정의
    # token_hash 행이 남았다(주석은 "hard-delete"라 적혀 있었다 — 잠금-불일치).
    # 이제 **행 자체를 지운다** — 탈퇴는 폐기가 아니라 erasure 이고, 재사용 가능한
    # 비밀을 남기지 않는 것이 데이터 최소화의 요구다.
    assert await RefreshToken.filter(account_id=account.id).count() == 0, (
        "탈퇴했는데 refresh token 행이 남아 있다 — token_hash 가 DB 에 잔존한다"
    )
    assert await Profile.filter(id=self_profile.id).count() == 0, "SELF 프로필 행이 남아 있다"
    assert await Medication.filter(id=medication.id).count() == 0, "약 행이 남아 있다"

    assert await ChatSession.filter(id=session.id).count() == 0, "계정 직속 세션 행이 남아 있다"
    assert await ChatMessage.filter(id=message.id).count() == 0, "세션 메시지 행이 남아 있다"

    account_rows = await Account.filter(id=account.id).values("is_active", "deleted_at")
    assert account_rows[0]["is_active"] is False, "탈퇴한 계정이 아직 활성이다"
    assert account_rows[0]["deleted_at"] is not None, "탈퇴한 계정에 deleted_at 이 없다"


async def _deleted_at_of(model: type[Model], row_id: Any) -> Any:
    """Read a row's ``deleted_at`` straight from the database.

    ORM 객체 속성 대신 행 값을 읽는다 — 디스크립터 타입 추론에 기대지 않기 위해.

    Args:
        model: Tortoise model class.
        row_id: Primary key of the row.

    Returns:
        The stored ``deleted_at`` value, or ``None`` when the row is gone.
    """
    rows = await model.filter(id=row_id).values("deleted_at")
    return rows[0]["deleted_at"] if rows else None


async def _count_by_profile(connection: Any, table: str, profile_id: Any) -> int:
    """profile_id 로 자식 테이블의 행 수를 센다.

    테이블명은 이 파일 안의 **고정 리터럴**만 들어온다(외부 입력 아님).

    Args:
        connection: Tortoise connection.
        table: 자식 테이블 이름.
        profile_id: 대상 프로필 UUID.

    Returns:
        남아 있는 행 수.
    """
    queries = {
        "intake_logs": "select count(*) as n from intake_logs where profile_id = $1",
        "daily_symptom_logs": "select count(*) as n from daily_symptom_logs where profile_id = $1",
        "ocr_drafts": "select count(*) as n from ocr_drafts where profile_id = $1",
    }
    _, rows = await connection.execute_query(queries[table], [profile_id])
    return int(rows[0]["n"])

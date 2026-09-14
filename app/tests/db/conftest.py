"""DB backend test layer - shared fixtures.

This package holds the only tests that talk to a real PostgreSQL server.
Everything else under ``app/tests`` runs without a database.

한계 (정직하게 남긴다):
    이 층은 **로컬/CI 의 Postgres** 를 검증한다. prod(Neon) 는 별도의 관리형
    인스턴스이므로 여기서 초록이라고 prod 가 같다는 보장은 없다. 그래서
    이미지 태그를 prod 와 같은 값으로 고정하고, ``test_db_version_pin`` 이
    그 고정이 풀리면 빨개지도록 잠근다. prod 쪽 버전이 올라간 것을 감지하는
    일은 이 층의 범위 밖이다(C12-c).
"""

from collections.abc import AsyncGenerator
from datetime import date
from typing import Any
from uuid import uuid4

from aerich import Command
import asyncpg
import pytest_asyncio
from tortoise import Tortoise, connections
from tortoise.transactions import in_transaction

from app.db.databases import TORTOISE_ORM
from app.models.accounts import Account, AuthProvider
from app.models.challenge import Challenge
from app.models.chat_sessions import ChatSession
from app.models.lifestyle_guide import LifestyleGuide
from app.models.medication import Medication
from app.models.prescription_group import PrescriptionGroup
from app.models.profiles import Profile, RelationType

# 마이그레이션 위치는 pyproject 의 [tool.aerich] 와 같은 값이어야 한다.
MIGRATIONS_LOCATION = "./app/db/migrations"
MIGRATIONS_APP = "models"

_BASE_CREDENTIALS: dict[str, Any] = {
    key: value
    for key, value in TORTOISE_ORM["connections"]["default"]["credentials"].items()
    if key not in {"maxsize", "timeout"}
}
#: 테스트 DB 를 만들고 지우기 위해 붙는 "관리용" DB (= 개발용 DB).
ADMIN_DATABASE: str = _BASE_CREDENTIALS["database"]
#: 테스트 전용 DB. 개발용 DB 는 절대 건드리지 않는다.
TEST_DATABASE: str = f"{ADMIN_DATABASE}_test"

_MISSING_DB_HINT = (
    "\n"
    "이 테스트는 진짜 PostgreSQL 이 필요하다. 연결하지 못했다.\n"
    f"  host={_BASE_CREDENTIALS['host']} port={_BASE_CREDENTIALS['port']} "
    f"user={_BASE_CREDENTIALS['user']} db={ADMIN_DATABASE}\n"
    "  로컬이라면:  docker compose up -d   (그 뒤 docker compose ps 로 healthy 확인)\n"
    "\n"
    "⚠️ 이 경우를 skip 으로 넘기지 않는 것은 의도적이다. skip 은 '검증하지 않았다'를\n"
    "   초록으로 보이게 만든다. DB 가 없으면 이 층은 아무것도 지키지 못하므로 실패한다.\n"
)


# ── 테스트 DB 조립 도우미 ──────────────────────────────────────────────
# 흐름: 개발용 DB 자격증명 재사용 -> database 이름만 교체 -> Tortoise 설정 반환
def orm_config(database: str) -> dict[str, Any]:
    """Build a Tortoise config pointing at ``database``.

    Args:
        database: Target database name.

    Returns:
        Tortoise ORM configuration dictionary.
    """
    return {
        "connections": {
            "default": {
                "engine": "tortoise.backends.asyncpg",
                "credentials": {**_BASE_CREDENTIALS, "database": database},
            }
        },
        "apps": TORTOISE_ORM["apps"],
        "timezone": TORTOISE_ORM["timezone"],
    }


def connect_kwargs(database: str) -> dict[str, Any]:
    """Build raw asyncpg connect kwargs for ``database``.

    Tortoise 가 붙어 있지 않은 DB(비교용 임시 DB 등)를 들여다볼 때 쓴다.

    Args:
        database: Target database name.

    Returns:
        Keyword arguments for ``asyncpg.connect``.
    """
    return {**_BASE_CREDENTIALS, "database": database}


async def admin_execute(statement: str) -> None:
    """Run a statement on the admin database (CREATE/DROP DATABASE).

    Args:
        statement: SQL to execute. Must not run inside a transaction.

    Raises:
        RuntimeError: When the server is unreachable, with a setup hint.
    """
    try:
        connection = await asyncpg.connect(**connect_kwargs(ADMIN_DATABASE))
    except (OSError, asyncpg.PostgresError) as exc:
        raise RuntimeError(_MISSING_DB_HINT) from exc
    try:
        await connection.execute(statement)
    finally:
        await connection.close()


# ── 세션 픽스처: 마이그레이션으로 만든 테스트 DB ──────────────────────
# 흐름: 기존 테스트 DB 삭제 -> 새로 생성 -> aerich upgrade -> Tortoise.init
#       -> 테스트 전체 -> 연결 종료
# 스키마를 generate_schemas() 로 만들지 않는 것이 이 픽스처의 핵심이다.
# 모델에서 바로 만들면 마이그레이션 체인이 영원히 미검증으로 남고, 그게 prod 가
# 코드보다 24 마이그레이션 뒤처졌던 드리프트의 구조다. 마이그레이션으로 만들어야
# "빈 DB 에서 우리 마이그레이션이 실제로 돈다" 가 매 실행마다 증명된다.
@pytest_asyncio.fixture(scope="session")
async def migrated_database() -> AsyncGenerator[str]:
    """Create a test database from the migration chain.

    Yields:
        str: Name of the migrated test database.
    """
    await admin_execute(f'DROP DATABASE IF EXISTS "{TEST_DATABASE}"')
    await admin_execute(f'CREATE DATABASE "{TEST_DATABASE}"')

    config = orm_config(TEST_DATABASE)
    command = Command(tortoise_config=config, app=MIGRATIONS_APP, location=MIGRATIONS_LOCATION)
    await command.init()
    await command.upgrade(run_in_transaction=False)
    await command.aclose()

    await Tortoise.init(config=config)
    try:
        yield TEST_DATABASE
    finally:
        await connections.close_all()
    # 끝나고 DROP 하지 않는다 — 실패 원인을 psql 로 들여다볼 수 있어야 한다.
    # 다음 세션이 시작할 때 어차피 DROP 하므로 상태가 새지는 않는다.


# ── 테스트별 격리: 트랜잭션 롤백 ──────────────────────────────────────
# 흐름: 트랜잭션 진입 -> 테스트 본문 -> 예외로 롤백 -> 다음 테스트는 빈 상태
# 실측(2026-09-15): 서비스가 내부에서 여는 in_transaction() 은 savepoint 로 중첩되고,
# 바깥 롤백이 안쪽에서 커밋한 행까지 되돌린다. 그래서 서비스를 정문으로 호출해도
# 상태가 다음 테스트로 새지 않는다.
# ⚠️ 알려진 사각: DEFERRABLE INITIALLY DEFERRED 제약은 commit 시점에만 발동하는데
#    이 픽스처는 commit 을 하지 않는다. 현재 스키마에 그런 제약이 없음을
#    test_db_constraints 가 단언한다.
class _RollbackError(Exception):
    """트랜잭션을 되돌리기 위한 내부 신호. 테스트 실패를 뜻하지 않는다."""


@pytest_asyncio.fixture
async def db(migrated_database: str) -> AsyncGenerator[None]:
    """Wrap a test in a transaction and roll it back afterwards.

    Yields:
        None: The test body runs inside an open transaction.
    """
    try:
        async with in_transaction():
            yield
            # TRY301 억제 사유: Tortoise 의 트랜잭션 컨텍스트는 "예외로 빠져나감"
            # 외에 롤백을 지시할 방법을 주지 않는다. 이 raise 가 곧 롤백 명령이라
            # 내부 함수로 뺄 수 있는 성질이 아니다.
            raise _RollbackError  # noqa: TRY301
    except _RollbackError:
        pass


# ── 테스트 데이터 팩토리 ──────────────────────────────────────────────
# 흐름: 계정 -> 프로필 -> 처방전 그룹 -> 약 / 챌린지 / 세션
# 최소 필수 필드만 채운다. 테스트가 신경 쓰는 값만 인자로 받고 나머지는 기본값이라
# "이 테스트가 무엇을 보는가"가 호출부에서 바로 읽힌다.
# 고유값(provider_account_id 등)은 uuid 로 만든다 — 복합 유니크 제약에 걸리지 않도록.
async def create_account(**overrides: Any) -> Account:
    """Create an account row with sane defaults.

    Args:
        **overrides: Field values overriding the defaults.

    Returns:
        The persisted account.
    """
    defaults: dict[str, Any] = {
        "auth_provider": AuthProvider.KAKAO,
        "provider_account_id": f"test-{uuid4().hex[:16]}",
        "nickname": "테스트계정",
        "is_active": True,
    }
    return await Account.create(**(defaults | overrides))


async def create_profile(account: Account, **overrides: Any) -> Profile:
    """Create a profile owned by ``account``.

    Args:
        account: Owning account.
        **overrides: Field values overriding the defaults.

    Returns:
        The persisted profile.
    """
    defaults: dict[str, Any] = {
        "account": account,
        "relation_type": RelationType.SELF,
        "name": "본인",
    }
    return await Profile.create(**(defaults | overrides))


async def create_prescription_group(profile: Profile, **overrides: Any) -> PrescriptionGroup:
    """Create a prescription group for ``profile``.

    Args:
        profile: Owning profile.
        **overrides: Field values overriding the defaults.

    Returns:
        The persisted prescription group.
    """
    defaults: dict[str, Any] = {
        "profile": profile,
        "hospital_name": "테스트의원",
        "dispensed_date": date(2026, 9, 1),
    }
    return await PrescriptionGroup.create(**(defaults | overrides))


async def create_medication(
    profile: Profile,
    prescription_group: PrescriptionGroup | None = None,
    **overrides: Any,
) -> Medication:
    """Create a medication row for ``profile``.

    Args:
        profile: Owning profile.
        prescription_group: Owning prescription group, when any.
        **overrides: Field values overriding the defaults.

    Returns:
        The persisted medication.
    """
    defaults: dict[str, Any] = {
        "profile": profile,
        "prescription_group": prescription_group,
        "medicine_name": "테스트정500mg",
        "intake_times": ["08:00"],
        "total_intake_count": 7,
        "remaining_intake_count": 7,
        "start_date": date(2026, 9, 1),
        "is_active": True,
    }
    return await Medication.create(**(defaults | overrides))


async def create_challenge(profile: Profile, **overrides: Any) -> Challenge:
    """Create a challenge for ``profile``.

    Args:
        profile: Owning profile.
        **overrides: Field values overriding the defaults.

    Returns:
        The persisted challenge.
    """
    defaults: dict[str, Any] = {
        "profile": profile,
        "title": "물 8잔 마시기",
        "target_days": 7,
        "started_date": date(2026, 9, 1),
    }
    return await Challenge.create(**(defaults | overrides))


async def create_lifestyle_guide(profile: Profile, **overrides: Any) -> LifestyleGuide:
    """Create a lifestyle guide for ``profile``.

    Args:
        profile: Owning profile.
        **overrides: Field values overriding the defaults.

    Returns:
        The persisted lifestyle guide.
    """
    defaults: dict[str, Any] = {
        "profile": profile,
        "content": {},
        "medication_snapshot": [],
        "input_fingerprint": uuid4().hex,
    }
    return await LifestyleGuide.create(**(defaults | overrides))


async def create_chat_session(account: Account, profile: Profile, **overrides: Any) -> ChatSession:
    """Create a chat session for ``account``/``profile``.

    Args:
        account: Owning account.
        profile: Owning profile.
        **overrides: Field values overriding the defaults.

    Returns:
        The persisted chat session.
    """
    defaults: dict[str, Any] = {
        "account": account,
        "profile": profile,
        "title": "테스트 대화",
    }
    return await ChatSession.create(**(defaults | overrides))

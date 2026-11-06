"""ORM 의 시간 해석이 진짜 DB 에서 한국 시간을 유지하는지 잠근다.

tortoise-orm 1.x 는 ``use_tz`` 의 뜻이 바뀌었다. ``False`` 로 두면 조회 값이
시간대 없는 UTC 로 돌아오므로, 0.25 와 같은 한국 시간 aware 값을 받으려면
``True`` 여야 한다. 설정값 확인만으로는 이 동작을 보증하지 못해 DB 에서 잰다.
"""

from datetime import datetime, timedelta
import zoneinfo

import pytest

from app.models.accounts import Account
from app.tests.db.conftest import create_account

pytestmark = [pytest.mark.db, pytest.mark.asyncio(loop_scope="session")]

_KST = zoneinfo.ZoneInfo("Asia/Seoul")
_KST_OFFSET = timedelta(hours=9)


async def test_query_result_keeps_korea_offset(db: None) -> None:
  """A timestamp read back from the database must be Korea-time aware."""
  account = await create_account()

  fresh = await Account.get(id=account.id)

  assert fresh.created_at.utcoffset() == _KST_OFFSET


async def test_aware_value_keeps_its_instant(db: None) -> None:
  """An aware value must round-trip as the same instant."""
  instant = datetime(2026, 1, 2, 3, 4, 5, tzinfo=_KST)
  account = await create_account()
  await Account.filter(id=account.id).update(created_at=instant)

  fresh = await Account.get(id=account.id)

  assert fresh.created_at == instant
  assert fresh.created_at.utcoffset() == _KST_OFFSET


async def test_naive_filter_value_is_read_as_korea_time(db: None) -> None:
  """A naive filter value must compare as Korea time, not UTC."""
  account = await create_account()
  fresh = await Account.get(id=account.id)
  naive_kst = fresh.created_at.astimezone(_KST).replace(tzinfo=None)
  one_second = timedelta(seconds=1)

  before = Account.filter(id=account.id, created_at__gte=naive_kst - one_second)
  after = Account.filter(id=account.id, created_at__gte=naive_kst + one_second)

  assert await before.exists()
  assert not await after.exists()

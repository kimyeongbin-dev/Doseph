"""ProfileService 의 relation→gender 자동 default 동작 검증 (mock 기반).

Phase 2 의 핵심 — `_resolve_gender` 와 `_apply_gender_default_on_relation_change`
가 의도대로 동작하는지 schema/DB 무관하게 검증.
"""

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.dtos.profile import ProfileCreate, ProfileUpdate
from app.models.profiles import Gender, RelationType
from app.services.profile_service import ProfileService


class TestResolveGender:
  """_resolve_gender — relation_type 기반 default + 사용자 우선."""

  @pytest.mark.parametrize(
    ("relation", "expected"),
    [
      (RelationType.FATHER, Gender.MALE),
      (RelationType.MOTHER, Gender.FEMALE),
      (RelationType.SON, Gender.MALE),
      (RelationType.DAUGHTER, Gender.FEMALE),
      (RelationType.HUSBAND, Gender.MALE),
      (RelationType.WIFE, Gender.FEMALE),
    ],
  )
  def test_explicit_relation_returns_default_gender(self, relation, expected) -> None:
    """6 가지 명시적 가족 관계는 자동 매핑된 gender 반환."""
    result = ProfileService._resolve_gender(relation, None)
    assert result == expected

  @pytest.mark.parametrize("relation", [RelationType.SELF, RelationType.OTHER])
  def test_self_and_other_have_no_default(self, relation) -> None:
    """SELF / OTHER 는 사용자 입력에 의존 — None 반환."""
    result = ProfileService._resolve_gender(relation, None)
    assert result is None

  def test_user_specified_gender_wins(self) -> None:
    """relation 이 FATHER 인데 사용자가 FEMALE 명시 시 → FEMALE 우선 (특수 케이스 대응)."""
    result = ProfileService._resolve_gender(RelationType.FATHER, Gender.FEMALE)
    assert result == Gender.FEMALE


class TestApplyGenderDefaultOnRelationChange:
  """update_profile 에서 relation_type 변경 시 gender 도 default 자동 갱신."""

  def test_relation_change_sets_default_gender(self) -> None:
    update = {"relation_type": "MOTHER"}
    ProfileService._apply_gender_default_on_relation_change(update)
    assert update["gender"] == Gender.FEMALE

  def test_user_explicit_gender_preserved(self) -> None:
    """사용자가 gender 도 같이 보내면 그 값을 그대로 둠 (특수 케이스)."""
    update = {"relation_type": "FATHER", "gender": Gender.FEMALE}
    ProfileService._apply_gender_default_on_relation_change(update)
    assert update["gender"] == Gender.FEMALE

  def test_no_relation_change_skips(self) -> None:
    """relation_type 갱신 안 하면 gender 도 건드리지 않음 (이름만 수정 등)."""
    update = {"name": "새이름"}
    ProfileService._apply_gender_default_on_relation_change(update)
    assert "gender" not in update

  def test_self_relation_no_default(self) -> None:
    """SELF / OTHER 로 변경 시 gender 변경 없음 (사용자 입력에 의존)."""
    update = {"relation_type": "SELF"}
    ProfileService._apply_gender_default_on_relation_change(update)
    assert "gender" not in update

    update = {"relation_type": "OTHER"}
    ProfileService._apply_gender_default_on_relation_change(update)
    assert "gender" not in update


@pytest.mark.asyncio
class TestCreateProfileWithGenderDefault:
  """create_profile 의 통합 동작 — repository 호출 시 gender 자동 채움."""

  async def test_father_creates_with_male_default(self) -> None:
    account_id = uuid4()
    service = ProfileService()
    service.repository = MagicMock()
    service.repository.get_self_profile = AsyncMock(return_value=None)
    service.repository.create = AsyncMock()

    await service.create_profile(
      account_id,
      ProfileCreate(
        relation_type=RelationType.FATHER,
        name="아빠",
        health_survey=None,
      ),
    )

    kwargs = service.repository.create.await_args.kwargs
    assert kwargs["gender"] == Gender.MALE
    assert kwargs["relation_type"] == RelationType.FATHER

  async def test_other_no_gender_default(self) -> None:
    account_id = uuid4()
    service = ProfileService()
    service.repository = MagicMock()
    service.repository.get_self_profile = AsyncMock(return_value=None)
    service.repository.create = AsyncMock()

    await service.create_profile(
      account_id,
      ProfileCreate(
        relation_type=RelationType.OTHER,
        name="친구",
        health_survey=None,
      ),
    )

    kwargs = service.repository.create.await_args.kwargs
    assert kwargs["gender"] is None

  async def test_user_specified_gender_overrides(self) -> None:
    """SON 인데 사용자가 FEMALE 명시 시 FEMALE 우선."""
    account_id = uuid4()
    service = ProfileService()
    service.repository = MagicMock()
    service.repository.get_self_profile = AsyncMock(return_value=None)
    service.repository.create = AsyncMock()

    await service.create_profile(
      account_id,
      ProfileCreate(
        relation_type=RelationType.SON,
        name="자녀",
        gender=Gender.FEMALE,
        health_survey=None,
      ),
    )

    kwargs = service.repository.create.await_args.kwargs
    assert kwargs["gender"] == Gender.FEMALE


@pytest.mark.asyncio
class TestUpdateProfileGenderAutoSet:
  """update_profile 의 통합 동작 — relation_type 변경 시 gender 자동 갱신."""

  async def test_change_to_mother_sets_female(self) -> None:
    profile_id = uuid4()
    existing = MagicMock(id=profile_id, relation_type=RelationType.FATHER)
    service = ProfileService()
    service.repository = MagicMock()
    service.repository.get_by_id = AsyncMock(return_value=existing)
    service.repository.update = AsyncMock(return_value=existing)

    await service.update_profile(
      profile_id,
      ProfileUpdate(relation_type=RelationType.MOTHER),
    )

    # update_profile 내부에서 update_data 에 gender 가 추가되어 repository.update 에 전달됨
    call_args = service.repository.update.await_args
    assert call_args.kwargs.get("gender") == Gender.FEMALE
    assert call_args.kwargs.get("relation_type") == RelationType.MOTHER

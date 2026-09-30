"""OAuthService._ensure_self_profile 동작 검증.

회원가입 흐름에서 SELF 프로필이 자동 생성되는지 + idempotent 동작 검증.
이 helper 는 dev_login / kakao_callback 둘 다에서 호출되며, 누락 시
프론트 ProfileContext 가 빈 배열을 받아 메인 페이지가 깨진다 (운영 사고 사례).
"""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.services.oauth import OAuthService


@pytest.mark.asyncio
class TestEnsureSelfProfile:
  """SELF 프로필 자동 생성 helper unit test."""

  async def test_creates_self_profile_when_absent(self) -> None:
    """SELF 프로필이 없으면 새로 INSERT — 신규 가입 기본 흐름."""
    service = OAuthService()
    account = MagicMock(id=uuid4())

    with (
      patch("app.services.oauth.Profile") as mock_profile,
    ):
      mock_filter = MagicMock()
      mock_filter.first = AsyncMock(return_value=None)  # SELF 없음
      mock_profile.filter.return_value = mock_filter
      mock_profile.create = AsyncMock()

      await service._ensure_self_profile(account, nickname="홍길동")

      mock_profile.create.assert_awaited_once()
      kwargs = mock_profile.create.await_args.kwargs
      assert kwargs["account_id"] == account.id
      assert kwargs["name"] == "홍길동"

  async def test_no_op_when_self_exists(self) -> None:
    """SELF 가 이미 있으면 INSERT 호출 X — idempotent 보장."""
    service = OAuthService()
    account = MagicMock(id=uuid4())
    existing_self = MagicMock(id=uuid4())

    with patch("app.services.oauth.Profile") as mock_profile:
      mock_filter = MagicMock()
      mock_filter.first = AsyncMock(return_value=existing_self)
      mock_profile.filter.return_value = mock_filter
      mock_profile.create = AsyncMock()

      await service._ensure_self_profile(account, nickname="홍길동")

      mock_profile.create.assert_not_awaited()

  async def test_truncates_long_nickname_to_32(self) -> None:
    """name 컬럼 max_length=32 — 카카오 긴 닉네임은 잘라서 저장."""
    service = OAuthService()
    account = MagicMock(id=uuid4())
    long_nickname = "가" * 50  # 50 자

    with patch("app.services.oauth.Profile") as mock_profile:
      mock_filter = MagicMock()
      mock_filter.first = AsyncMock(return_value=None)
      mock_profile.filter.return_value = mock_filter
      mock_profile.create = AsyncMock()

      await service._ensure_self_profile(account, nickname=long_nickname)

      kwargs = mock_profile.create.await_args.kwargs
      assert len(kwargs["name"]) == 32

  async def test_falls_back_when_nickname_empty(self) -> None:
    """nickname 이 None / 빈 문자열이면 기본값 '사용자' 사용."""
    service = OAuthService()
    account = MagicMock(id=uuid4())

    with patch("app.services.oauth.Profile") as mock_profile:
      mock_filter = MagicMock()
      mock_filter.first = AsyncMock(return_value=None)
      mock_profile.filter.return_value = mock_filter
      mock_profile.create = AsyncMock()

      await service._ensure_self_profile(account, nickname="")

      kwargs = mock_profile.create.await_args.kwargs
      assert kwargs["name"] == "사용자"

  async def test_health_survey_passed_through_when_provided(self) -> None:
    """dev_login 처럼 health_survey 인자 주면 그대로 INSERT 에 포함."""
    service = OAuthService()
    account = MagicMock(id=uuid4())
    survey = {"age": 25, "gender": "MALE"}

    with patch("app.services.oauth.Profile") as mock_profile:
      mock_filter = MagicMock()
      mock_filter.first = AsyncMock(return_value=None)
      mock_profile.filter.return_value = mock_filter
      mock_profile.create = AsyncMock()

      await service._ensure_self_profile(account, nickname="홍길동", health_survey=survey)

      kwargs = mock_profile.create.await_args.kwargs
      assert kwargs["health_survey"] == survey

  async def test_health_survey_none_for_kakao_callback(self) -> None:
    """카카오 콜백 흐름에선 health_survey 미지정 → None 으로 INSERT."""
    service = OAuthService()
    account = MagicMock(id=uuid4())

    with patch("app.services.oauth.Profile") as mock_profile:
      mock_filter = MagicMock()
      mock_filter.first = AsyncMock(return_value=None)
      mock_profile.filter.return_value = mock_filter
      mock_profile.create = AsyncMock()

      await service._ensure_self_profile(account, nickname="홍길동")

      kwargs = mock_profile.create.await_args.kwargs
      assert kwargs["health_survey"] is None

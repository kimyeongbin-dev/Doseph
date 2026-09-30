"""Regression guard: the dev_test_login backdoor must not exist anywhere.

The instant-login backdoor (``code == "dev_test_login"``) bypassed the full
OAuth flow and was a security risk. It has been removed; these tests fail if
it is ever reintroduced in the service or the router.
"""

from pathlib import Path

from app.services.oauth import OAuthService

_APP_ROOT = Path(__file__).resolve().parent.parent


def test_oauth_service_has_no_dev_login_method() -> None:
  """OAuthService 에 dev_test_login 백도어 메서드가 없어야 함."""
  assert not hasattr(OAuthService, "dev_test_login")


def test_oauth_router_source_has_no_dev_login_bypass() -> None:
  """oauth_routers 소스에 dev_test_login 우회 분기가 남아있지 않아야 함."""
  source = (_APP_ROOT / "apis" / "v1" / "oauth_routers.py").read_text(encoding="utf-8")

  assert "dev_test_login" not in source

"""JWT token classes module.

This module provides JWT token classes for access and refresh tokens
with automatic expiration handling and token backend integration.
"""

from calendar import timegm
from datetime import datetime, timedelta
from typing import Any
from uuid import uuid4

from app.core import config
from app.utils.jwt.backends import TokenBackend
from app.utils.jwt.exceptions import ExpiredTokenError, TokenBackendError, TokenBackendExpiredError, TokenError
from app.utils.jwt.state import token_backend


class Token:
  """Base JWT token class.

  This class provides the foundation for JWT token handling including
  encoding, decoding, expiration management, and payload manipulation.

  Attributes:
      token_type: Type of token (must be set in subclasses).
      lifetime: Token lifetime duration (must be set in subclasses).
  """

  token_type: str | None = None
  lifetime: timedelta | None = None
  _token_backend: TokenBackend = token_backend

  def __init__(self, token: str | None = None, verify: bool = True) -> None:
    """Initialize token instance.

    Args:
        token: Existing token string to decode.
        verify: Whether to verify token signature.

    Raises:
        TokenError: If token_type or lifetime not set, or token is invalid.
        ExpiredTokenError: If token is expired.
    """
    if not self.token_type:
      raise TokenError("token_type must be set")
    if not self.lifetime:
      raise TokenError("lifetime must be set")

    self.token = token
    self.current_time = datetime.now(tz=config.TIMEZONE)
    self.payload: dict[str, Any] = {}

    if token is not None:
      try:
        self.payload = token_backend.decode(token, verify=verify)
      except TokenBackendExpiredError as err:
        raise ExpiredTokenError("Token is expired") from err
      except TokenBackendError as err:
        raise TokenError("Token is invalid") from err
    else:
      self.payload = {"type": self.token_type}
      self.set_exp(from_time=self.current_time, lifetime=self.lifetime)
      self.set_jti()

  def __repr__(self) -> str:
    """Return string representation of token payload."""
    return repr(self.payload)

  def __getitem__(self, key: str) -> Any:
    """Get payload item by key."""
    return self.payload[key]

  def __setitem__(self, key: str, value: Any) -> None:
    """Set payload item by key."""
    self.payload[key] = value

  def __delitem__(self, key: str) -> None:
    """Delete payload item by key."""
    del self.payload[key]

  def __contains__(self, key: str) -> bool:
    """Check if key exists in payload."""
    return key in self.payload

  def __str__(self) -> str:
    """Sign and return token as base64 encoded string.

    Returns:
        str: Encoded JWT token string.
    """
    return self._token_backend.encode(self.payload)

  def set_exp(self, from_time: datetime | None = None, lifetime: timedelta | None = None) -> None:
    """Set token expiration time.

    Args:
        from_time: Base time for expiration calculation.
        lifetime: Token lifetime duration.
    """
    if from_time is None:
      from_time = self.current_time

    if lifetime is None:
      lifetime = self.lifetime

    assert lifetime is not None

    dt = from_time + lifetime
    self.payload["exp"] = timegm(dt.timetuple())

  def set_jti(self) -> None:
    """Set JWT ID (unique identifier) for the token."""
    self.payload["jti"] = uuid4().hex


class AccessToken(Token):
  """Access token class for API authentication.

  Short-lived token used for API access authentication.
  """

  token_type = "access"
  lifetime = timedelta(minutes=config.ACCESS_TOKEN_EXPIRE_MINUTES)


class RefreshToken(Token):
  """Refresh token class for token renewal.

  Long-lived token used to generate new access tokens.
  """

  token_type = "refresh"
  lifetime = timedelta(minutes=config.REFRESH_TOKEN_EXPIRE_MINUTES)
  no_copy_claims = ("type", "exp", "jti")

  @property
  def access_token(self) -> AccessToken:
    """Generate new access token from refresh token.

    Returns:
        AccessToken: New access token with copied claims.
    """
    access = AccessToken()
    access.set_exp(from_time=self.current_time)

    no_copy = self.no_copy_claims
    for claim, value in self.payload.items():
      if claim in no_copy:
        continue
      access[claim] = value

    return access

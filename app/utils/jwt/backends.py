"""JWT token backend implementation.

This module provides JWT token encoding and decoding functionality
with support for various algorithms and security features.
"""

from collections.abc import Iterable
from datetime import timedelta
from functools import cached_property
from typing import Any

import jwt
from jwt import ExpiredSignatureError, InvalidAlgorithmError, PyJWTError, algorithms

from app.core import config
from app.utils.jwt.exceptions import TokenBackendError, TokenBackendExpiredError

ALLOWED_ALGORITHMS = {
  "HS256",
  "HS384",
  "HS512",
}


class TokenBackend:
  """JWT token backend for encoding and decoding tokens.

  This class provides secure JWT token operations with configurable
  algorithms, signing keys, and validation options.

  Attributes:
      algorithm: JWT signing algorithm.
      signing_key: Key used for signing tokens.
      verifying_key: Key used for verifying tokens.
      audience: Token audience for validation.
      issuer: Token issuer for validation.
      leeway: Time leeway for token validation.
  """

  def __init__(
    self,
    algorithm: str,
    signing_key: str = config.SECRET_KEY,
    audience: str | Iterable | None = None,
    issuer: str | None = None,
    leeway: float | timedelta | None = None,
  ) -> None:
    """Initialize token backend.

    Args:
        algorithm: JWT algorithm to use.
        signing_key: Secret key for signing tokens.
        audience: Token audience for validation.
        issuer: Token issuer for validation.
        leeway: Time leeway for token validation.
    """
    self._validate_algorithm(algorithm)
    self.algorithm = algorithm
    self.signing_key = signing_key
    self.verifying_key = signing_key
    self.audience = audience
    self.issuer = issuer
    self.leeway = leeway

  @cached_property
  def prepared_signing_key(self) -> Any:
    """Cached, library-ready signing key (parsed once on first access)."""
    return self._prepare_key(self.signing_key)

  @cached_property
  def prepared_verifying_key(self) -> Any:
    """Cached, library-ready verifying key (parsed once on first access)."""
    return self._prepare_key(self.verifying_key)

  def _prepare_key(self, key: str | None) -> Any:
    """Prepare signing/verifying key for JWT operations.

    Args:
        key: Raw key string.

    Returns:
        Any: Prepared key for JWT operations.
    """
    if key is None or not getattr(jwt.PyJWS, "get_algorithm_by_name", None):
      return key
    jws_alg = jwt.PyJWS().get_algorithm_by_name(self.algorithm)
    return jws_alg.prepare_key(key)

  def _validate_algorithm(self, algorithm: str) -> None:
    """Validate JWT algorithm.

    Args:
        algorithm: Algorithm to validate.

    Raises:
        TokenBackendError: If algorithm is not supported.
    """
    if algorithm not in ALLOWED_ALGORITHMS:
      raise TokenBackendError(f"Unrecognized algorithm type '{algorithm}'")

    if algorithm in algorithms.requires_cryptography and not algorithms.has_crypto:
      raise TokenBackendError(f"You must have cryptography installed to use {algorithm}.")

  def get_leeway(self) -> timedelta:
    """Get time leeway for token validation.

    Returns:
        timedelta: Time leeway for validation.

    Raises:
        TokenBackendError: If leeway type is invalid.
    """
    if self.leeway is None:
      return timedelta(seconds=0)
    if isinstance(self.leeway, (int, float)):
      return timedelta(seconds=self.leeway)
    if isinstance(self.leeway, timedelta):
      return self.leeway
    raise TokenBackendError(
      f"Unrecognized type '{type(self.leeway)}', 'leeway' must be of type int, float or timedelta."
    )

  def encode(self, payload: dict[str, Any]) -> str:
    """Encode payload into JWT token.

    Args:
        payload: Data to encode in token.

    Returns:
        str: Encoded JWT token.
    """
    jwt_payload = payload.copy()
    if self.audience is not None:
      jwt_payload["aud"] = self.audience
    if self.issuer is not None:
      jwt_payload["iss"] = self.issuer

    token = jwt.encode(
      jwt_payload,
      self.prepared_signing_key,
      algorithm=self.algorithm,
    )
    if isinstance(token, bytes):
      return token.decode("utf-8")
    return token

  def decode(self, token: str, verify: bool = True) -> dict[str, Any]:
    """Decode JWT token and return payload.

    Args:
        token: JWT token to decode.
        verify: Whether to verify token signature.

    Returns:
        dict[str, Any]: Decoded token payload.

    Raises:
        TokenBackendError: If token is invalid.
        TokenBackendExpiredError: If token is expired.
    """
    try:
      return jwt.decode(
        token,
        self.prepared_signing_key,
        algorithms=[self.algorithm],
        audience=self.audience,
        issuer=self.issuer,
        leeway=self.get_leeway(),
        options={
          "verify_aud": self.audience is not None,
          "verify_signature": verify,
        },
      )
    except InvalidAlgorithmError as ex:
      raise TokenBackendError("Invalid algorithm specified") from ex
    except ExpiredSignatureError as ex:
      raise TokenBackendExpiredError("Token is expired") from ex
    except PyJWTError as ex:
      raise TokenBackendError("Token is invalid") from ex

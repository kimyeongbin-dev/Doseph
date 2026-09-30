"""JWT token exceptions.

This module defines custom exceptions for JWT token operations
including backend errors and token validation failures.
"""


class TokenBackendError(Exception):
  """Base exception for token backend errors."""


class TokenBackendExpiredError(TokenBackendError):
  """Exception raised when token is expired."""


class TokenError(Exception):
  """Base exception for token-related errors."""


class ExpiredTokenError(TokenError):
  """Exception raised when token has expired."""

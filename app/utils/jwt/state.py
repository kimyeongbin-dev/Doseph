"""JWT token backend state.

This module provides the global token backend instance
used throughout the application for JWT operations.
"""

from app.core import config
from app.utils.jwt.backends import TokenBackend

token_backend = TokenBackend(
  algorithm=config.JWT_ALGORITHM,
  signing_key=config.SECRET_KEY,
  leeway=config.JWT_LEEWAY,
)

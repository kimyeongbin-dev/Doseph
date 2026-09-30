"""Security utility functions.

This module provides password hashing and verification utilities
using bcrypt for secure password management.
"""

from passlib.context import CryptContext

pwd_context = CryptContext(
  schemes=["bcrypt"],
  deprecated="auto",
)


def hash_password(password: str) -> str:
  """Hash password using bcrypt.

  Args:
      password: Plain text password to hash.

  Returns:
      str: Hashed password.
  """
  return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
  """Verify password against hash.

  Args:
      plain_password: Plain text password to verify.
      hashed_password: Hashed password to compare against.

  Returns:
      bool: True if password matches, False otherwise.
  """
  return pwd_context.verify(plain_password, hashed_password)

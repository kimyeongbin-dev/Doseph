"""Security validation types.

This module defines reusable security types for Pydantic models
to prevent common security vulnerabilities like XSS, SQL injection,
and path traversal attacks.

Usage: Use SafeString, CleanString, etc. as types instead of str.
"""

import re
from typing import Annotated

import bleach
from pydantic import AfterValidator, BeforeValidator

# Dangerous pattern list (SQL Injection, XSS, Template Injection, Path Traversal)
DANGEROUS_PATTERNS = [
  # XSS
  (r"<script", "script tag"),
  (r"javascript:", "javascript protocol"),
  (r"on\w+\s*=", "event handler"),
  (r"<iframe", "iframe tag"),
  # SQL Injection
  (r"'\s*OR\s+", "SQL OR clause"),
  (r'"\s*OR\s+', "SQL OR clause"),
  (r";\s*DROP\s+", "SQL DROP statement"),
  (r";\s*DELETE\s+", "SQL DELETE statement"),
  (r"UNION\s+SELECT", "SQL UNION statement"),
  (r"--\s*$", "SQL comment"),
  # Template Injection
  (r"\{\{", "template syntax"),
  (r"\$\{", "template syntax"),
  (r"#\{", "template syntax"),
  # Path Traversal
  (r"\.\.[/\\]", "path traversal"),
]


def check_dangerous_patterns(value: str) -> str:
  """Check for dangerous patterns and raise ValueError if found.

  Args:
      value: String value to check.

  Returns:
      str: Original value if safe.

  Raises:
      ValueError: If dangerous pattern is detected.
  """
  if not isinstance(value, str):
    return value

  for pattern, description in DANGEROUS_PATTERNS:
    if re.search(pattern, value, re.IGNORECASE):
      raise ValueError(f"Disallowed input detected: {description}")
  return value


def sanitize_html(value: str) -> str:
  """Completely remove HTML tags.

  Args:
      value: String value to sanitize.

  Returns:
      str: String with all HTML tags removed.
  """
  if not isinstance(value, str):
    return value
  return bleach.clean(value, tags=[], strip=True)


def sanitize_html_partial(value: str) -> str:
  """Allow only safe HTML tags (b, i, u, p, br, strong, em).

  Args:
      value: String value to sanitize.

  Returns:
      str: String with only safe HTML tags preserved.
  """
  if not isinstance(value, str):
    return value
  allowed_tags = ["b", "i", "u", "p", "br", "strong", "em"]
  return bleach.clean(value, tags=allowed_tags, strip=True)


def strip_whitespace(value: str) -> str:
  """Remove leading and trailing whitespace.

  Args:
      value: String value to strip.

  Returns:
      str: String with whitespace removed.
  """
  if not isinstance(value, str):
    return value
  return value.strip()


# Reusable type definitions
# Usage example: nickname: SafeString

# Block dangerous patterns (XSS, SQLi, etc.)
SafeString = Annotated[str, AfterValidator(check_dangerous_patterns)]

# Complete HTML removal + whitespace cleanup
CleanString = Annotated[
  str,
  BeforeValidator(strip_whitespace),
  AfterValidator(sanitize_html),
  AfterValidator(check_dangerous_patterns),
]

# Allow some HTML (for chat, etc.)
PartialHtmlString = Annotated[
  str,
  BeforeValidator(strip_whitespace),
  AfterValidator(sanitize_html_partial),
  AfterValidator(check_dangerous_patterns),
]

# Whitespace cleanup only (no dangerous pattern check, for trusted internal data)
TrimmedString = Annotated[str, BeforeValidator(strip_whitespace)]

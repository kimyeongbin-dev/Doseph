"""Tests for the Tortoise ORM configuration builder.

Focuses on the ``DB_SSL`` toggle that injects an asyncpg ``ssl`` credential
for managed Postgres providers (e.g. Neon) which require TLS connections.
"""

from typing import Any

from app.core.config import Config
from app.db.databases import build_tortoise_orm


def _credentials(cfg: Config) -> dict[str, Any]:
  """Extract the default connection credentials from a built ORM config."""
  orm = build_tortoise_orm(cfg)
  return orm["connections"]["default"]["credentials"]


def test_db_ssl_disabled_omits_ssl_credential() -> None:
  """DB_SSL=False (local/dev Docker postgres) must not add an ssl credential."""
  cfg = Config(DB_SSL=False)

  assert "ssl" not in _credentials(cfg)


def test_db_ssl_enabled_requires_tls() -> None:
  """DB_SSL=True (Neon) must add ssl='require' for a TLS connection."""
  cfg = Config(DB_SSL=True)

  assert _credentials(cfg)["ssl"] == "require"


def test_builder_preserves_core_credentials() -> None:
  """Host/user/database credentials must flow through unchanged."""
  cfg = Config(DB_HOST="db.example.com", DB_USER="tester", DB_NAME="Doseph")

  creds = _credentials(cfg)

  assert creds["host"] == "db.example.com"
  assert creds["user"] == "tester"
  assert creds["database"] == "Doseph"

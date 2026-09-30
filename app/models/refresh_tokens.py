"""Refresh token model module.

This module defines the RefreshToken model for secure token management
with RTR (Refresh Token Rotation) and Grace Period support.

REQ-USR-AUT-010: Token-based authentication security enhancement.
"""

from tortoise import fields, models


class RefreshToken(models.Model):
  """Refresh token management model.

  This model manages refresh tokens with enhanced security features:
  - Stores SHA-256 hash values only (not original tokens)
  - Immediate invalidation on logout (is_revoked = True)
  - Multi-device login support (multiple tokens per account)
  - RTR: Issues new token + invalidates old token on use
  - Grace Period: Handles concurrent requests (2-second validity after rotation)

  Attributes:
      id: Primary key for token record.
      account: Foreign key to Account model.
      token_hash: SHA-256 hash of refresh token.
      expires_at: Token expiration timestamp.
      is_revoked: Token revocation status (logout or RTR).
      rotated_at: Token rotation timestamp (for Grace Period calculation).
      replaced_by_id: ID of replacement token (for tracking).
      created_at: Token issuance timestamp.
  """

  id = fields.BigIntField(
    primary_key=True,
    description="Token record ID",
  )
  account: fields.ForeignKeyRelation["models.Model"] = fields.ForeignKeyField(
    "models.Account",
    related_name="refresh_tokens",
    on_delete=fields.CASCADE,
    description="Token owner account",
  )
  token_hash = fields.CharField(
    max_length=64,
    description="SHA-256 hash of refresh token",
    db_index=True,
  )
  expires_at = fields.DatetimeField(
    description="Token expiration timestamp",
  )
  is_revoked = fields.BooleanField(
    default=False,
    description="Token revocation status (logout or RTR)",
  )
  rotated_at = fields.DatetimeField(
    null=True,
    description="Token rotation timestamp (for Grace Period calculation)",
  )
  replaced_by_id = fields.BigIntField(
    null=True,
    description="ID of replacement token (for tracking)",
  )
  created_at = fields.DatetimeField(
    auto_now_add=True,
    description="Token issuance timestamp",
  )

  class Meta:
    table = "refresh_tokens"
    indexes = [
      ("account_id", "is_revoked"),
    ]

  def __str__(self) -> str:
    return f"RefreshToken(account_id={self.account_id}, revoked={self.is_revoked})"

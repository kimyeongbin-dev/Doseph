"""Account model module.

This module defines the Account model for storing user authentication information
from social login providers.
"""

from enum import StrEnum

from tortoise import fields, models


class AuthProvider(StrEnum):
    """Authentication provider enumeration."""

    KAKAO = "KAKAO"
    NAVER = "NAVER"


class Account(models.Model):
    """Account model for storing user authentication information.

    This model stores social login authentication information and has
    1:N relationships with profiles, chat_sessions, and refresh_tokens.

    Attributes:
        id: Primary key UUID.
        auth_provider: Authentication provider (KAKAO, NAVER).
        provider_account_id: Account ID from the provider.
        nickname: User's nickname.
        profile_image_url: URL of user's profile image.
        is_active: Whether the account is active.
        created_at: Account creation timestamp.
        updated_at: Last update timestamp.
    """

    id = fields.UUIDField(primary_key=True)
    auth_provider = fields.CharEnumField(enum_type=AuthProvider, max_length=16)
    provider_account_id = fields.CharField(max_length=128)
    nickname = fields.CharField(max_length=32)
    profile_image_url = fields.CharField(max_length=512, null=True)
    is_active = fields.BooleanField()
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    class Meta:
        table = "accounts"
        unique_together = (("auth_provider", "provider_account_id"),)

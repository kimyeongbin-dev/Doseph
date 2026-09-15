"""Create fake user script.

This script creates a test user account and profile for development purposes.
Used for testing OAuth login flow with mock data.
"""

import asyncio
import sys

# Windows 콘솔 기본 코드페이지(cp949)에서 한글 출력이 깨지거나 죽지 않도록 고정한다.
# 🔴 stdout 과 stderr 는 **서로를 보호하지 않는다** — 한쪽만 고정하면 다른 쪽이 크래시한다(대장 D36).
# 지금 이 파일은 비-ASCII 를 안 찍지만 둔다: 나중에 한글 한 줄을 넣는 순간 조용히 죽는 자리다.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from tortoise import Tortoise

from app.db.databases import TORTOISE_ORM
from app.models.accounts import Account, AuthProvider
from app.models.profiles import Profile, RelationType


async def create_test_account() -> tuple[Account, bool]:
    """Create or get test account for mock Kakao login.

    Returns:
        Tuple[Account, bool]: Account instance and whether it was created.
    """
    account, created = await Account.get_or_create(
        auth_provider=AuthProvider.KAKAO,
        provider_account_id="mock_user_1234",
        defaults={
            "nickname": "Test User",
            "is_active": True,
            "profile_image_url": "https://via.placeholder.com/150",
        },
    )
    return account, created


async def create_test_profile(account: Account) -> tuple[Profile, bool]:
    """Create or get test profile for the account.

    Args:
        account: Account instance to create profile for.

    Returns:
        Tuple[Profile, bool]: Profile instance and whether it was created.
    """
    profile, created = await Profile.get_or_create(
        account=account,
        relation_type=RelationType.SELF,
        defaults={
            "name": "Test User (Self)",
            "health_survey": {"age": 25, "gender": "MALE"},
        },
    )
    return profile, created


async def run() -> None:
    """Main execution function."""
    # Initialize database connection
    await Tortoise.init(config=TORTOISE_ORM)

    try:
        # Create test account
        account, account_created = await create_test_account()

        if account_created:
            print(f"New account created: {account.nickname}")
        else:
            print(f"Using existing account: {account.nickname}")

        # Create test profile
        profile, profile_created = await create_test_profile(account)

        if profile_created:
            print(f"New profile created: {profile.name}")
        else:
            print(f"Using existing profile: {profile.name}")

    finally:
        await Tortoise.close_connections()


async def main() -> None:
    """Main entry point with error handling."""
    try:
        await run()
    except Exception as e:
        print(f"Error occurred: {e}")


if __name__ == "__main__":
    asyncio.run(main())

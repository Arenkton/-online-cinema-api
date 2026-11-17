import hashlib
from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from sqlalchemy import func, select

from src.crud import create_user, get_user_by_email
from src.models import (
    ActivationToken,
    User,
    UserGroup,
    UserGroupEnum,
)
from src.schemas import UserCreate
from src.security import verify_password


@pytest_asyncio.fixture
async def default_group(db_session):
    group = UserGroup(name=UserGroupEnum.USER.value)

    db_session.add(group)
    await db_session.commit()
    await db_session.refresh(group)

    return group


@pytest.mark.asyncio
async def test_get_user_by_email_missing(db_session):
    user = await get_user_by_email(
        db_session,
        "missing@example.com"
    )

    assert user is None


@pytest.mark.asyncio
async def test_create_user(db_session, default_group):
    data = UserCreate(
        email="test@example.com",
        password="StrongPassword123!"
    )

    user, raw_token = await create_user(db_session, data)

    assert user.id is not None
    assert user.email == "test@example.com"
    assert user.is_active is False
    assert user.group_id == default_group.id

    assert user.hashed_password != data.password
    assert verify_password(
        data.password,
        user.hashed_password
    )

    assert isinstance(raw_token, str)
    assert len(raw_token) > 20


@pytest.mark.asyncio
async def test_get_user_by_email(db_session, default_group):
    data = UserCreate(
        email="found@example.com",
        password="StrongPassword123!"
    )

    created_user, _ = await create_user(db_session, data)

    found_user = await get_user_by_email(
        db_session,
        "found@example.com"
    )

    assert found_user is not None
    assert found_user.id == created_user.id
    assert found_user.email == created_user.email


@pytest.mark.asyncio
async def test_duplicate_email(db_session, default_group):
    first_user = UserCreate(
        email="duplicate@example.com",
        password="StrongPassword123!"
    )

    await create_user(db_session, first_user)

    second_user = UserCreate(
        email="DUPLICATE@example.com",
        password="AnotherPassword123!"
    )

    with pytest.raises(
        ValueError,
        match="Email already registered"
    ):
        await create_user(db_session, second_user)

    result = await db_session.execute(
        select(func.count()).select_from(User)
    )

    assert result.scalar_one() == 1


@pytest.mark.asyncio
async def test_user_email_normalization(
    db_session,
    default_group
):
    data = UserCreate(
        email="TEST@EXAMPLE.COM",
        password="StrongPassword123!"
    )

    user, _ = await create_user(db_session, data)

    assert user.email == "test@example.com"


@pytest.mark.asyncio
async def test_create_user_without_group(db_session):
    data = UserCreate(
        email="test@example.com",
        password="StrongPassword123!"
    )

    with pytest.raises(
        ValueError,
        match="Default user group not found"
    ):
        await create_user(db_session, data)

    result = await db_session.execute(select(User))

    assert result.scalars().all() == []


@pytest.mark.asyncio
async def test_activation_token_created(
    db_session,
    default_group
):
    data = UserCreate(
        email="activation@example.com",
        password="StrongPassword123!"
    )

    user, raw_token = await create_user(db_session, data)

    result = await db_session.execute(
        select(ActivationToken).where(
            ActivationToken.user_id == user.id
        )
    )

    saved_token = result.scalar_one_or_none()

    assert saved_token is not None

    expected_hash = hashlib.sha256(
        raw_token.encode("utf-8")
    ).hexdigest()

    assert saved_token.token == expected_hash
    assert saved_token.token != raw_token


@pytest.mark.asyncio
async def test_activation_token_expires_in_24_hours(
    db_session,
    default_group
):
    before = datetime.now(timezone.utc)

    data = UserCreate(
        email="expiration@example.com",
        password="StrongPassword123!"
    )

    user, _ = await create_user(db_session, data)

    result = await db_session.execute(
        select(ActivationToken).where(
            ActivationToken.user_id == user.id
        )
    )

    token = result.scalar_one()

    expires_at = token.expires_at

    # SQLite may return a naive UTC datetime.
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(
            tzinfo=timezone.utc
        )

    expected_expiration = before + timedelta(hours=24)

    assert abs(
        expires_at - expected_expiration
    ) < timedelta(minutes=1)


@pytest.mark.asyncio
async def test_two_users_have_different_tokens(
    db_session,
    default_group
):
    first = UserCreate(
        email="first@example.com",
        password="StrongPassword123!"
    )

    second = UserCreate(
        email="second@example.com",
        password="StrongPassword123!"
    )

    first_user, first_token = await create_user(
        db_session, first
    )

    second_user, second_token = await create_user(
        db_session, second
    )

    assert first_user.id != second_user.id
    assert first_token != second_token

    assert (
        first_user.hashed_password
        != second_user.hashed_password
    )

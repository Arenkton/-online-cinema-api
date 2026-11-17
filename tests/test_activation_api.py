from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from sqlalchemy import select

from src.crud import create_user
from src.models import (
    ActivationToken,
    User,
    UserGroup,
    UserGroupEnum,
)
from src.schemas import UserCreate


@pytest_asyncio.fixture
async def default_group(db_session):
    group = UserGroup(name=UserGroupEnum.USER.value)

    db_session.add(group)
    await db_session.commit()
    await db_session.refresh(group)

    return group


@pytest_asyncio.fixture
async def activation_data(db_session, default_group):
    user_data = UserCreate(
        email="activation@example.com",
        password="StrongPassword123!",
    )

    user, raw_token = await create_user(
        db_session,
        user_data,
    )

    return user.id, raw_token


@pytest.mark.asyncio
async def test_activate_user_success(
    api_client,
    db_session,
    activation_data,
):
    user_id, raw_token = activation_data

    response = await api_client.get(
        "/auth/activate",
        params={"token": raw_token},
    )

    assert response.status_code == 200
    assert response.json() == {
        "message": "Account activated successfully"
    }

    # Check that the user is active.
    user = await db_session.get(User, user_id)
    await db_session.refresh(user)

    assert user.is_active is True

    # Activation token must be deleted.
    result = await db_session.execute(
        select(ActivationToken).where(
            ActivationToken.user_id == user_id
        )
    )

    assert result.scalar_one_or_none() is None


@pytest.mark.asyncio
async def test_activate_invalid_token(
    api_client,
    db_session,
    activation_data,
):
    user_id, _ = activation_data

    response = await api_client.get(
        "/auth/activate",
        params={"token": "invalid-token"},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == (
        "Invalid or expired activation token"
    )

    user = await db_session.get(User, user_id)
    await db_session.refresh(user)

    assert user.is_active is False


@pytest.mark.asyncio
async def test_activate_expired_token(
    api_client,
    db_session,
    activation_data,
):
    user_id, raw_token = activation_data

    result = await db_session.execute(
        select(ActivationToken).where(
            ActivationToken.user_id == user_id
        )
    )

    activation_token = result.scalar_one()

    # Make the token expired.
    activation_token.expires_at = (
        datetime.now(timezone.utc)
        - timedelta(minutes=1)
    )

    await db_session.commit()

    response = await api_client.get(
        "/auth/activate",
        params={"token": raw_token},
    )

    assert response.status_code == 400

    user = await db_session.get(User, user_id)
    await db_session.refresh(user)

    assert user.is_active is False


@pytest.mark.asyncio
async def test_activation_token_cannot_be_reused(
    api_client,
    activation_data,
):
    _, raw_token = activation_data

    first_response = await api_client.get(
        "/auth/activate",
        params={"token": raw_token},
    )

    assert first_response.status_code == 200

    second_response = await api_client.get(
        "/auth/activate",
        params={"token": raw_token},
    )

    assert second_response.status_code == 400
    assert second_response.json()["detail"] == (
        "Invalid or expired activation token"
    )


@pytest.mark.asyncio
async def test_activate_without_token(api_client):
    response = await api_client.get(
        "/auth/activate"
    )

    assert response.status_code == 422

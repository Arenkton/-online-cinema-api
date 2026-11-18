import hashlib

import pytest
import pytest_asyncio
from sqlalchemy import select

from src.crud import create_user
from src.models import (
    RefreshToken,
    UserGroup,
    UserGroupEnum,
)
from src.schemas import UserCreate


@pytest.fixture(autouse=True)
def jwt_secret(monkeypatch):
    monkeypatch.setenv(
        "JWT_SECRET_KEY",
        "test-secret-key-for-jwt-unit-tests-123456789",
    )


@pytest_asyncio.fixture
async def default_group(db_session):
    group = UserGroup(name=UserGroupEnum.USER.value)

    db_session.add(group)
    await db_session.commit()

    return group


@pytest_asyncio.fixture
async def active_user(db_session, default_group):
    user, _ = await create_user(
        db_session,
        UserCreate(
            email="logout@example.com",
            password="StrongPassword123!",
        ),
    )

    user.is_active = True
    await db_session.commit()

    return user.id


@pytest_asyncio.fixture
async def login_tokens(api_client, active_user):
    response = await api_client.post(
        "/auth/login",
        json={
            "email": "logout@example.com",
            "password": "StrongPassword123!",
        },
    )

    assert response.status_code == 200
    return response.json()


@pytest.mark.asyncio
async def test_logout_success(
    api_client,
    db_session,
    active_user,
    login_tokens,
):
    refresh_token = login_tokens["refresh_token"]

    response = await api_client.post(
        "/auth/logout",
        json={"refresh_token": refresh_token},
    )

    assert response.status_code == 204
    assert response.content == b""

    token_hash = hashlib.sha256(
        refresh_token.encode("utf-8")
    ).hexdigest()

    result = await db_session.execute(
        select(RefreshToken).where(
            RefreshToken.token == token_hash
        )
    )

    assert result.scalar_one_or_none() is None


@pytest.mark.asyncio
async def test_logout_revokes_refresh_token(
    api_client,
    login_tokens,
):
    token = login_tokens["refresh_token"]

    logout_response = await api_client.post(
        "/auth/logout",
        json={"refresh_token": token},
    )

    assert logout_response.status_code == 204

    refresh_response = await api_client.post(
        "/auth/refresh",
        json={"refresh_token": token},
    )

    assert refresh_response.status_code == 401


@pytest.mark.asyncio
async def test_logout_token_cannot_be_reused(
    api_client,
    login_tokens,
):
    token = login_tokens["refresh_token"]

    first_response = await api_client.post(
        "/auth/logout",
        json={"refresh_token": token},
    )

    second_response = await api_client.post(
        "/auth/logout",
        json={"refresh_token": token},
    )

    assert first_response.status_code == 204
    assert second_response.status_code == 401


@pytest.mark.asyncio
async def test_logout_invalid_token(api_client):
    response = await api_client.post(
        "/auth/logout",
        json={"refresh_token": "invalid.jwt.token"},
    )

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_logout_rejects_access_token(
    api_client,
    login_tokens,
):
    response = await api_client.post(
        "/auth/logout",
        json={
            "refresh_token": login_tokens["access_token"]
        },
    )

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_logout_missing_token(api_client):
    response = await api_client.post(
        "/auth/logout",
        json={},
    )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_logout_only_current_session(
    api_client,
    active_user,
):
    credentials = {
        "email": "logout@example.com",
        "password": "StrongPassword123!",
    }

    first_login = await api_client.post(
        "/auth/login",
        json=credentials,
    )

    second_login = await api_client.post(
        "/auth/login",
        json=credentials,
    )

    assert first_login.status_code == 200
    assert second_login.status_code == 200

    first_token = first_login.json()["refresh_token"]
    second_token = second_login.json()["refresh_token"]

    assert first_token != second_token

    logout_response = await api_client.post(
        "/auth/logout",
        json={"refresh_token": first_token},
    )

    assert logout_response.status_code == 204

    # The first session is revoked.
    first_refresh = await api_client.post(
        "/auth/refresh",
        json={"refresh_token": first_token},
    )

    assert first_refresh.status_code == 401

    # The second session remains active.
    second_refresh = await api_client.post(
        "/auth/refresh",
        json={"refresh_token": second_token},
    )

    assert second_refresh.status_code == 200

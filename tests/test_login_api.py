import hashlib

import pytest
import pytest_asyncio
from sqlalchemy import select

from src.crud import create_user
from src.jwt_service import decode_jwt_token
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
    await db_session.refresh(group)

    return group


@pytest_asyncio.fixture
async def active_user(db_session, default_group):
    data = UserCreate(
        email="login@example.com",
        password="StrongPassword123!",
    )

    user, _ = await create_user(db_session, data)

    user.is_active = True
    await db_session.commit()

    return user.id


@pytest.mark.asyncio
async def test_login_success(
    api_client,
    db_session,
    active_user,
):
    response = await api_client.post(
        "/auth/login",
        json={
            "email": "login@example.com",
            "password": "StrongPassword123!",
        },
    )

    assert response.status_code == 200

    data = response.json()

    assert data["token_type"] == "bearer"
    assert isinstance(data["access_token"], str)
    assert isinstance(data["refresh_token"], str)

    access_payload = decode_jwt_token(
        data["access_token"],
        expected_type="access",
    )

    refresh_payload = decode_jwt_token(
        data["refresh_token"],
        expected_type="refresh",
    )

    assert access_payload["sub"] == str(active_user)
    assert refresh_payload["sub"] == str(active_user)

    assert access_payload["exp"] - access_payload["iat"] == 900
    assert refresh_payload["exp"] - refresh_payload["iat"] == 604800

    result = await db_session.execute(
        select(RefreshToken).where(
            RefreshToken.user_id == active_user
        )
    )

    saved_token = result.scalar_one()

    expected_hash = hashlib.sha256(
        data["refresh_token"].encode("utf-8")
    ).hexdigest()

    assert saved_token.token == expected_hash
    assert saved_token.token != data["refresh_token"]


@pytest.mark.asyncio
async def test_login_wrong_password(
    api_client,
    active_user,
):
    response = await api_client.post(
        "/auth/login",
        json={
            "email": "login@example.com",
            "password": "WrongPassword123!",
        },
    )

    assert response.status_code == 401
    assert response.json()["detail"] == (
        "Invalid email or password"
    )


@pytest.mark.asyncio
async def test_login_unknown_email(api_client):
    response = await api_client.post(
        "/auth/login",
        json={
            "email": "unknown@example.com",
            "password": "StrongPassword123!",
        },
    )

    assert response.status_code == 401
    assert response.json()["detail"] == (
        "Invalid email or password"
    )


@pytest.mark.asyncio
async def test_login_inactive_user(
    api_client,
    db_session,
    default_group,
):
    data = UserCreate(
        email="inactive@example.com",
        password="StrongPassword123!",
    )

    await create_user(db_session, data)

    response = await api_client.post(
        "/auth/login",
        json={
            "email": "inactive@example.com",
            "password": "StrongPassword123!",
        },
    )

    assert response.status_code == 403
    assert response.json()["detail"] == (
        "Account is not activated"
    )


@pytest.mark.asyncio
async def test_login_invalid_email(api_client):
    response = await api_client.post(
        "/auth/login",
        json={
            "email": "not-an-email",
            "password": "StrongPassword123!",
        },
    )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_login_missing_password(api_client):
    response = await api_client.post(
        "/auth/login",
        json={"email": "login@example.com"},
    )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_login_email_case_insensitive(
    api_client,
    active_user,
):
    response = await api_client.post(
        "/auth/login",
        json={
            "email": "LOGIN@EXAMPLE.COM",
            "password": "StrongPassword123!",
        },
    )

    assert response.status_code == 200


@pytest.mark.asyncio
async def test_failed_login_does_not_create_refresh_token(
    api_client,
    db_session,
    active_user,
):
    response = await api_client.post(
        "/auth/login",
        json={
            "email": "login@example.com",
            "password": "WrongPassword123!",
        },
    )

    assert response.status_code == 401

    result = await db_session.execute(
        select(RefreshToken).where(
            RefreshToken.user_id == active_user
        )
    )

    assert result.scalars().all() == []

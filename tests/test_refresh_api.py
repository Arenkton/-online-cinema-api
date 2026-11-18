import hashlib
from datetime import datetime, timedelta, timezone

import jwt
import pytest
import pytest_asyncio
from sqlalchemy import select

from src.crud import create_user
from src.jwt_service import (
    create_jwt_token,
    decode_jwt_token,
)
from src.models import (
    RefreshToken,
    User,
    UserGroup,
    UserGroupEnum,
)
from src.schemas import UserCreate


TEST_SECRET = "test-secret-key-for-jwt-unit-tests-123456789"


@pytest.fixture(autouse=True)
def jwt_secret(monkeypatch):
    monkeypatch.setenv("JWT_SECRET_KEY", TEST_SECRET)


@pytest_asyncio.fixture
async def default_group(db_session):
    group = UserGroup(name=UserGroupEnum.USER.value)

    db_session.add(group)
    await db_session.commit()

    return group


@pytest_asyncio.fixture
async def active_user(db_session, default_group):
    data = UserCreate(
        email="refresh@example.com",
        password="StrongPassword123!",
    )

    user, _ = await create_user(db_session, data)

    user.is_active = True
    await db_session.commit()

    return user.id


@pytest_asyncio.fixture
async def login_tokens(api_client, active_user):
    response = await api_client.post(
        "/auth/login",
        json={
            "email": "refresh@example.com",
            "password": "StrongPassword123!",
        },
    )

    assert response.status_code == 200

    return response.json()


@pytest.mark.asyncio
async def test_refresh_success(
    api_client,
    db_session,
    active_user,
    login_tokens,
):
    old_refresh = login_tokens["refresh_token"]

    response = await api_client.post(
        "/auth/refresh",
        json={"refresh_token": old_refresh},
    )

    assert response.status_code == 200

    data = response.json()

    assert data["token_type"] == "bearer"
    assert data["refresh_token"] != old_refresh

    access_payload = decode_jwt_token(
        data["access_token"], "access"
    )

    refresh_payload = decode_jwt_token(
        data["refresh_token"], "refresh"
    )

    assert access_payload["sub"] == str(active_user)
    assert refresh_payload["sub"] == str(active_user)

    old_hash = hashlib.sha256(
        old_refresh.encode()
    ).hexdigest()

    new_hash = hashlib.sha256(
        data["refresh_token"].encode()
    ).hexdigest()

    result = await db_session.execute(
        select(RefreshToken).where(
            RefreshToken.user_id == active_user
        )
    )

    stored_tokens = result.scalars().all()

    assert len(stored_tokens) == 1
    assert stored_tokens[0].token == new_hash
    assert stored_tokens[0].token != old_hash


@pytest.mark.asyncio
async def test_old_refresh_token_cannot_be_reused(
    api_client,
    login_tokens,
):
    old_token = login_tokens["refresh_token"]

    first_response = await api_client.post(
        "/auth/refresh",
        json={"refresh_token": old_token},
    )

    assert first_response.status_code == 200

    second_response = await api_client.post(
        "/auth/refresh",
        json={"refresh_token": old_token},
    )

    assert second_response.status_code == 401

    # The newly issued token must still work.
    new_token = first_response.json()["refresh_token"]

    third_response = await api_client.post(
        "/auth/refresh",
        json={"refresh_token": new_token},
    )

    assert third_response.status_code == 200


@pytest.mark.asyncio
async def test_access_token_cannot_be_refreshed(
    api_client,
    login_tokens,
):
    response = await api_client.post(
        "/auth/refresh",
        json={
            "refresh_token": login_tokens["access_token"]
        },
    )

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_invalid_refresh_token(api_client):
    response = await api_client.post(
        "/auth/refresh",
        json={"refresh_token": "invalid.jwt.token"},
    )

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_expired_refresh_token(
    api_client,
    active_user,
):
    now = datetime.now(timezone.utc)

    token = jwt.encode(
        {
            "sub": str(active_user),
            "type": "refresh",
            "jti": "expired-refresh",
            "iat": now - timedelta(days=8),
            "exp": now - timedelta(days=1),
        },
        TEST_SECRET,
        algorithm="HS256",
    )

    response = await api_client.post(
        "/auth/refresh",
        json={"refresh_token": token},
    )

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_unstored_refresh_token(
    api_client,
    active_user,
):
    # Valid JWT, but it was never saved in the database.
    token = create_jwt_token(
        active_user,
        "refresh",
    )

    response = await api_client.post(
        "/auth/refresh",
        json={"refresh_token": token},
    )

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_inactive_user_cannot_refresh(
    api_client,
    db_session,
    active_user,
    login_tokens,
):
    user = await db_session.get(User, active_user)

    user.is_active = False
    await db_session.commit()

    response = await api_client.post(
        "/auth/refresh",
        json={
            "refresh_token": login_tokens["refresh_token"]
        },
    )

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_refresh_missing_token(api_client):
    response = await api_client.post(
        "/auth/refresh",
        json={},
    )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_new_access_token_works(
    api_client,
    login_tokens,
):
    response = await api_client.post(
        "/auth/refresh",
        json={
            "refresh_token": login_tokens["refresh_token"]
        },
    )

    assert response.status_code == 200

    new_access = response.json()["access_token"]

    me_response = await api_client.get(
        "/auth/me",
        headers={
            "Authorization": f"Bearer {new_access}"
        },
    )

    assert me_response.status_code == 200
    assert me_response.json()["email"] == (
        "refresh@example.com"
    )

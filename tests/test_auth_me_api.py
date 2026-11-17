from datetime import datetime, timedelta, timezone

import jwt
import pytest
import pytest_asyncio

from src.crud import create_user
from src.jwt_service import create_jwt_token
from src.models import User, UserGroup, UserGroupEnum
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
    await db_session.refresh(group)

    return group


@pytest_asyncio.fixture
async def active_user(db_session, default_group):
    data = UserCreate(
        email="test@example.com",
        password="StrongPassword123!",
    )

    user, _ = await create_user(db_session, data)

    user.is_active = True
    await db_session.commit()

    return user.id


def auth_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_get_me_success(api_client, active_user):
    token = create_jwt_token(active_user, "access")

    response = await api_client.get(
        "/auth/me",
        headers=auth_headers(token),
    )

    assert response.status_code == 200

    data = response.json()

    assert data["id"] == active_user
    assert data["email"] == "test@example.com"
    assert data["is_active"] is True

    assert "password" not in data
    assert "hashed_password" not in data
    assert "refresh_tokens" not in data


@pytest.mark.asyncio
async def test_get_me_without_token(api_client):
    response = await api_client.get("/auth/me")

    assert response.status_code == 401
    assert response.json()["detail"] == (
        "Could not validate credentials"
    )

    assert response.headers["www-authenticate"] == "Bearer"


@pytest.mark.asyncio
async def test_get_me_invalid_token(api_client):
    response = await api_client.get(
        "/auth/me",
        headers=auth_headers("invalid.jwt.token"),
    )

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_get_me_wrong_auth_scheme(
    api_client,
    active_user,
):
    token = create_jwt_token(active_user, "access")

    response = await api_client.get(
        "/auth/me",
        headers={"Authorization": f"Basic {token}"},
    )

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_refresh_token_cannot_access_me(
    api_client,
    active_user,
):
    refresh_token = create_jwt_token(
        active_user,
        "refresh",
    )

    response = await api_client.get(
        "/auth/me",
        headers=auth_headers(refresh_token),
    )

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_expired_access_token(
    api_client,
    active_user,
):
    now = datetime.now(timezone.utc)

    payload = {
        "sub": str(active_user),
        "type": "access",
        "jti": "expired-access-token",
        "iat": now - timedelta(hours=2),
        "exp": now - timedelta(hours=1),
    }

    expired_token = jwt.encode(
        payload,
        TEST_SECRET,
        algorithm="HS256",
    )

    response = await api_client.get(
        "/auth/me",
        headers=auth_headers(expired_token),
    )

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_invalid_token_signature(
    api_client,
    active_user,
):
    token = jwt.encode(
        {
            "sub": str(active_user),
            "type": "access",
            "jti": "invalid-signature",
            "iat": datetime.now(timezone.utc),
            "exp": (
                datetime.now(timezone.utc)
                + timedelta(minutes=15)
            ),
        },
        "another-secret-key-with-enough-characters-123",
        algorithm="HS256",
    )

    response = await api_client.get(
        "/auth/me",
        headers=auth_headers(token),
    )

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_nonexistent_user(api_client):
    token = create_jwt_token(
        user_id=999999,
        token_type="access",
    )

    response = await api_client.get(
        "/auth/me",
        headers=auth_headers(token),
    )

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_inactive_user_cannot_access_me(
    api_client,
    db_session,
    active_user,
):
    user = await db_session.get(User, active_user)

    user.is_active = False
    await db_session.commit()

    token = create_jwt_token(active_user, "access")

    response = await api_client.get(
        "/auth/me",
        headers=auth_headers(token),
    )

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_invalid_user_id_in_token(api_client):
    now = datetime.now(timezone.utc)

    payload = {
        "sub": "not-an-integer",
        "type": "access",
        "jti": "invalid-user-id",
        "iat": now,
        "exp": now + timedelta(minutes=15),
    }

    token = jwt.encode(
        payload,
        TEST_SECRET,
        algorithm="HS256",
    )

    response = await api_client.get(
        "/auth/me",
        headers=auth_headers(token),
    )

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_missing_subject_in_token(api_client):
    now = datetime.now(timezone.utc)

    payload = {
        "type": "access",
        "jti": "missing-subject",
        "iat": now,
        "exp": now + timedelta(minutes=15),
    }

    token = jwt.encode(
        payload,
        TEST_SECRET,
        algorithm="HS256",
    )

    response = await api_client.get(
        "/auth/me",
        headers=auth_headers(token),
    )

    assert response.status_code == 401

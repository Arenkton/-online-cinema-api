import hashlib

import pytest
import pytest_asyncio

from sqlalchemy import select

from src.models import (
    User,
    UserGroup,
    UserGroupEnum,
    ActivationToken,
)
from src.security import verify_password


@pytest_asyncio.fixture
async def default_group(db_session):
    group = UserGroup(name=UserGroupEnum.USER.value)

    db_session.add(group)
    await db_session.commit()
    await db_session.refresh(group)

    return group


@pytest.fixture
def sent_emails(monkeypatch):
    emails = []

    def fake_send_activation_email(recipient, token):
        emails.append({
            "recipient": recipient,
            "token": token,
        })

    monkeypatch.setattr(
        "src.routers.auth.send_activation_email",
        fake_send_activation_email,
    )

    return emails


@pytest.mark.asyncio
async def test_register_user_success(
    api_client,
    db_session,
    default_group,
    sent_emails,
):
    response = await api_client.post(
        "/auth/register",
        json={
            "email": "test@example.com",
            "password": "StrongPassword123!",
        },
    )

    assert response.status_code == 201

    data = response.json()

    assert data["email"] == "test@example.com"
    assert data["is_active"] is False
    assert isinstance(data["id"], int)

    assert "password" not in data
    assert "hashed_password" not in data
    assert "token" not in data

    result = await db_session.execute(
        select(User).where(
            User.email == "test@example.com"
        )
    )

    user = result.scalar_one()

    assert user.group_id == default_group.id
    assert verify_password(
        "StrongPassword123!",
        user.hashed_password,
    )

    assert len(sent_emails) == 1
    assert sent_emails[0]["recipient"] == user.email

    raw_token = sent_emails[0]["token"]

    result = await db_session.execute(
        select(ActivationToken).where(
            ActivationToken.user_id == user.id
        )
    )

    saved_token = result.scalar_one()

    expected_hash = hashlib.sha256(
        raw_token.encode("utf-8")
    ).hexdigest()

    assert saved_token.token == expected_hash


@pytest.mark.asyncio
async def test_register_duplicate_email(
    api_client,
    default_group,
    sent_emails,
):
    payload = {
        "email": "duplicate@example.com",
        "password": "StrongPassword123!",
    }

    first_response = await api_client.post(
        "/auth/register",
        json=payload,
    )

    assert first_response.status_code == 201

    second_response = await api_client.post(
        "/auth/register",
        json={
            "email": "DUPLICATE@example.com",
            "password": "AnotherPassword123!",
        },
    )

    assert second_response.status_code == 409
    assert second_response.json()["detail"] == (
        "Email already registered"
    )

    assert len(sent_emails) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "payload",
    [
        {
            "email": "invalid-email",
            "password": "StrongPassword123!",
        },
        {
            "email": "test@example.com",
            "password": "Ab1!",
        },
        {
            "email": "test@example.com",
            "password": "lowercase123!",
        },
        {
            "email": "test@example.com",
            "password": "UPPERCASE123!",
        },
        {
            "email": "test@example.com",
            "password": "NoDigitsHere!",
        },
        {
            "email": "test@example.com",
            "password": "NoSpecial123",
        },
    ],
)
async def test_register_invalid_data(
    api_client,
    default_group,
    sent_emails,
    payload,
):
    response = await api_client.post(
        "/auth/register",
        json=payload,
    )

    assert response.status_code == 422
    assert sent_emails == []


@pytest.mark.asyncio
async def test_register_missing_password(
    api_client,
    default_group,
    sent_emails,
):
    response = await api_client.post(
        "/auth/register",
        json={
            "email": "test@example.com",
        },
    )

    assert response.status_code == 422
    assert sent_emails == []


@pytest.mark.asyncio
async def test_register_without_default_group(
    api_client,
    db_session,
    sent_emails,
):
    response = await api_client.post(
        "/auth/register",
        json={
            "email": "test@example.com",
            "password": "StrongPassword123!",
        },
    )

    assert response.status_code == 500
    assert response.json()["detail"] == (
        "Registration unavailable"
    )

    assert sent_emails == []

    result = await db_session.execute(select(User))

    assert result.scalars().all() == []

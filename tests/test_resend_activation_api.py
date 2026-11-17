import hashlib
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
async def inactive_user(db_session, default_group):
    user_data = UserCreate(
        email="test@example.com",
        password="StrongPassword123!",
    )

    user, raw_token = await create_user(
        db_session,
        user_data,
    )

    return user.id, raw_token


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


async def make_token_resendable(db_session, user_id):
    result = await db_session.execute(
        select(ActivationToken).where(
            ActivationToken.user_id == user_id
        )
    )

    activation = result.scalar_one()

    # Simulate that more than 5 minutes have passed.
    activation.expires_at = (
        datetime.now(timezone.utc)
        + timedelta(hours=23, minutes=54)
    )

    await db_session.commit()


@pytest.mark.asyncio
async def test_resend_activation_success(
    api_client,
    db_session,
    inactive_user,
    sent_emails,
):
    user_id, old_token = inactive_user

    await make_token_resendable(db_session, user_id)

    response = await api_client.post(
        "/auth/resend-activation",
        json={"email": "test@example.com"},
    )

    assert response.status_code == 202
    assert len(sent_emails) == 1

    new_token = sent_emails[0]["token"]

    assert sent_emails[0]["recipient"] == "test@example.com"
    assert new_token != old_token

    result = await db_session.execute(
        select(ActivationToken).where(
            ActivationToken.user_id == user_id
        )
    )

    saved_token = result.scalar_one()

    expected_hash = hashlib.sha256(
        new_token.encode("utf-8")
    ).hexdigest()

    assert saved_token.token == expected_hash


@pytest.mark.asyncio
async def test_resend_activation_cooldown(
    api_client,
    db_session,
    inactive_user,
    sent_emails,
):
    user_id, old_token = inactive_user

    response = await api_client.post(
        "/auth/resend-activation",
        json={"email": "test@example.com"},
    )

    assert response.status_code == 202
    assert sent_emails == []

    result = await db_session.execute(
        select(ActivationToken).where(
            ActivationToken.user_id == user_id
        )
    )

    saved_token = result.scalar_one()

    old_hash = hashlib.sha256(
        old_token.encode("utf-8")
    ).hexdigest()

    assert saved_token.token == old_hash


@pytest.mark.asyncio
async def test_resend_activation_unknown_email(
    api_client,
    sent_emails,
):
    response = await api_client.post(
        "/auth/resend-activation",
        json={"email": "unknown@example.com"},
    )

    assert response.status_code == 202
    assert sent_emails == []


@pytest.mark.asyncio
async def test_resend_activation_active_user(
    api_client,
    db_session,
    inactive_user,
    sent_emails,
):
    user_id, _ = inactive_user

    user = await db_session.get(User, user_id)
    user.is_active = True

    await db_session.commit()

    response = await api_client.post(
        "/auth/resend-activation",
        json={"email": "test@example.com"},
    )

    assert response.status_code == 202
    assert sent_emails == []


@pytest.mark.asyncio
async def test_resend_activation_creates_missing_token(
    api_client,
    db_session,
    inactive_user,
    sent_emails,
):
    user_id, _ = inactive_user

    result = await db_session.execute(
        select(ActivationToken).where(
            ActivationToken.user_id == user_id
        )
    )

    old_activation = result.scalar_one()

    await db_session.delete(old_activation)
    await db_session.commit()

    response = await api_client.post(
        "/auth/resend-activation",
        json={"email": "test@example.com"},
    )

    assert response.status_code == 202
    assert len(sent_emails) == 1

    result = await db_session.execute(
        select(ActivationToken).where(
            ActivationToken.user_id == user_id
        )
    )

    new_activation = result.scalar_one_or_none()

    assert new_activation is not None

    expected_hash = hashlib.sha256(
        sent_emails[0]["token"].encode("utf-8")
    ).hexdigest()

    assert new_activation.token == expected_hash


@pytest.mark.asyncio
async def test_old_token_invalid_after_resend(
    api_client,
    db_session,
    inactive_user,
    sent_emails,
):
    user_id, old_token = inactive_user

    await make_token_resendable(db_session, user_id)

    response = await api_client.post(
        "/auth/resend-activation",
        json={"email": "test@example.com"},
    )

    assert response.status_code == 202

    old_response = await api_client.get(
        "/auth/activate",
        params={"token": old_token},
    )

    assert old_response.status_code == 400

    new_token = sent_emails[0]["token"]

    new_response = await api_client.get(
        "/auth/activate",
        params={"token": new_token},
    )

    assert new_response.status_code == 200

    user = await db_session.get(User, user_id)
    await db_session.refresh(user)

    assert user.is_active is True


@pytest.mark.asyncio
async def test_resend_activation_invalid_email(
    api_client,
    sent_emails,
):
    response = await api_client.post(
        "/auth/resend-activation",
        json={"email": "invalid-email"},
    )

    assert response.status_code == 422
    assert sent_emails == []


@pytest.mark.asyncio
async def test_resend_activation_generic_response(
    api_client,
    inactive_user,
    sent_emails,
):
    existing_response = await api_client.post(
        "/auth/resend-activation",
        json={"email": "test@example.com"},
    )

    unknown_response = await api_client.post(
        "/auth/resend-activation",
        json={"email": "unknown@example.com"},
    )

    assert existing_response.status_code == 202
    assert unknown_response.status_code == 202

    assert existing_response.json() == unknown_response.json()

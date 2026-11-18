from datetime import datetime, timedelta, timezone

import jwt
import pytest

from src.jwt_service import (
    create_jwt_token,
    decode_jwt_token,
    get_jwt_secret,
)


TEST_SECRET = "test-secret-key-for-jwt-unit-tests-123456789"


@pytest.fixture(autouse=True)
def setup_jwt_secret(monkeypatch):
    monkeypatch.setenv("JWT_SECRET_KEY", TEST_SECRET)


@pytest.mark.parametrize(
    ("token_type", "expected_lifetime"),
    [
        ("access", 15 * 60),
        ("refresh", 7 * 24 * 60 * 60),
    ],
)
def test_create_jwt_token(token_type, expected_lifetime):
    token = create_jwt_token(
        user_id=1,
        token_type=token_type,
    )

    payload = decode_jwt_token(
        token,
        expected_type=token_type,
    )

    assert payload["sub"] == "1"
    assert payload["type"] == token_type
    assert payload["jti"]
    assert payload["exp"] - payload["iat"] == expected_lifetime


def test_access_token_cannot_be_used_as_refresh():
    token = create_jwt_token(1, "access")

    with pytest.raises(jwt.InvalidTokenError):
        decode_jwt_token(token, "refresh")


def test_refresh_token_cannot_be_used_as_access():
    token = create_jwt_token(1, "refresh")

    with pytest.raises(jwt.InvalidTokenError):
        decode_jwt_token(token, "access")


def test_expired_token():
    now = datetime.now(timezone.utc)

    payload = {
        "sub": "1",
        "type": "access",
        "jti": "expired-token-id",
        "iat": now - timedelta(hours=2),
        "exp": now - timedelta(hours=1),
    }

    token = jwt.encode(
        payload,
        TEST_SECRET,
        algorithm="HS256",
    )

    with pytest.raises(jwt.ExpiredSignatureError):
        decode_jwt_token(token, "access")


def test_invalid_signature(monkeypatch):
    token = create_jwt_token(1, "access")

    monkeypatch.setenv(
        "JWT_SECRET_KEY",
        "another-secret-key-with-enough-characters-123",
    )

    with pytest.raises(jwt.InvalidSignatureError):
        decode_jwt_token(token, "access")


def test_missing_required_claim():
    now = datetime.now(timezone.utc)

    payload = {
        "sub": "1",
        "type": "access",
        "jti": "test-token-id",
        "iat": now,
        # Missing "exp"
    }

    token = jwt.encode(
        payload,
        TEST_SECRET,
        algorithm="HS256",
    )

    with pytest.raises(jwt.MissingRequiredClaimError):
        decode_jwt_token(token, "access")


def test_tokens_have_unique_jti():
    first_token = create_jwt_token(1, "access")
    second_token = create_jwt_token(1, "access")

    first_payload = decode_jwt_token(
        first_token,
        "access",
    )

    second_payload = decode_jwt_token(
        second_token,
        "access",
    )

    assert first_token != second_token
    assert first_payload["jti"] != second_payload["jti"]


def test_missing_secret_key(monkeypatch):
    monkeypatch.delenv("JWT_SECRET_KEY", raising=False)

    with pytest.raises(
        RuntimeError,
        match="JWT_SECRET_KEY",
    ):
        get_jwt_secret()


def test_short_secret_key(monkeypatch):
    monkeypatch.setenv("JWT_SECRET_KEY", "short")

    with pytest.raises(
        RuntimeError,
        match="at least 32 characters",
    ):
        get_jwt_secret()

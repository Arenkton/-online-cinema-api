from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from src.schemas import UserCreate, UserRead


@pytest.mark.parametrize(
    "password",
    [
        "StrongPassword123!",
        "ValidPassword9@",
    ],
)
def test_valid_password(password):
    user = UserCreate(
        email="test@example.com",
        password=password,
    )

    assert user.password == password
    assert user.email == "test@example.com"


@pytest.mark.parametrize(
    ("password", "expected_error"),
    [
        (
            "Ab1!",
            "String should have at least 8 characters",
        ),
        (
            "lowercase123!",
            "Password must contain an uppercase letter",
        ),
        (
            "UPPERCASE123!",
            "Password must contain a lowercase letter",
        ),
        (
            "NoDigitsHere!",
            "Password must contain a digit",
        ),
        (
            "NoSpecial123",
            "Password must contain a special character",
        ),
    ],
)
def test_invalid_password(password, expected_error):
    with pytest.raises(ValidationError) as exc_info:
        UserCreate(
            email="test@example.com",
            password=password,
        )

    errors = exc_info.value.errors()

    assert errors[0]["loc"] == ("password",)
    assert expected_error in str(exc_info.value)


def test_invalid_email():
    with pytest.raises(ValidationError) as exc_info:
        UserCreate(
            email="invalid-email",
            password="StrongPassword123!",
        )

    errors = exc_info.value.errors()

    assert errors[0]["loc"] == ("email",)


def test_user_read_does_not_expose_sensitive_data():
    db_user = SimpleNamespace(
        id=1,
        email="test@example.com",
        is_active=False,
        hashed_password="secret_password_hash",
    )

    user = UserRead.model_validate(db_user)
    response = user.model_dump()

    assert response == {
        "id": 1,
        "email": "test@example.com",
        "is_active": False,
    }

    assert "password" not in response
    assert "hashed_password" not in response
    assert "activation_token" not in response

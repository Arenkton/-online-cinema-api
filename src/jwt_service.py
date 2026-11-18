import os
import secrets

from datetime import datetime, timedelta, timezone
from typing import Literal

import jwt


TokenType = Literal["access", "refresh"]

JWT_ALGORITHM = "HS256"

ACCESS_TOKEN_LIFETIME = timedelta(minutes=15)
REFRESH_TOKEN_LIFETIME = timedelta(days=7)


def get_jwt_secret() -> str:
    secret = os.getenv("JWT_SECRET_KEY")

    if not secret or len(secret) < 32:
        raise RuntimeError(
            "JWT_SECRET_KEY must contain at least 32 characters"
        )

    return secret


def create_jwt_token(
    user_id: int,
    token_type: TokenType,
) -> str:
    now = datetime.now(timezone.utc)

    lifetime = (
        ACCESS_TOKEN_LIFETIME
        if token_type == "access"
        else REFRESH_TOKEN_LIFETIME
    )

    payload = {
        "sub": str(user_id),
        "type": token_type,
        "jti": secrets.token_urlsafe(16),
        "iat": now,
        "exp": now + lifetime,
    }

    return jwt.encode(
        payload,
        get_jwt_secret(),
        algorithm=JWT_ALGORITHM,
    )


def decode_jwt_token(
    token: str,
    expected_type: TokenType,
) -> dict:
    payload = jwt.decode(
        token,
        get_jwt_secret(),
        algorithms=[JWT_ALGORITHM],
        options={
            "require": [
                "sub",
                "type",
                "jti",
                "iat",
                "exp",
            ]
        },
    )

    if payload["type"] != expected_type:
        raise jwt.InvalidTokenError(
            "Invalid token type"
        )

    return payload

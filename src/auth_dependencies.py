import jwt

from fastapi import Depends, HTTPException, status
from fastapi.security import (
    HTTPAuthorizationCredentials,
    HTTPBearer,
)
from sqlalchemy.ext.asyncio import AsyncSession

from src.database import get_db
from src.jwt_service import decode_jwt_token
from src.models import User


bearer_scheme = HTTPBearer(auto_error=False)


def credentials_exception() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(
        bearer_scheme
    ),
    db: AsyncSession = Depends(get_db),
) -> User:
    if credentials is None:
        raise credentials_exception()

    try:
        payload = decode_jwt_token(
            credentials.credentials,
            expected_type="access",
        )

        user_id = int(payload["sub"])

        if user_id <= 0 or str(user_id) != payload["sub"]:
            raise ValueError("Invalid user ID")

    except (jwt.InvalidTokenError, ValueError, TypeError) as exc:
        raise credentials_exception() from exc

    user = await db.get(User, user_id)

    if user is None or not user.is_active:
        raise credentials_exception()

    return user

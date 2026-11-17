from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    HTTPException,
    status,
)
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.crud import create_user, get_user_by_email
from src.database import get_db
from src.email_service import send_activation_email
from src.schemas import UserCreate, UserRead


router = APIRouter(
    prefix="/auth",
    tags=["Authentication"],
)


@router.post(
    "/register",
    response_model=UserRead,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new user",
    description=(
        "Creates an inactive user and sends an "
        "activation link valid for 24 hours."
    ),
)
async def register_user(
    user: UserCreate,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    try:
        new_user, raw_token = await create_user(db, user)

    except ValueError as exc:
        if str(exc) == "Email already registered":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Email already registered",
            ) from exc

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Registration unavailable",
        ) from exc

    except IntegrityError as exc:
        await db.rollback()

        existing_user = await get_user_by_email(
            db, user.email.strip().lower()
        )

        if existing_user is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Email already registered",
            ) from exc

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Registration unavailable",
        ) from exc

    background_tasks.add_task(
        send_activation_email,
        new_user.email,
        raw_token,
    )

    return new_user

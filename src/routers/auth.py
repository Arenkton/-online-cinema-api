from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    HTTPException,
    status,
    Query,
)
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.crud import(
    create_user,
    get_user_by_email,
    activate_user,
    resend_activation_token,
)
from src.database import get_db
from src.email_service import send_activation_email
from src.schemas import UserCreate, UserRead, UserBase


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


@router.get(
    "/activate",
    status_code=status.HTTP_200_OK,
    summary="Activate user account",
    description=(
        "Activates a user account using a valid "
        "one-time token from the activation email."
    ),
)
async def activate_account(
    token: str = Query(
        ...,
        min_length=1,
        max_length=256,
    ),
    db: AsyncSession = Depends(get_db),
):
    activated = await activate_user(
        db=db,
        raw_token=token,
    )

    if not activated:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired activation token",
        )

    return {
        "message": "Account activated successfully"
    }


@router.post(
    "/resend-activation",
    status_code=status.HTTP_202_ACCEPTED,
    summary="Resend account activation email",
    description=(
        "Requests a new activation email for an "
        "inactive account. Requests are limited "
        "to one every 5 minutes."
    ),
)
async def resend_activation(
    data: UserBase,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    result = await resend_activation_token(
        db=db,
        email=data.email,
    )

    if result is not None:
        email, raw_token = result

        background_tasks.add_task(
            send_activation_email,
            email,
            raw_token,
        )

    return {
        "message": (
            "If this email belongs to an inactive "
            "account, an activation email may be sent."
        )
    }

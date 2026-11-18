from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    status,
)
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth_dependencies import get_current_user
from src.crud import (
    PaymentConflictError,
    create_payment_from_order,
)
from src.database import get_db
from src.models import User
from src.schemas import PaymentCreate, PaymentRead


router = APIRouter(
    prefix="/payments",
    tags=["Payments"],
)


@router.post(
    "",
    response_model=PaymentRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create payment",
    description=(
        "Creates a pending payment attempt "
        "for an authenticated user's order."
    ),
)
async def create_payment(
    data: PaymentCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        payment = await create_payment_from_order(
            db=db,
            user_id=current_user.id,
            order_id=data.order_id,
        )
    except PaymentConflictError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc

    if payment is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Order not found",
        )

    return payment

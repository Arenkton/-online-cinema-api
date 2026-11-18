from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    status,
)
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth_dependencies import get_current_user
from src.crud import create_order_from_cart
from src.database import get_db
from src.models import User
from src.schemas import OrderRead


router = APIRouter(
    prefix="/orders",
    tags=["Orders"],
)


@router.post(
    "",
    response_model=OrderRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create order",
    description=(
        "Creates a pending order from the "
        "authenticated user's shopping cart."
    ),
)
async def create_order(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    order = await create_order_from_cart(
        db=db,
        user_id=current_user.id,
    )

    if order is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Shopping cart is empty",
        )

    return order

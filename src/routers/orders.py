from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    status,
    Path,
)
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth_dependencies import get_current_user
from src.crud import(
    AllCartItemsPurchasedError,
    PendingOrderConflictError,
    create_order_from_cart,
    get_user_orders,
    get_user_order,
)
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
    try:
        order = await create_order_from_cart(
            db=db,
            user_id=current_user.id,
        )

    except AllCartItemsPurchasedError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="All movies in cart are already purchased",
        ) from exc

    except PendingOrderConflictError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Movie already exists in a pending order",
        ) from exc

    if order is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Shopping cart is empty",
        )

    return order


@router.get(
    "",
    response_model=list[OrderRead],
    status_code=status.HTTP_200_OK,
    summary="Get user orders",
    description=(
        "Returns all orders belonging to "
        "the authenticated user."
    ),
)
async def list_orders(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return await get_user_orders(
        db=db,
        user_id=current_user.id,
    )


@router.get(
    "/{order_id}",
    response_model=OrderRead,
    status_code=status.HTTP_200_OK,
    summary="Get order details",
    description=(
        "Returns a specific order belonging "
        "to the authenticated user."
    ),
)
async def get_order_details(
    order_id: int = Path(gt=0),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    order = await get_user_order(
        db=db,
        user_id=current_user.id,
        order_id=order_id,
    )

    if order is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Order not found",
        )

    return order

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    status,
    Path,
)
from sqlalchemy import select, delete
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from decimal import Decimal

from src.auth_dependencies import get_current_user
from src.crud import (
    add_movie_to_cart,
    get_cart_items,
    remove_movie_from_cart,
)
from src.database import get_db
from src.models import (
    Movie,
    User,
    Cart,
    CartItem,
    Order,
    OrderItem,
)
from src.schemas import (
    CartItemCreate,
    CartItemRead,
    CartRead,
    CartMovieRead,
)


router = APIRouter(
    prefix="/cart",
    tags=["Cart"],
)


@router.post(
    "/items",
    response_model=CartItemRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_cart_item(
    data: CartItemCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    movie = await db.get(Movie, data.movie_id)

    if movie is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Movie not found",
        )

    # Check whether the user already purchased this movie.
    purchased_movie_id = await db.scalar(
        select(OrderItem.movie_id)
        .join(Order, OrderItem.order_id == Order.id)
        .where(
            Order.user_id == current_user.id,
            Order.status == "paid",
            OrderItem.movie_id == data.movie_id,
        )
        .limit(1)
    )

    if purchased_movie_id is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Movie has already been purchased",
        )

    try:
        item = await add_movie_to_cart(
            db=db,
            user_id=current_user.id,
            movie_id=data.movie_id,
        )
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Cart operation conflict",
        ) from exc

    if item is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Movie is already in cart",
        )

    return item


@router.get(
    "",
    response_model=CartRead,
    status_code=status.HTTP_200_OK,
    summary="Get shopping cart",
    description=(
        "Returns the authenticated user's cart "
        "with movie details and total price."
    ),
)
async def get_cart(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    cart_items = await get_cart_items(
        db=db,
        user_id=current_user.id,
    )

    items = [
        CartMovieRead(
            id=item.id,
            movie_id=item.movie_id,
            name=item.movie.name,
            price=item.movie.price,
            added_at=item.added_at,
        )
        for item in cart_items
    ]

    total_price = sum(
        (item.price for item in items),
        Decimal("0.00"),
    )

    return CartRead(
        items=items,
        total_price=total_price,
    )


@router.delete(
    "/items/{movie_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Remove movie from cart",
    description=(
        "Removes a movie from the authenticated "
        "user's shopping cart."
    ),
)
async def delete_cart_item(
    movie_id: int = Path(gt=0),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> None:
    removed = await remove_movie_from_cart(
        db=db,
        user_id=current_user.id,
        movie_id=movie_id,
    )

    if not removed:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Movie not found in cart",
        )


@router.delete(
    "",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def clear_cart(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    cart_id = await db.scalar(
        select(Cart.id).where(
            Cart.user_id == current_user.id
        )
    )

    if cart_id is not None:
        await db.execute(
            delete(CartItem).where(
                CartItem.cart_id == cart_id
            )
        )
        await db.commit()

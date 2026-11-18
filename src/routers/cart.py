from fastapi import(
    APIRouter,
    Depends,
    HTTPException,
    status,
    Path,
)
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from decimal import Decimal

from src.auth_dependencies import get_current_user
from src.crud import(
    add_movie_to_cart,
    get_cart_items,
    remove_movie_from_cart,
)
from src.database import get_db
from src.models import Movie, User
from src.schemas import(
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

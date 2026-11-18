from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth_dependencies import get_current_user
from src.crud import add_movie_to_cart
from src.database import get_db
from src.models import Movie, User
from src.schemas import CartItemCreate, CartItemRead


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

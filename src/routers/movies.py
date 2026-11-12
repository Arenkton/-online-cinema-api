from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.database import get_db
from src import crud
from src.schemas import MovieCreate, MovieRead, MovieUpdate


router = APIRouter(
    prefix="/movies",
    tags=["Movies"]
)


@router.post(
    "/",
    response_model=MovieRead,
    status_code=status.HTTP_201_CREATED
)
async def create_movie(
    movie: MovieCreate,
    db: AsyncSession = Depends(get_db)
):
    try:
        return await crud.create_movie(db, movie)
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Movie violates database constraints"
        )


@router.get(
    "/",
    response_model=list[MovieRead]
)
async def get_movies(
    db: AsyncSession = Depends(get_db)
):
    return await crud.get_movies(db)


@router.get(
    "/{movie_id}",
    response_model=MovieRead
)
async def get_movie(
    movie_id: int,
    db: AsyncSession = Depends(get_db)
):
    movie = await crud.get_movie(db, movie_id)

    if movie is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Movie not found"
        )

    return movie


@router.patch(
    "/{movie_id}",
    response_model=MovieRead
)
async def update_movie(
    movie_id: int,
    movie: MovieUpdate,
    db: AsyncSession = Depends(get_db)
):
    required_fields = {
        "name",
        "year",
        "time",
        "imdb",
        "votes",
        "description",
        "price",
        "certification_id",
    }

    update_data = movie.model_dump(exclude_unset=True)

    if any(
            field in required_fields and value is None
            for field, value in update_data.items()
    ):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Required movie fields cannot be null"
        )

    try:
        updated_movie = await crud.update_movie(
            db, movie_id, movie
        )
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Movie with this name already exists"
        )

    if updated_movie is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Movie not found"
        )

    return updated_movie


@router.delete(
    "/{movie_id}",
    status_code=status.HTTP_204_NO_CONTENT
)
async def delete_movie(
    movie_id: int,
    db: AsyncSession = Depends(get_db)
):
    try:
        deleted_movie = await crud.delete_movie(
            db, movie_id
        )
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Movie cannot be deleted due to related records"
        )

    if deleted_movie is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Movie not found"
        )

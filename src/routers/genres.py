from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.database import get_db
from src import crud
from src.schemas import GenreCreate, GenreUpdate, GenreResponse


router = APIRouter(
    prefix="/genres",
    tags=["Genres"]
)


@router.post(
    "/",
    response_model=GenreResponse,
    status_code=status.HTTP_201_CREATED
)
async def create_genre(
    genre: GenreCreate,
    db: AsyncSession = Depends(get_db)
):
    try:
        return await crud.create_genre(db, genre)
    except IntegrityError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Genre already exists"
        )


@router.get(
    "/",
    response_model=list[GenreResponse]
)
async def get_genres(
    db: AsyncSession = Depends(get_db)
):
    return await crud.get_genres(db)


@router.get(
    "/{genre_id}",
    response_model=GenreResponse
)
async def get_genre(
    genre_id: int,
    db: AsyncSession = Depends(get_db)
):
    genre = await crud.get_genre(db, genre_id)

    if genre is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Genre not found"
        )

    return genre


@router.patch(
    "/{genre_id}",
    response_model=GenreResponse
)
async def update_genre(
    genre_id: int,
    genre: GenreUpdate,
    db: AsyncSession = Depends(get_db)
):
    if "name" in genre.model_fields_set and genre.name is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Genre name cannot be null"
        )

    try:
        updated_genre = await crud.update_genre(
            db, genre_id, genre
        )
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Genre with this name already exists"
        )

    if updated_genre is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Genre not found"
        )

    return updated_genre


@router.delete(
    "/{genre_id}",
    status_code=status.HTTP_204_NO_CONTENT
)
async def delete_genre(
    genre_id: int,
    db: AsyncSession = Depends(get_db)
):
    try:
        deleted_genre = await crud.delete_genre(
            db, genre_id
        )
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Genre cannot be deleted due to related records"
        )

    if deleted_genre is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Genre not found"
        )

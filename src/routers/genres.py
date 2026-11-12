from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.database import get_db
from src import crud
from src.schemas import GenreCreate, GenreResponse


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

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from src.models import Movie
from src.schemas import MovieCreate, MovieRead
from src.database import get_db

router = APIRouter()


@router.get("/movies/{movie_id}", response_model=MovieRead)
async def get_movie(
    movie_id: int,
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(
        select(Movie).where(Movie.id == movie_id)
    )
    movie = result.scalar_one_or_none()

    if not movie:
        raise HTTPException(
            status_code=404,
            detail="Movie not found"
        )

    return movie


@router.post("/movies/", response_model=MovieRead, status_code=201)
async def create_movie(
    movie: MovieCreate,
    db: AsyncSession = Depends(get_db)
):
    new_movie = Movie(**movie.model_dump())

    db.add(new_movie)
    await db.commit()
    await db.refresh(new_movie)

    return new_movie

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.database import get_db
from src import crud
from src.schemas import DirectorCreate, DirectorResponse


router = APIRouter(
    prefix="/directors",
    tags=["Directors"],
)


@router.post(
    "/",
    response_model=DirectorResponse,
    status_code=status.HTTP_201_CREATED
)
async def create_director(
    director: DirectorCreate,
    db: AsyncSession = Depends(get_db)
):
    try:
        return await crud.create_director(db, director)
    except IntegrityError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Director already exists"
        )


@router.get(
    "/",
    response_model=list[DirectorResponse]
)
async def get_directors(
    db: AsyncSession = Depends(get_db)
):
    return await crud.get_directors(db)

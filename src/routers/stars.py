from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.database import get_db
from src import crud
from src.schemas import StarCreate, StarResponse


router = APIRouter(
    prefix="/stars",
    tags=["Stars"]
)


@router.post(
    "/",
    response_model=StarResponse,
    status_code=status.HTTP_201_CREATED
)
async def create_star(
        star: StarCreate,
        db: AsyncSession = Depends(get_db),
):
    try:
        return await crud.create_star(db, star)
    except IntegrityError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This star already exists"
        )


@router.get(
    "/",
    response_model=list[StarResponse],
)
async def get_all_stars(
        db: AsyncSession = Depends(get_db),
):
    return await crud.get_stars(db)

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.database import get_db
from src import crud
from src.schemas import StarCreate, StarUpdate, StarResponse


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


@router.get(
    "/{star_id}",
    response_model=StarResponse
)
async def get_star(
    star_id: int,
    db: AsyncSession = Depends(get_db)
):
    star = await crud.get_genre(db, star_id)

    if star is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Genre not found"
        )

    return star


@router.patch(
    "/{genre_id}",
    response_model=StarResponse
)
async def update_star(
    star_id: int,
    star: StarUpdate,
    db: AsyncSession = Depends(get_db)
):
    if "name" in star.model_fields_set and star.name is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Genre name cannot be null"
        )

    try:
        updated_star = await crud.update_star(
            db, star_id, star
        )
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Star with this name already exists"
        )

    if updated_star is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Star not found"
        )

    return updated_star


@router.delete(
    "/{star_id}",
    status_code=status.HTTP_204_NO_CONTENT
)
async def delete_star(
    star_id: int,
    db: AsyncSession = Depends(get_db)
):
    try:
        deleted_star = await crud.delete_star(
            db, star_id
        )
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Star cannot be deleted due to related records"
        )

    if deleted_star is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Star not found"
        )

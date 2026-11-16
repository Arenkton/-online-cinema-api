from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.database import get_db
from src import crud
from src.schemas import DirectorCreate, DirectorUpdate, DirectorResponse


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


@router.get(
    "/{director_id}",
    response_model=DirectorResponse
)
async def get_director(
    director_id: int,
    db: AsyncSession = Depends(get_db)
):
    director = await crud.get_director(db, director_id)

    if director is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="director not found"
        )

    return director


@router.patch(
    "/{director_id}",
    response_model=DirectorResponse
)
async def update_director(
    director_id: int,
    director: DirectorUpdate,
    db: AsyncSession = Depends(get_db)
):
    if "name" in director.model_fields_set and director.name is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Director name cannot be null"
        )

    try:
        updated_director = await crud.update_director(
            db, director_id, director
        )
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Director with this name already exists"
        )

    if updated_director is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Director not found"
        )

    return updated_director


@router.delete(
    "/{director_id}",
    status_code=status.HTTP_204_NO_CONTENT
)
async def delete_director(
    director_id: int,
    db: AsyncSession = Depends(get_db)
):
    try:
        deleted_director = await crud.delete_director(
            db, director_id
        )
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Director cannot be deleted due to related records"
        )

    if deleted_director is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Director not found"
        )

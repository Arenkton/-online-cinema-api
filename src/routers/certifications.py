from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.database import get_db
from src import crud
from src.schemas import CertificationCreate, CertificationUpdate, CertificationRead


router = APIRouter(
    prefix="/certifications",
    tags=["Certifications"]
)


@router.post(
    "/",
    response_model=CertificationRead,
    status_code=status.HTTP_201_CREATED
)
async def create_certification(
    certification: CertificationCreate,
    db: AsyncSession = Depends(get_db)
):
    try:
        return await crud.create_certification(
            db, certification
        )
    except IntegrityError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Certification already exists"
        )


@router.get(
    "/",
    response_model=list[CertificationRead]
)
async def get_certifications(
    db: AsyncSession = Depends(get_db)
):
    return await crud.get_certifications(db)


@router.get(
    "/{certification_id}",
    response_model=CertificationRead
)
async def get_certification(
    certification_id: int,
    db: AsyncSession = Depends(get_db)
):
    certification = await crud.get_certification(db, certification_id)

    if certification is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Certification not found"
        )

    return certification


@router.patch(
    "/{certification_id}",
    response_model=CertificationRead
)
async def update_certification(
    certification_id: int,
    certification: CertificationUpdate,
    db: AsyncSession = Depends(get_db)
):
    if "name" in certification.model_fields_set and certification.name is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Certification name cannot be null"
        )

    try:
        updated_certification = await crud.update_certification(
            db, certification_id, certification
        )
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Certification with this name already exists"
        )

    if updated_certification is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Certification not found"
        )

    return updated_certification

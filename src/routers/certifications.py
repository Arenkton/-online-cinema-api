from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.database import get_db
from src import crud
from src.schemas import CertificationCreate, CertificationRead


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

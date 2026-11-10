
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field


# ==================== MOVIES ====================

class MovieBase(BaseModel):
    name: str = Field(min_length=1)
    year: int = Field(gt=0)
    time: int = Field(gt=0)
    imdb: float = Field(ge=0, le=10)
    votes: int = Field(ge=0)
    description: str = Field(min_length=1)
    price: Decimal = Field(
        ge=0, max_digits=10, decimal_places=2
    )
    certification_id: int

    meta_score: float | None = None
    gross: float | None = None


class MovieCreate(MovieBase):
    pass


class MovieRead(MovieBase):
    id: int
    uuid: UUID

    model_config = ConfigDict(from_attributes=True)


class MovieUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1)
    year: int | None = Field(default=None, gt=0)
    time: int | None = Field(default=None, gt=0)
    imdb: float | None = Field(default=None, ge=0, le=10)
    votes: int | None = Field(default=None, ge=0)
    description: str | None = Field(default=None, min_length=1)
    price: Decimal | None = Field(
        default=None, ge=0, max_digits=10, decimal_places=2
    )
    certification_id: int | None = None
    meta_score: float | None = None
    gross: float | None = None


# ==================== USERS ====================

class UserBase(BaseModel):
    email: EmailStr


class UserCreate(UserBase):
    password: str = Field(min_length=8)


class UserRead(UserBase):
    id: int

    model_config = ConfigDict(from_attributes=True)


# ==================== CERTIFICATIONS ====================

class CertificationCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)


class CertificationUpdate(BaseModel):
    name: str | None = Field(
        default=None, min_length=1, max_length=100
    )


class CertificationRead(CertificationCreate):
    id: int

    model_config = ConfigDict(from_attributes=True)


# ==================== GENRES ====================

class GenreCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)


class GenreUpdate(BaseModel):
    name: str | None = Field(
        default=None, min_length=1, max_length=100
    )


class GenreResponse(GenreCreate):
    id: int

    model_config = ConfigDict(from_attributes=True)


# ==================== STARS ====================

class StarCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)


class StarUpdate(BaseModel):
    name: str | None = Field(
        default=None, min_length=1, max_length=100
    )


class StarResponse(StarCreate):
    id: int

    model_config = ConfigDict(from_attributes=True)


# ==================== DIRECTORS ====================

class DirectorCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)


class DirectorUpdate(BaseModel):
    name: str | None = Field(
        default=None, min_length=1, max_length=100
    )


class DirectorResponse(DirectorCreate):
    id: int

    model_config = ConfigDict(from_attributes=True)

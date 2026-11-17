import re

from decimal import Decimal
from uuid import UUID
from typing import Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
    field_validator,
)

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
    genre_ids: list[int] = Field(default_factory=list)
    star_ids: list[int] = Field(default_factory=list)
    director_ids: list[int] = Field(default_factory=list)


class MovieRead(MovieBase):
    id: int
    uuid: UUID

    genres: list[GenreResponse] = Field(default_factory=list)
    stars: list[StarResponse] = Field(default_factory=list)
    directors: list[DirectorResponse] = Field(default_factory=list)

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
    genre_ids: list[int] = Field(default_factory=list)
    star_ids: list[int] = Field(default_factory=list)
    director_ids: list[int] = Field(default_factory=list)


# ==================== USERS ====================

class UserBase(BaseModel):
    email: EmailStr


class UserCreate(UserBase):
    password: str = Field(min_length=8)

    @field_validator("password")
    @classmethod
    def validate_password(cls, value: str) -> str:
        if not re.search(r"[A-Z]", value):
            raise ValueError("Password must contain an uppercase letter")

        if not re.search(r"[a-z]", value):
            raise ValueError("Password must contain a lowercase letter")

        if not re.search(r"\d", value):
            raise ValueError("Password must contain a digit")

        if not re.search(r"[^A-Za-z0-9]", value):
            raise ValueError("Password must contain a special character")

        return value


class UserRead(UserBase):
    id: int
    is_active: bool

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


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: Literal["bearer"] = "bearer"

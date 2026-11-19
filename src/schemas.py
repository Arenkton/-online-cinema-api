import re

from decimal import Decimal
from uuid import UUID
from typing import Literal
from datetime import datetime

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


class MovieRead(MovieBase):
    id: int
    uuid: UUID

    genres: list[GenreResponse] = Field(default_factory=list)
    stars: list[StarResponse] = Field(default_factory=list)
    directors: list[DirectorResponse] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: Literal["bearer"] = "bearer"


class RefreshTokenRequest(BaseModel):
    refresh_token: str = Field(min_length=1)


class CartItemCreate(BaseModel):
    movie_id: int = Field(gt=0)


class CartItemRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    movie_id: int
    added_at: datetime


class CartMovieRead(BaseModel):
    id: int
    movie_id: int
    name: str
    price: Decimal
    added_at: datetime


class CartRead(BaseModel):
    items: list[CartMovieRead]
    total_price: Decimal


class OrderItemRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    movie_id: int
    price_at_order: Decimal


class OrderRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    created_at: datetime
    status: str
    total_amount: Decimal
    items: list[OrderItemRead]


class PaymentCreate(BaseModel):
    order_id: int = Field(gt=0)


class PaymentItemRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    order_item_id: int
    price_at_payment: Decimal


class PaymentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    order_id: int
    created_at: datetime
    status: str
    amount: Decimal
    external_payment_id: str | None
    items: list[PaymentItemRead]


class CheckoutSessionRead(BaseModel):
    payment_id: int
    session_id: str
    checkout_url: str


class RefundRead(BaseModel):
    payment_id: int
    refund_id: str
    refund_status: str
    payment_status: str
    order_status: str

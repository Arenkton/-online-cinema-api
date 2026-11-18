from datetime import datetime
from enum import Enum
from operator import index
from uuid import uuid4

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    Uuid,
    false,
    func,
    Date,
    Enum as SQLEnum,
)
from sqlalchemy.orm import (
    Mapped,
    declarative_base,
    mapped_column,
    relationship,
)


class UserGroupEnum(str, Enum):
    USER = "USER"
    MODERATOR = "MODERATOR"
    ADMIN = "ADMIN"


class GenderEnum(str, Enum):
    MAN = "MAN"
    WOMAN = "WOMAN"


Base = declarative_base()


class UserGroup(Base):
    __tablename__ = "user_groups"

    id: Mapped[int] = mapped_column(
        primary_key=True
    )

    name: Mapped[str] = mapped_column(
        String(50),
        unique=True,
        nullable=False
    )

    users: Mapped[list["User"]] = relationship(
        "User",
        back_populates="group"
    )


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(
        primary_key=True
    )

    email: Mapped[str] = mapped_column(
        String(255),
        unique=True,
        nullable=False,
        index=True
    )

    hashed_password: Mapped[str] = mapped_column(
        String(255),
        nullable=False
    )

    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        server_default=false(),
        nullable=False
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False
    )

    group_id: Mapped[int] = mapped_column(
        ForeignKey("user_groups.id"),
        nullable=False
    )

    group: Mapped["UserGroup"] = relationship(
        "UserGroup",
        back_populates="users"
    )

    profile: Mapped["UserProfile | None"] = relationship(
        "UserProfile",
        back_populates="user",
        uselist=False
    )

    activation_token: Mapped["ActivationToken | None"] = relationship(
        "ActivationToken",
        back_populates="user",
        uselist=False,
        cascade="all, delete-orphan"
    )

    password_reset_token: Mapped["PasswordResetToken | None"] = relationship(
        "PasswordResetToken",
        back_populates="user",
        uselist=False,
        cascade="all, delete-orphan"
    )

    refresh_tokens: Mapped[list["RefreshToken"]] = relationship(
        "RefreshToken",
        back_populates="user",
        cascade="all, delete-orphan"
    )


class UserProfile(Base):
    __tablename__ = "user_profiles"

    id = Column(Integer, primary_key=True)

    user_id = Column(
        Integer,
        ForeignKey("users.id"),
        unique=True,
        nullable=False
    )

    first_name = Column(String(100), nullable=True)
    last_name = Column(String(100), nullable=True)
    avatar = Column(String(255), nullable=True)

    gender = Column(
        SQLEnum(GenderEnum),
        nullable=True
    )

    date_of_birth = Column(Date, nullable=True)
    info = Column(Text, nullable=True)

    user = relationship(
        "User",
        back_populates="profile"
    )


class ActivationToken(Base):
    __tablename__ = "activation_tokens"

    id = Column(Integer, primary_key=True)

    user_id = Column(
        Integer,
        ForeignKey("users.id"),
        unique=True,
        nullable=False
    )

    token = Column(
        String(255),
        unique=True,
        nullable=False
    )

    expires_at = Column(
        DateTime(timezone=True),
        nullable=False
    )

    user = relationship(
        "User",
        back_populates="activation_token"
    )


class PasswordResetToken(Base):
    __tablename__ = "password_reset_tokens"

    id = Column(Integer, primary_key=True)

    user_id = Column(
        Integer,
        ForeignKey("users.id"),
        unique=True,
        nullable=False
    )

    token = Column(
        String(255),
        unique=True,
        nullable=False
    )

    expires_at = Column(
        DateTime(timezone=True),
        nullable=False
    )

    user = relationship(
        "User",
        back_populates="password_reset_token"
    )


class RefreshToken(Base):
    __tablename__ = "refresh_tokens"

    id = Column(Integer, primary_key=True)

    user_id = Column(
        Integer,
        ForeignKey("users.id"),
        nullable=False
    )

    token = Column(
        String(255),
        unique=True,
        nullable=False
    )

    expires_at = Column(
        DateTime(timezone=True),
        nullable=False
    )

    user = relationship(
        "User",
        back_populates="refresh_tokens"
    )


class Movie(Base):
    __tablename__ = "movies"

    id = Column(Integer, primary_key=True, autoincrement=True)
    uuid = Column(Uuid(as_uuid=True), default=uuid4,
                  unique=True, nullable=False)

    name = Column(String, nullable=False)
    year = Column(Integer, nullable=False)
    time = Column(Integer, nullable=False)
    imdb = Column(Float, nullable=False)
    votes = Column(Integer, nullable=False)

    meta_score = Column(Float, nullable=True)
    gross = Column(Float, nullable=True)

    description = Column(Text, nullable=False)
    price = Column(Numeric(10, 2), nullable=False)

    certification_id = Column(
        Integer,
        ForeignKey("certifications.id"),
        nullable=False
    )

    certification = relationship(
        "Certification",
        back_populates="movies"
    )

    stars = relationship(
        "Star",
        secondary="movie_stars",
        back_populates="movies"
    )

    genres = relationship(
        "Genre",
        secondary="movie_genres",
        back_populates="movies")

    directors = relationship(
        "Director",
        secondary="movie_directors",
        back_populates="movies"
    )


class Certification(Base):
    __tablename__ = "certifications"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, index=True, nullable=False)
    movies = relationship(
        "Movie",
        back_populates="certification"
    )


class MovieStars(Base):
    __tablename__ = "movie_stars"
    movie_id = Column(Integer, ForeignKey("movies.id"), primary_key=True)
    star_id = Column(Integer, ForeignKey("stars.id"), primary_key=True)


class Star(Base):
    __tablename__ = "stars"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), unique=True, index=True, nullable=False)
    movies = relationship(
        "Movie",
        secondary="movie_stars",
        back_populates="stars"
    )


class MovieGenres(Base):
    __tablename__ = "movie_genres"
    movie_id = Column(Integer, ForeignKey("movies.id"), primary_key=True)
    genre_id = Column(Integer, ForeignKey("genres.id"), primary_key=True)


class Genre(Base):
    __tablename__ = "genres"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), unique=True, index=True, nullable=False)
    movies = relationship(
        "Movie",
        secondary="movie_genres",
        back_populates="genres"
    )


class MovieDirectors(Base):
    __tablename__ = "movie_directors"
    movie_id = Column(Integer, ForeignKey("movies.id"), primary_key=True)
    director_id = Column(Integer, ForeignKey("directors.id"), primary_key=True)


class Director(Base):
    __tablename__ = "directors"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), unique=True, index=True, nullable=False)
    movies = relationship(
        "Movie",
        secondary="movie_directors",
        back_populates="directors"
    )

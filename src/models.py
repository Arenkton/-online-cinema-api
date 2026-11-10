from sqlalchemy import (
    Column,
    Integer,
    String,
    Float,
    Text,
    Numeric,
    ForeignKey,
    Uuid,
)
from sqlalchemy.ext.declarative import declarative_base
from uuid import uuid4
from sqlalchemy import Uuid
from sqlalchemy.orm import relationship

Base = declarative_base()


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)


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

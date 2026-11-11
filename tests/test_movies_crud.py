from decimal import Decimal
from uuid import UUID

import pytest
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from src.crud import (
    create_certification,
    create_director,
    create_genre,
    create_movie,
    create_star,
    delete_movie,
    get_movie,
    get_movies,
    update_movie,
)
from src.models import Movie, MovieDirectors, MovieGenres, MovieStars
from src.schemas import (
    CertificationCreate,
    DirectorCreate,
    GenreCreate,
    MovieCreate,
    MovieRead,
    MovieUpdate,
    StarCreate,
)

pytestmark = pytest.mark.asyncio


def movie_data(certification_id: int, **overrides) -> MovieCreate:
    data = {
        "name": "Inception",
        "year": 2010,
        "time": 148,
        "imdb": 8.8,
        "votes": 2500000,
        "description": "A science-fiction thriller",
        "price": Decimal("9.99"),
        "certification_id": certification_id,
    }
    data.update(overrides)
    return MovieCreate(**data)


async def make_certification(db_session):
    # Helper, not a pytest fixture: each test controls its own setup.
    return await create_certification(
        db_session, CertificationCreate(name="PG-13")
    )


async def test_create_movie_and_read_back(db_session):
    cert = await make_certification(db_session)
    movie = await create_movie(db_session, movie_data(cert.id))
    assert movie.id is not None
    assert isinstance(movie.uuid, UUID)
    assert movie.price == Decimal("9.99")
    stored = await get_movie(db_session, movie.id)
    assert stored is not None and stored.name == "Inception"


async def test_movie_read_pydantic_serialization(db_session):
    cert = await make_certification(db_session)
    created = await create_movie(db_session, movie_data(cert.id))
    response = MovieRead.model_validate(created)
    assert response.id == created.id
    assert response.uuid == created.uuid
    assert response.price == Decimal("9.99")


async def test_get_movie_missing(db_session):
    assert await get_movie(db_session, 999) is None


async def test_get_movies(db_session):
    cert = await make_certification(db_session)
    await create_movie(db_session, movie_data(cert.id, name="Inception"))
    await create_movie(db_session, movie_data(cert.id, name="Interstellar"))
    result = await get_movies(db_session)
    assert {movie.name for movie in result} == {"Inception", "Interstellar"}


async def test_get_movies_empty(db_session):
    assert await get_movies(db_session) == []


async def test_update_movie_partial(db_session):
    cert = await make_certification(db_session)
    created = await create_movie(db_session, movie_data(cert.id))
    updated = await update_movie(
        db_session, created.id, MovieUpdate(price=Decimal("12.50"))
    )
    assert updated is not None
    assert updated.price == Decimal("12.50")
    assert updated.name == "Inception"
    assert (await get_movie(db_session, created.id)).price == Decimal("12.50")


async def test_update_movie_missing(db_session):
    assert await update_movie(
        db_session, 999, MovieUpdate(name="Unknown")
    ) is None


async def test_update_movie_without_changes(db_session):
    cert = await make_certification(db_session)
    created = await create_movie(db_session, movie_data(cert.id))
    result = await update_movie(db_session, created.id, MovieUpdate())
    assert result is not None and result.name == "Inception"


async def test_delete_movie(db_session):
    cert = await make_certification(db_session)
    created = await create_movie(db_session, movie_data(cert.id))
    deleted = await delete_movie(db_session, created.id)
    assert deleted is not None and deleted.id == created.id
    assert await get_movie(db_session, created.id) is None


async def test_delete_movie_missing(db_session):
    assert await delete_movie(db_session, 999) is None


async def test_movie_relationships_load(db_session):
    """Verify relation tables round-trip via eager loading.

    Current create_movie() does not yet accept lists of genre/star/director IDs.
    We create association records directly until that feature is implemented.
    """
    cert = await make_certification(db_session)
    movie = await create_movie(db_session, movie_data(cert.id))
    genre = await create_genre(db_session, GenreCreate(name="Sci-Fi"))
    star = await create_star(db_session, StarCreate(name="Actor One"))
    director = await create_director(
        db_session, DirectorCreate(name="Director One")
    )

    db_session.add_all([
        MovieGenres(movie_id=movie.id, genre_id=genre.id),
        MovieStars(movie_id=movie.id, star_id=star.id),
        MovieDirectors(movie_id=movie.id, director_id=director.id),
    ])
    await db_session.commit()

    result = await db_session.execute(
        select(Movie)
        .options(
            selectinload(Movie.genres),
            selectinload(Movie.stars),
            selectinload(Movie.directors),
            selectinload(Movie.certification),
        )
        .where(Movie.id == movie.id)
    )
    loaded = result.scalar_one()
    assert [genre.name for genre in loaded.genres] == ["Sci-Fi"]
    assert [star.name for star in loaded.stars] == ["Actor One"]
    assert [director.name for director in loaded.directors] == ["Director One"]
    assert loaded.certification.name == "PG-13"

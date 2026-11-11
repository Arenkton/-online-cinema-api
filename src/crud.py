from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from src.models import Movie, Genre, Certification
from src.schemas import (
    MovieCreate,
    MovieUpdate,
    GenreCreate,
    GenreUpdate,
    CertificationCreate,
    CertificationUpdate,
    StarCreate,
    StarUpdate,
    DirectorCreate,
    DirectorUpdate,
)

async def create_movie(
    db: AsyncSession,
    movie: MovieCreate
) -> Movie:
    new_movie = Movie(**movie.model_dump())

    db.add(new_movie)
    await db.commit()
    await db.refresh(new_movie)

    return new_movie


async def get_movie(
    db: AsyncSession,
    movie_id: int
) -> Movie | None:
    result = await db.execute(
        select(Movie).where(Movie.id == movie_id)
    )

    return result.scalar_one_or_none()


async def get_movies(
    db: AsyncSession
) -> list[Movie]:
    result = await db.execute(select(Movie))

    return result.scalars().all()


async def update_movie(
    db: AsyncSession,
    movie_id: int,
    movie: MovieUpdate
) -> Movie | None:
    db_movie = await get_movie(db, movie_id)

    if db_movie is None:
        return None

    update_data = movie.model_dump(exclude_unset=True)

    for field, value in update_data.items():
        setattr(db_movie, field, value)

    await db.commit()
    await db.refresh(db_movie)

    return db_movie


async def delete_movie(
    db: AsyncSession,
    movie_id: int
) -> Movie | None:
    db_movie = await get_movie(db, movie_id)

    if db_movie is None:
        return None

    await db.delete(db_movie)
    await db.commit()

    return db_movie


async def create_genre(db: AsyncSession, genre: GenreCreate) -> Genre:
    new_genre = Genre(**genre.model_dump())

    db.add(new_genre)

    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise

    await db.refresh(new_genre)

    return new_genre


async def get_genre(
    db: AsyncSession,
    genre_id: int
) -> Genre | None:
    result = await db.execute(
        select(Genre).where(Genre.id == genre_id)
    )
    return result.scalar_one_or_none()


async def get_genres(db: AsyncSession) -> list[Genre]:
    result = await db.execute(select(Genre).order_by(Genre.name))

    return result.scalars().all()


async def update_genre(
    db: AsyncSession,
    genre_id: int,
    genre: GenreUpdate
) -> Genre | None:
    db_genre = await get_genre(db, genre_id)

    if db_genre is None:
        return None

    update_data = genre.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(db_genre, field, value)

    await db.commit()
    await db.refresh(db_genre)

    return db_genre


async def delete_genre(
    db: AsyncSession,
    genre_id: int
) -> Genre | None:
    db_genre = await get_genre(db, genre_id)

    if db_genre is None:
        return None

    await db.delete(db_genre)
    await db.commit()

    return db_genre


async def create_certification(
    db: AsyncSession,
    certification: CertificationCreate
) -> Certification:
    new_certification = Certification(**certification.model_dump())

    db.add(new_certification)

    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise

    await db.refresh(new_certification)

    return new_certification


async def get_certification(
        db: AsyncSession,
        certification_id: int
) -> Certification | None:
    result = await db.execute(select(Certification).where(Certification.id == certification_id))

    return result.scalar_one_or_none()


async def get_certifications(db: AsyncSession) -> list[Certification]:
    result = await db.execute(select(Certification).order_by(Certification.id))

    return result.scalars().all()


async def update_certification(
    db: AsyncSession,
    certification_id: int,
    certification: CertificationUpdate
) -> Certification | None:
    db_certification = await get_certification(db, certification_id)

    if db_certification is None:
        return None

    update_data = certification.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(db_certification, field, value)

    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise

    await db.refresh(db_certification)

    return db_certification


async def create_star(
    db: AsyncSession,
    star: StarCreate
) -> Star:
    new_star = Star(**star.model_dump())
    db.add(new_star)

    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise

    await db.refresh(new_star)
    return new_star


async def get_star(
    db: AsyncSession,
    star_id: int
) -> Star | None:
    result = await db.execute(
        select(Star).where(Star.id == star_id)
    )
    return result.scalar_one_or_none()


async def get_stars(
    db: AsyncSession
) -> list[Star]:
    result = await db.execute(
        select(Star).order_by(Star.name)
    )
    return list(result.scalars().all())


async def update_star(
    db: AsyncSession,
    star_id: int,
    star: StarUpdate
) -> Star | None:
    db_star = await get_star(db, star_id)

    if db_star is None:
        return None

    update_data = star.model_dump(exclude_unset=True)

    if "name" in update_data and update_data["name"] is None:
        raise ValueError("Star name cannot be null")

    for field, value in update_data.items():
        setattr(db_star, field, value)

    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise

    await db.refresh(db_star)
    return db_star


async def delete_star(
    db: AsyncSession,
    star_id: int
) -> Star | None:
    db_star = await get_star(db, star_id)

    if db_star is None:
        return None

    try:
        await db.delete(db_star)
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise

    return db_star


async def create_director(
    db: AsyncSession,
    director: DirectorCreate
) -> Director:
    new_director = Director(**director.model_dump())
    db.add(new_director)

    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise

    await db.refresh(new_director)
    return new_director


async def get_director(
    db: AsyncSession,
    director_id: int
) -> Director | None:
    result = await db.execute(
        select(Director).where(Director.id == director_id)
    )
    return result.scalar_one_or_none()


async def get_directors(
    db: AsyncSession
) -> list[Director]:
    result = await db.execute(
        select(Director).order_by(Director.name)
    )
    return list(result.scalars().all())


async def update_director(
    db: AsyncSession,
    director_id: int,
    director: DirectorUpdate
) -> Director | None:
    db_director = await get_director(db, director_id)

    if db_director is None:
        return None

    update_data = director.model_dump(exclude_unset=True)

    if "name" in update_data and update_data["name"] is None:
        raise ValueError("Director name cannot be null")

    for field, value in update_data.items():
        setattr(db_director, field, value)

    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise

    await db.refresh(db_director)
    return db_director


async def delete_director(
    db: AsyncSession,
    director_id: int
) -> Director | None:
    db_director = await get_director(db, director_id)

    if db_director is None:
        return None

    try:
        await db.delete(db_director)
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise

    return db_director

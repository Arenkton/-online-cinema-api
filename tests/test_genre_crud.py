import pytest
from sqlalchemy.exc import IntegrityError

from src.crud import (
    create_genre,
    get_genre,
    get_genres,
    update_genre,
    delete_genre,
)
from src.schemas import GenreCreate, GenreUpdate


pytestmark = pytest.mark.asyncio


# 1. Створення жанру
async def test_create_genre(db_session):
    genre_data = GenreCreate(name="Action")

    genre = await create_genre(db_session, genre_data)

    assert genre.id is not None
    assert genre.name == "Action"


# 2. Отримання жанру за ID
async def test_get_genre(db_session):
    created = await create_genre(
        db_session,
        GenreCreate(name="Drama")
    )

    genre = await get_genre(db_session, created.id)

    assert genre is not None
    assert genre.id == created.id
    assert genre.name == "Drama"


# 3. Отримання неіснуючого жанру
async def test_get_genre_not_found(db_session):
    genre = await get_genre(db_session, 999)

    assert genre is None


# 4. Отримання списку жанрів
async def test_get_genres(db_session):
    await create_genre(
        db_session,
        GenreCreate(name="Drama")
    )
    await create_genre(
        db_session,
        GenreCreate(name="Action")
    )

    genres = await get_genres(db_session)

    assert len(genres) == 2
    assert [genre.name for genre in genres] == [
        "Action",
        "Drama",
    ]


# 5. Оновлення жанру
async def test_update_genre(db_session):
    created = await create_genre(
        db_session,
        GenreCreate(name="Comedy")
    )

    update_data = GenreUpdate(name="Horror")

    updated = await update_genre(
        db_session,
        created.id,
        update_data
    )

    assert updated is not None
    assert updated.name == "Horror"

    saved = await get_genre(db_session, created.id)
    assert saved.name == "Horror"


# 6. Оновлення неіснуючого жанру
async def test_update_genre_not_found(db_session):
    update_data = GenreUpdate(name="Thriller")

    result = await update_genre(
        db_session,
        999,
        update_data
    )

    assert result is None


# 7. Видалення жанру
async def test_delete_genre(db_session):
    created = await create_genre(
        db_session,
        GenreCreate(name="Fantasy")
    )

    deleted = await delete_genre(
        db_session,
        created.id
    )

    assert deleted is not None
    assert deleted.id == created.id

    genre = await get_genre(db_session, created.id)
    assert genre is None


# 8. Видалення неіснуючого жанру
async def test_delete_genre_not_found(db_session):
    result = await delete_genre(db_session, 999)

    assert result is None


# 9. Спроба створити дублікат
async def test_create_duplicate_genre(db_session):
    await create_genre(
        db_session,
        GenreCreate(name="Action")
    )

    with pytest.raises(IntegrityError):
        await create_genre(
            db_session,
            GenreCreate(name="Action")
        )

    genres = await get_genres(db_session)

    assert len(genres) == 1


# 10. Оновлення без переданих полів
async def test_update_genre_without_changes(db_session):
    created = await create_genre(
        db_session,
        GenreCreate(name="Sci-Fi")
    )

    updated = await update_genre(
        db_session,
        created.id,
        GenreUpdate()
    )

    assert updated is not None
    assert updated.name == "Sci-Fi"

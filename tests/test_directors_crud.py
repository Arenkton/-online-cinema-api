import pytest
from sqlalchemy.exc import IntegrityError

from src.crud import (
    create_director, get_director, get_directors, update_director, delete_director
)
from src.schemas import DirectorCreate, DirectorUpdate

pytestmark = pytest.mark.asyncio


async def test_create_director(db_session):
    created = await create_director(db_session, DirectorCreate(name="Alpha"))
    assert created.id is not None
    assert created.name == "Alpha"
    stored = await get_director(db_session, created.id)
    assert stored is not None and stored.name == "Alpha"


async def test_get_director_missing(db_session):
    assert await get_director(db_session, 999) is None


async def test_get_directors_sorted(db_session):
    await create_director(db_session, DirectorCreate(name="Zeta"))
    await create_director(db_session, DirectorCreate(name="Alpha"))
    results = await get_directors(db_session)
    assert [item.name for item in results] == ["Alpha", "Zeta"]


async def test_update_director(db_session):
    created = await create_director(db_session, DirectorCreate(name="Old"))
    updated = await update_director(
        db_session, created.id, DirectorUpdate(name="New")
    )
    assert updated is not None and updated.name == "New"
    stored = await get_director(db_session, created.id)
    assert stored.name == "New"


async def test_update_director_missing(db_session):
    assert await update_director(
        db_session, 999, DirectorUpdate(name="New")
    ) is None


async def test_update_director_empty_payload(db_session):
    created = await create_director(db_session, DirectorCreate(name="Keep"))
    updated = await update_director(db_session, created.id, DirectorUpdate())
    assert updated is not None and updated.name == "Keep"


async def test_update_director_null_name_rejected(db_session):
    created = await create_director(db_session, DirectorCreate(name="Keep"))
    with pytest.raises(ValueError):
        await update_director(
            db_session, created.id, DirectorUpdate(name=None)
        )
    stored = await get_director(db_session, created.id)
    assert stored.name == "Keep"


async def test_create_director_duplicate_name(db_session):
    await create_director(db_session, DirectorCreate(name="Same"))
    with pytest.raises(IntegrityError):
        await create_director(db_session, DirectorCreate(name="Same"))
    # The CRUD function should have rolled back, leaving session reusable.
    assert len(await get_directors(db_session)) == 1


async def test_update_director_duplicate_name(db_session):
    await create_director(db_session, DirectorCreate(name="First"))
    second = await create_director(db_session, DirectorCreate(name="Second"))
    second_id = second.id
    with pytest.raises(IntegrityError):
        await update_director(
            db_session, second_id, DirectorUpdate(name="First")
        )
    stored = await get_director(db_session, second_id)
    assert stored.name == "Second"


async def test_delete_director(db_session):
    created = await create_director(db_session, DirectorCreate(name="Delete me"))
    deleted = await delete_director(db_session, created.id)
    assert deleted is not None and deleted.id == created.id
    assert await get_director(db_session, created.id) is None


async def test_delete_director_missing(db_session):
    assert await delete_director(db_session, 999) is None

import pytest
from sqlalchemy.exc import IntegrityError

from src.crud import (
    create_star, get_star, get_stars, update_star, delete_star
)
from src.schemas import StarCreate, StarUpdate

pytestmark = pytest.mark.asyncio


async def test_create_star(db_session):
    created = await create_star(db_session, StarCreate(name="Alpha"))
    assert created.id is not None
    assert created.name == "Alpha"
    stored = await get_star(db_session, created.id)
    assert stored is not None and stored.name == "Alpha"


async def test_get_star_missing(db_session):
    assert await get_star(db_session, 999) is None


async def test_get_stars_sorted(db_session):
    await create_star(db_session, StarCreate(name="Zeta"))
    await create_star(db_session, StarCreate(name="Alpha"))
    results = await get_stars(db_session)
    assert [item.name for item in results] == ["Alpha", "Zeta"]


async def test_update_star(db_session):
    created = await create_star(db_session, StarCreate(name="Old"))
    updated = await update_star(
        db_session, created.id, StarUpdate(name="New")
    )
    assert updated is not None and updated.name == "New"
    stored = await get_star(db_session, created.id)
    assert stored.name == "New"


async def test_update_star_missing(db_session):
    assert await update_star(
        db_session, 999, StarUpdate(name="New")
    ) is None


async def test_update_star_empty_payload(db_session):
    created = await create_star(db_session, StarCreate(name="Keep"))
    updated = await update_star(db_session, created.id, StarUpdate())
    assert updated is not None and updated.name == "Keep"


async def test_update_star_null_name_rejected(db_session):
    created = await create_star(db_session, StarCreate(name="Keep"))
    with pytest.raises(ValueError):
        await update_star(
            db_session, created.id, StarUpdate(name=None)
        )
    stored = await get_star(db_session, created.id)
    assert stored.name == "Keep"


async def test_create_star_duplicate_name(db_session):
    await create_star(db_session, StarCreate(name="Same"))
    with pytest.raises(IntegrityError):
        await create_star(db_session, StarCreate(name="Same"))
    # The CRUD function should have rolled back, leaving session reusable.
    assert len(await get_stars(db_session)) == 1


async def test_update_star_duplicate_name(db_session):
    await create_star(db_session, StarCreate(name="First"))
    second = await create_star(db_session, StarCreate(name="Second"))
    second_id = second.id
    with pytest.raises(IntegrityError):
        await update_star(
            db_session, second_id, StarUpdate(name="First")
        )
    stored = await get_star(db_session, second_id)
    assert stored.name == "Second"


async def test_delete_star(db_session):
    created = await create_star(db_session, StarCreate(name="Delete me"))
    deleted = await delete_star(db_session, created.id)
    assert deleted is not None and deleted.id == created.id
    assert await get_star(db_session, created.id) is None


async def test_delete_star_missing(db_session):
    assert await delete_star(db_session, 999) is None

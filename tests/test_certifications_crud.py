import pytest
from sqlalchemy.exc import IntegrityError

from src.crud import (
    create_certification,
    get_certification,
    get_certifications,
    update_certification,
)
from src.schemas import CertificationCreate, CertificationUpdate

pytestmark = pytest.mark.asyncio


async def test_create_certification(db_session):
    created = await create_certification(
        db_session, CertificationCreate(name="PG-13")
    )
    assert created.id is not None
    assert created.name == "PG-13"
    assert (await get_certification(db_session, created.id)).name == "PG-13"


async def test_get_certification_missing(db_session):
    assert await get_certification(db_session, 999) is None


async def test_get_certifications_sorted_by_id(db_session):
    first = await create_certification(
        db_session, CertificationCreate(name="R")
    )
    second = await create_certification(
        db_session, CertificationCreate(name="PG")
    )
    results = await get_certifications(db_session)
    assert [item.id for item in results] == [first.id, second.id]


async def test_update_certification(db_session):
    created = await create_certification(
        db_session, CertificationCreate(name="PG")
    )
    updated = await update_certification(
        db_session, created.id, CertificationUpdate(name="PG-13")
    )
    assert updated is not None and updated.name == "PG-13"
    assert (await get_certification(db_session, created.id)).name == "PG-13"


async def test_update_certification_missing(db_session):
    assert await update_certification(
        db_session, 999, CertificationUpdate(name="R")
    ) is None


async def test_update_certification_without_changes(db_session):
    created = await create_certification(
        db_session, CertificationCreate(name="G")
    )
    updated = await update_certification(
        db_session, created.id, CertificationUpdate()
    )
    assert updated is not None and updated.name == "G"


async def test_create_certification_duplicate(db_session):
    await create_certification(db_session, CertificationCreate(name="R"))
    with pytest.raises(IntegrityError):
        await create_certification(db_session, CertificationCreate(name="R"))
    assert len(await get_certifications(db_session)) == 1


async def test_update_certification_duplicate(db_session):
    await create_certification(db_session, CertificationCreate(name="R"))
    second = await create_certification(
        db_session, CertificationCreate(name="PG")
    )
    second_id = second.id
    with pytest.raises(IntegrityError):
        await update_certification(
            db_session, second_id, CertificationUpdate(name="R")
        )
    # update_certification must roll back after a failed commit.
    assert (await get_certification(db_session, second_id)).name == "PG"

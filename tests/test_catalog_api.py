"""HTTP integration tests for reference catalog endpoints."""

import pytest


pytestmark = pytest.mark.asyncio


@pytest.mark.parametrize(
    "resource",
    ["genres", "stars", "directors", "certifications"],
)
async def test_catalog_create_list_get_patch(api_client, resource):
    created = await api_client.post(
        f"/{resource}/", json={"name": "Initial Name"}
    )
    assert created.status_code == 201, created.text
    item_id = created.json()["id"]
    assert created.json()["name"] == "Initial Name"

    listing = await api_client.get(f"/{resource}/")
    assert listing.status_code == 200, listing.text
    assert any(item["id"] == item_id for item in listing.json())

    detail = await api_client.get(f"/{resource}/{item_id}")
    assert detail.status_code == 200, detail.text
    assert detail.json()["name"] == "Initial Name"

    updated = await api_client.patch(
        f"/{resource}/{item_id}", json={"name": "Updated Name"}
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["name"] == "Updated Name"


@pytest.mark.parametrize(
    "resource",
    ["genres", "stars", "directors", "certifications"],
)
async def test_catalog_get_missing(api_client, resource):
    response = await api_client.get(f"/{resource}/999999")
    assert response.status_code == 404


@pytest.mark.parametrize(
    "resource",
    ["genres", "stars", "directors", "certifications"],
)
async def test_catalog_patch_null_name_rejected(api_client, resource):
    created = await api_client.post(
        f"/{resource}/", json={"name": "Existing Name"}
    )
    assert created.status_code == 201, created.text

    response = await api_client.patch(
        f"/{resource}/{created.json()['id']}",
        json={"name": None},
    )
    assert response.status_code == 422


@pytest.mark.parametrize(
    "resource", ["genres", "stars", "directors"]
)
async def test_catalog_delete(api_client, resource):
    created = await api_client.post(
        f"/{resource}/", json={"name": "Delete Me"}
    )
    assert created.status_code == 201, created.text
    item_id = created.json()["id"]

    deleted = await api_client.delete(f"/{resource}/{item_id}")
    assert deleted.status_code == 204, deleted.text
    assert deleted.content == b""

    missing = await api_client.get(f"/{resource}/{item_id}")
    assert missing.status_code == 404


@pytest.mark.parametrize(
    "resource", ["genres", "stars", "directors"]
)
async def test_catalog_delete_missing(api_client, resource):
    response = await api_client.delete(f"/{resource}/999999")
    assert response.status_code == 404


@pytest.mark.parametrize(
    "resource",
    ["genres", "stars", "directors", "certifications"],
)
async def test_catalog_duplicate_name_returns_conflict(
    api_client, resource
):
    first = await api_client.post(
        f"/{resource}/", json={"name": "Unique Name"}
    )
    assert first.status_code == 201, first.text

    second = await api_client.post(
        f"/{resource}/", json={"name": "Unique Name"}
    )
    assert second.status_code == 409, second.text

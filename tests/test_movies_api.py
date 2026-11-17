"""HTTP integration tests for /movies/.

Requires the ``api_client`` fixture appended to the existing tests/conftest.py.
The fixture overrides get_db with the existing in-memory db_session.
"""

from uuid import UUID

import pytest


pytestmark = pytest.mark.asyncio


async def create_certification(api_client, name="PG-13"):
    response = await api_client.post(
        "/certifications/", json={"name": name}
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


async def create_related(api_client, resource, name):
    response = await api_client.post(
        f"/{resource}/", json={"name": name}
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


def movie_payload(certification_id, **overrides):
    """All required MovieCreate fields; relationships are optional."""
    payload = {
        "name": "Inception",
        "year": 2010,
        "time": 148,
        "imdb": 8.8,
        "votes": 2500000,
        "description": "A science-fiction thriller",
        "price": "9.99",
        "certification_id": certification_id,
    }
    payload.update(overrides)
    return payload


async def create_movie(api_client, certification_id, **overrides):
    response = await api_client.post(
        "/movies/",
        json=movie_payload(certification_id, **overrides),
    )
    assert response.status_code == 201, response.text
    return response.json()


async def test_get_movies_empty(api_client):
    response = await api_client.get("/movies/")
    assert response.status_code == 200
    assert response.json() == []


async def test_create_movie_without_relationships(api_client):
    certification_id = await create_certification(api_client)
    response = await api_client.post(
        "/movies/", json=movie_payload(certification_id)
    )

    assert response.status_code == 201, response.text
    body = response.json()
    assert isinstance(body["id"], int)
    assert UUID(body["uuid"])
    assert body["name"] == "Inception"
    assert body["certification_id"] == certification_id
    assert str(body["price"]) == "9.99"
    assert body["genres"] == []
    assert body["stars"] == []
    assert body["directors"] == []


async def test_create_and_read_movie_with_relationships(api_client):
    certification_id = await create_certification(api_client)
    genre_id = await create_related(api_client, "genres", "Sci-Fi")
    star_id = await create_related(api_client, "stars", "Actor One")
    director_id = await create_related(
        api_client, "directors", "Director One"
    )

    created = await create_movie(
        api_client,
        certification_id,
        genre_ids=[genre_id],
        star_ids=[star_id],
        director_ids=[director_id],
    )
    response = await api_client.get(f"/movies/{created['id']}")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["id"] == created["id"]
    assert [(g["id"], g["name"]) for g in body["genres"]] == [
        (genre_id, "Sci-Fi")
    ]
    assert [(s["id"], s["name"]) for s in body["stars"]] == [
        (star_id, "Actor One")
    ]
    assert [(d["id"], d["name"]) for d in body["directors"]] == [
        (director_id, "Director One")
    ]


async def test_list_movies_with_relationships(api_client):
    certification_id = await create_certification(api_client)
    genre_id = await create_related(api_client, "genres", "Sci-Fi")
    first = await create_movie(
        api_client, certification_id, genre_ids=[genre_id]
    )
    second = await create_movie(
        api_client, certification_id, name="Interstellar"
    )

    response = await api_client.get("/movies/")

    assert response.status_code == 200, response.text
    movies = {item["id"]: item for item in response.json()}
    assert set(movies) == {first["id"], second["id"]}
    assert [g["name"] for g in movies[first["id"]]["genres"]] == [
        "Sci-Fi"
    ]
    assert movies[second["id"]]["genres"] == []


async def test_get_movie_not_found(api_client):
    response = await api_client.get("/movies/999999")
    assert response.status_code == 404
    assert response.json()["detail"] == "Movie not found"


@pytest.mark.parametrize(
    "invalid_field, invalid_value",
    [
        ("name", ""),
        ("year", 0),
        ("time", 0),
        ("imdb", 10.5),
        ("votes", -1),
        ("price", "-0.01"),
    ],
)
async def test_create_movie_invalid_fields(
    api_client, invalid_field, invalid_value
):
    certification_id = await create_certification(api_client)
    payload = movie_payload(
        certification_id, **{invalid_field: invalid_value}
    )

    response = await api_client.post("/movies/", json=payload)
    assert response.status_code == 422, response.text


async def test_create_movie_missing_required_field(api_client):
    certification_id = await create_certification(api_client)
    payload = movie_payload(certification_id)
    del payload["name"]

    response = await api_client.post("/movies/", json=payload)
    assert response.status_code == 422


@pytest.mark.parametrize(
    "field", ["genre_ids", "star_ids", "director_ids"]
)
async def test_create_movie_unknown_related_id(api_client, field):
    certification_id = await create_certification(api_client)
    payload = movie_payload(certification_id, **{field: [999999]})

    response = await api_client.post("/movies/", json=payload)

    assert response.status_code == 422, response.text
    assert "do not exist" in response.json()["detail"]
    # An invalid request must not create a movie.
    listing = await api_client.get("/movies/")
    assert listing.status_code == 200
    assert listing.json() == []


async def test_patch_movie_scalar_fields(api_client):
    certification_id = await create_certification(api_client)
    created = await create_movie(api_client, certification_id)

    response = await api_client.patch(
        f"/movies/{created['id']}",
        json={"name": "Inception: Updated", "price": "12.50"},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["name"] == "Inception: Updated"
    assert str(body["price"]) == "12.50"
    assert body["year"] == 2010


async def test_patch_name_preserves_relationships(api_client):
    certification_id = await create_certification(api_client)
    genre_id = await create_related(api_client, "genres", "Sci-Fi")
    created = await create_movie(
        api_client, certification_id, genre_ids=[genre_id]
    )

    response = await api_client.patch(
        f"/movies/{created['id']}", json={"name": "New Name"}
    )

    assert response.status_code == 200, response.text
    assert [g["id"] for g in response.json()["genres"]] == [genre_id]


async def test_patch_replaces_all_relationships(api_client):
    certification_id = await create_certification(api_client)
    old_genre = await create_related(api_client, "genres", "Action")
    new_genre = await create_related(api_client, "genres", "Sci-Fi")
    old_star = await create_related(api_client, "stars", "Actor One")
    new_star = await create_related(api_client, "stars", "Actor Two")
    old_director = await create_related(
        api_client, "directors", "Director One"
    )
    new_director = await create_related(
        api_client, "directors", "Director Two"
    )
    created = await create_movie(
        api_client,
        certification_id,
        genre_ids=[old_genre],
        star_ids=[old_star],
        director_ids=[old_director],
    )

    response = await api_client.patch(
        f"/movies/{created['id']}",
        json={
            "genre_ids": [new_genre],
            "star_ids": [new_star],
            "director_ids": [new_director],
        },
    )

    assert response.status_code == 200, response.text
    updated = response.json()
    assert [g["id"] for g in updated["genres"]] == [new_genre]
    assert [s["id"] for s in updated["stars"]] == [new_star]
    assert [d["id"] for d in updated["directors"]] == [
        new_director
    ]


async def test_patch_empty_lists_clear_relationships(api_client):
    certification_id = await create_certification(api_client)
    genre_id = await create_related(api_client, "genres", "Sci-Fi")
    star_id = await create_related(api_client, "stars", "Actor One")
    director_id = await create_related(
        api_client, "directors", "Director One"
    )
    created = await create_movie(
        api_client,
        certification_id,
        genre_ids=[genre_id],
        star_ids=[star_id],
        director_ids=[director_id],
    )

    response = await api_client.patch(
        f"/movies/{created['id']}",
        json={
            "genre_ids": [],
            "star_ids": [],
            "director_ids": [],
        },
    )

    assert response.status_code == 200, response.text
    assert response.json()["genres"] == []
    assert response.json()["stars"] == []
    assert response.json()["directors"] == []

    # Deleting an association must not delete the related objects.
    assert (await api_client.get(f"/genres/{genre_id}")).status_code == 200
    assert (await api_client.get(f"/stars/{star_id}")).status_code == 200
    assert (
        await api_client.get(f"/directors/{director_id}")
    ).status_code == 200


@pytest.mark.parametrize(
    "field", ["genre_ids", "star_ids", "director_ids"]
)
async def test_patch_unknown_related_id_rolls_back(api_client, field):
    certification_id = await create_certification(api_client)
    created = await create_movie(api_client, certification_id)

    response = await api_client.patch(
        f"/movies/{created['id']}",
        json={"name": "Should Not Persist", field: [999999]},
    )

    assert response.status_code == 422, response.text
    stored = await api_client.get(f"/movies/{created['id']}")
    assert stored.status_code == 200
    assert stored.json()["name"] == "Inception"


async def test_patch_null_name_rejected(api_client):
    certification_id = await create_certification(api_client)
    created = await create_movie(api_client, certification_id)

    response = await api_client.patch(
        f"/movies/{created['id']}", json={"name": None}
    )

    assert response.status_code == 422
    stored = await api_client.get(f"/movies/{created['id']}")
    assert stored.json()["name"] == "Inception"


@pytest.mark.parametrize(
    "field", ["genre_ids", "star_ids", "director_ids"]
)
async def test_patch_null_relationship_rejected(api_client, field):
    certification_id = await create_certification(api_client)
    created = await create_movie(api_client, certification_id)

    response = await api_client.patch(
        f"/movies/{created['id']}", json={field: None}
    )
    assert response.status_code == 422


async def test_patch_movie_not_found(api_client):
    response = await api_client.patch(
        "/movies/999999", json={"name": "Missing"}
    )
    assert response.status_code == 404


async def test_delete_movie(api_client):
    certification_id = await create_certification(api_client)
    created = await create_movie(api_client, certification_id)

    response = await api_client.delete(f"/movies/{created['id']}")

    assert response.status_code == 204, response.text
    assert response.content == b""
    assert (
        await api_client.get(f"/movies/{created['id']}")
    ).status_code == 404


async def test_delete_movie_not_found(api_client):
    response = await api_client.delete("/movies/999999")
    assert response.status_code == 404

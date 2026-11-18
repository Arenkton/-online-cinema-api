from decimal import Decimal

import pytest
import pytest_asyncio

from src.jwt_service import create_jwt_token
from src.models import (
    Cart,
    CartItem,
    Certification,
    Movie,
    User,
    UserGroup,
    UserGroupEnum,
)


TEST_SECRET = "test-secret-key-for-jwt-unit-tests-123456789"


@pytest.fixture(autouse=True)
def jwt_secret(monkeypatch):
    monkeypatch.setenv("JWT_SECRET_KEY", TEST_SECRET)


@pytest_asyncio.fixture
async def cart_data(db_session):
    group = UserGroup(name=UserGroupEnum.USER.value)
    certification = Certification(name="PG-13")

    first_user = User(
        email="first-cart@example.com",
        hashed_password="test-password-hash",
        is_active=True,
        group=group,
    )

    second_user = User(
        email="second-cart@example.com",
        hashed_password="test-password-hash",
        is_active=True,
        group=group,
    )

    first_movie = Movie(
        name="First Movie",
        year=2024,
        time=120,
        imdb=8.5,
        votes=1000,
        description="First test movie",
        price=Decimal("9.99"),
        certification=certification,
    )

    second_movie = Movie(
        name="Second Movie",
        year=2025,
        time=150,
        imdb=9.0,
        votes=2000,
        description="Second test movie",
        price=Decimal("12.50"),
        certification=certification,
    )

    db_session.add_all([
        first_user,
        second_user,
        first_movie,
        second_movie,
    ])

    await db_session.commit()

    return {
        "user1": first_user.id,
        "user2": second_user.id,
        "movie1": first_movie.id,
        "movie2": second_movie.id,
    }


def auth_headers(user_id, token_type="access"):
    token = create_jwt_token(user_id, token_type)

    return {
        "Authorization": f"Bearer {token}"
    }


async def create_cart_with_movies(
    db_session,
    user_id,
    movie_ids,
):
    cart = Cart(user_id=user_id)

    db_session.add(cart)
    await db_session.flush()

    for movie_id in movie_ids:
        db_session.add(
            CartItem(
                cart_id=cart.id,
                movie_id=movie_id,
            )
        )

    await db_session.commit()

    return cart.id


@pytest.mark.asyncio
async def test_get_cart_without_existing_cart(
    api_client,
    cart_data,
):
    response = await api_client.get(
        "/cart",
        headers=auth_headers(cart_data["user1"]),
    )

    assert response.status_code == 200
    assert response.json() == {
        "items": [],
        "total_price": "0.00",
    }


@pytest.mark.asyncio
async def test_get_existing_empty_cart(
    api_client,
    db_session,
    cart_data,
):
    await create_cart_with_movies(
        db_session,
        cart_data["user1"],
        [],
    )

    response = await api_client.get(
        "/cart",
        headers=auth_headers(cart_data["user1"]),
    )

    assert response.status_code == 200
    assert response.json()["items"] == []
    assert Decimal(
        response.json()["total_price"]
    ) == Decimal("0.00")


@pytest.mark.asyncio
async def test_get_cart_with_one_movie(
    api_client,
    db_session,
    cart_data,
):
    await create_cart_with_movies(
        db_session,
        cart_data["user1"],
        [cart_data["movie1"]],
    )

    response = await api_client.get(
        "/cart",
        headers=auth_headers(cart_data["user1"]),
    )

    assert response.status_code == 200

    data = response.json()

    assert len(data["items"]) == 1

    item = data["items"][0]

    assert item["id"] is not None
    assert item["movie_id"] == cart_data["movie1"]
    assert item["name"] == "First Movie"
    assert Decimal(item["price"]) == Decimal("9.99")
    assert item["added_at"] is not None

    assert Decimal(
        data["total_price"]
    ) == Decimal("9.99")


@pytest.mark.asyncio
async def test_get_cart_with_multiple_movies(
    api_client,
    db_session,
    cart_data,
):
    await create_cart_with_movies(
        db_session,
        cart_data["user1"],
        [
            cart_data["movie1"],
            cart_data["movie2"],
        ],
    )

    response = await api_client.get(
        "/cart",
        headers=auth_headers(cart_data["user1"]),
    )

    assert response.status_code == 200

    data = response.json()

    assert len(data["items"]) == 2

    movie_ids = [
        item["movie_id"]
        for item in data["items"]
    ]

    assert movie_ids == [
        cart_data["movie1"],
        cart_data["movie2"],
    ]

    assert Decimal(
        data["total_price"]
    ) == Decimal("22.49")


@pytest.mark.asyncio
async def test_users_have_separate_carts(
    api_client,
    db_session,
    cart_data,
):
    await create_cart_with_movies(
        db_session,
        cart_data["user1"],
        [cart_data["movie1"]],
    )

    await create_cart_with_movies(
        db_session,
        cart_data["user2"],
        [cart_data["movie2"]],
    )

    first_response = await api_client.get(
        "/cart",
        headers=auth_headers(cart_data["user1"]),
    )

    second_response = await api_client.get(
        "/cart",
        headers=auth_headers(cart_data["user2"]),
    )

    assert first_response.status_code == 200
    assert second_response.status_code == 200

    first_data = first_response.json()
    second_data = second_response.json()

    assert [
        item["movie_id"]
        for item in first_data["items"]
    ] == [cart_data["movie1"]]

    assert [
        item["movie_id"]
        for item in second_data["items"]
    ] == [cart_data["movie2"]]

    assert Decimal(
        first_data["total_price"]
    ) == Decimal("9.99")

    assert Decimal(
        second_data["total_price"]
    ) == Decimal("12.50")


@pytest.mark.asyncio
async def test_get_cart_without_auth(api_client):
    response = await api_client.get("/cart")

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_get_cart_invalid_token(api_client):
    response = await api_client.get(
        "/cart",
        headers={
            "Authorization": "Bearer invalid.jwt.token"
        },
    )

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_refresh_token_cannot_access_cart(
    api_client,
    cart_data,
):
    response = await api_client.get(
        "/cart",
        headers=auth_headers(
            cart_data["user1"],
            token_type="refresh",
        ),
    )

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_inactive_user_cannot_access_cart(
    api_client,
    db_session,
    cart_data,
):
    user = await db_session.get(
        User,
        cart_data["user1"],
    )

    user.is_active = False
    await db_session.commit()

    response = await api_client.get(
        "/cart",
        headers=auth_headers(cart_data["user1"]),
    )

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_cart_uses_current_movie_price(
    api_client,
    db_session,
    cart_data,
):
    await create_cart_with_movies(
        db_session,
        cart_data["user1"],
        [cart_data["movie1"]],
    )

    movie = await db_session.get(
        Movie,
        cart_data["movie1"],
    )

    movie.price = Decimal("15.99")
    await db_session.commit()

    response = await api_client.get(
        "/cart",
        headers=auth_headers(cart_data["user1"]),
    )

    assert response.status_code == 200

    data = response.json()

    assert Decimal(
        data["items"][0]["price"]
    ) == Decimal("15.99")

    assert Decimal(
        data["total_price"]
    ) == Decimal("15.99")

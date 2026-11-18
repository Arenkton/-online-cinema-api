from decimal import Decimal

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from src.jwt_service import create_jwt_token
from src.models import (
    Cart,
    CartItem,
    Certification,
    Movie,
    Order,
    OrderItem,
    User,
    UserGroup,
    UserGroupEnum,
)


TEST_SECRET = "test-secret-key-for-jwt-unit-tests-123456789"


@pytest.fixture(autouse=True)
def jwt_secret(monkeypatch):
    monkeypatch.setenv("JWT_SECRET_KEY", TEST_SECRET)


@pytest_asyncio.fixture
async def order_data(db_session):
    group = UserGroup(name=UserGroupEnum.USER.value)
    certification = Certification(name="PG-13")

    first_user = User(
        email="orders-first@example.com",
        hashed_password="test-password-hash",
        is_active=True,
        group=group,
    )

    second_user = User(
        email="orders-second@example.com",
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
        description="First order test movie",
        price=Decimal("9.99"),
        certification=certification,
    )

    second_movie = Movie(
        name="Second Movie",
        year=2025,
        time=150,
        imdb=9.0,
        votes=2000,
        description="Second order test movie",
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
    token = create_jwt_token(
        user_id,
        token_type,
    )

    return {
        "Authorization": f"Bearer {token}"
    }


async def add_movies_to_cart(
    api_client,
    user_id,
    movie_ids,
):
    for movie_id in movie_ids:
        response = await api_client.post(
            "/cart/items",
            json={"movie_id": movie_id},
            headers=auth_headers(user_id),
        )

        assert response.status_code == 201


@pytest.mark.asyncio
async def test_create_order_success(
    api_client,
    db_session,
    order_data,
):
    user_id = order_data["user1"]

    await add_movies_to_cart(
        api_client,
        user_id,
        [
            order_data["movie1"],
            order_data["movie2"],
        ],
    )

    response = await api_client.post(
        "/orders",
        headers=auth_headers(user_id),
    )

    assert response.status_code == 201

    data = response.json()

    assert data["id"] is not None
    assert data["user_id"] == user_id
    assert data["status"] == "pending"
    assert data["created_at"] is not None

    assert Decimal(
        data["total_amount"]
    ) == Decimal("22.49")

    assert len(data["items"]) == 2

    items_by_movie = {
        item["movie_id"]: item
        for item in data["items"]
    }

    assert Decimal(
        items_by_movie[order_data["movie1"]]["price_at_order"]
    ) == Decimal("9.99")

    assert Decimal(
        items_by_movie[order_data["movie2"]]["price_at_order"]
    ) == Decimal("12.50")

    # Check saved order and its items.
    result = await db_session.execute(
        select(Order)
        .options(selectinload(Order.items))
        .where(Order.id == data["id"])
    )

    saved_order = result.scalar_one()

    assert saved_order.user_id == user_id
    assert saved_order.status == "pending"
    assert saved_order.total_amount == Decimal("22.49")
    assert len(saved_order.items) == 2

    # The shopping cart must be empty after checkout.
    cart_response = await api_client.get(
        "/cart",
        headers=auth_headers(user_id),
    )

    assert cart_response.status_code == 200
    assert cart_response.json()["items"] == []
    assert Decimal(
        cart_response.json()["total_price"]
    ) == Decimal("0.00")


@pytest.mark.asyncio
async def test_create_order_without_cart(
    api_client,
    db_session,
    order_data,
):
    response = await api_client.post(
        "/orders",
        headers=auth_headers(order_data["user1"]),
    )

    assert response.status_code == 400
    assert response.json()["detail"] == (
        "Shopping cart is empty"
    )

    result = await db_session.execute(select(Order))

    assert result.scalars().all() == []


@pytest.mark.asyncio
async def test_create_order_with_empty_cart(
    api_client,
    db_session,
    order_data,
):
    cart = Cart(user_id=order_data["user1"])

    db_session.add(cart)
    await db_session.commit()

    response = await api_client.post(
        "/orders",
        headers=auth_headers(order_data["user1"]),
    )

    assert response.status_code == 400


@pytest.mark.asyncio
async def test_cannot_create_order_twice_from_same_cart(
    api_client,
    db_session,
    order_data,
):
    user_id = order_data["user1"]

    await add_movies_to_cart(
        api_client,
        user_id,
        [order_data["movie1"]],
    )

    first_response = await api_client.post(
        "/orders",
        headers=auth_headers(user_id),
    )

    second_response = await api_client.post(
        "/orders",
        headers=auth_headers(user_id),
    )

    assert first_response.status_code == 201
    assert second_response.status_code == 400

    result = await db_session.execute(
        select(Order).where(Order.user_id == user_id)
    )

    assert len(result.scalars().all()) == 1


@pytest.mark.asyncio
async def test_create_order_without_auth(api_client):
    response = await api_client.post("/orders")

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_create_order_invalid_token(api_client):
    response = await api_client.post(
        "/orders",
        headers={
            "Authorization": "Bearer invalid.jwt.token"
        },
    )

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_refresh_token_cannot_create_order(
    api_client,
    order_data,
):
    response = await api_client.post(
        "/orders",
        headers=auth_headers(
            order_data["user1"],
            token_type="refresh",
        ),
    )

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_inactive_user_cannot_create_order(
    api_client,
    db_session,
    order_data,
):
    user_id = order_data["user1"]

    await add_movies_to_cart(
        api_client,
        user_id,
        [order_data["movie1"]],
    )

    user = await db_session.get(User, user_id)
    user.is_active = False

    await db_session.commit()

    response = await api_client.post(
        "/orders",
        headers=auth_headers(user_id),
    )

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_cannot_order_another_users_cart(
    api_client,
    order_data,
):
    await add_movies_to_cart(
        api_client,
        order_data["user2"],
        [order_data["movie1"]],
    )

    # User 1 has an empty cart.
    response = await api_client.post(
        "/orders",
        headers=auth_headers(order_data["user1"]),
    )

    assert response.status_code == 400

    # User 2's cart must remain unchanged.
    cart_response = await api_client.get(
        "/cart",
        headers=auth_headers(order_data["user2"]),
    )

    assert cart_response.status_code == 200
    assert len(cart_response.json()["items"]) == 1


@pytest.mark.asyncio
async def test_users_create_separate_orders(
    api_client,
    db_session,
    order_data,
):
    await add_movies_to_cart(
        api_client,
        order_data["user1"],
        [order_data["movie1"]],
    )

    await add_movies_to_cart(
        api_client,
        order_data["user2"],
        [order_data["movie2"]],
    )

    first_response = await api_client.post(
        "/orders",
        headers=auth_headers(order_data["user1"]),
    )

    second_response = await api_client.post(
        "/orders",
        headers=auth_headers(order_data["user2"]),
    )

    assert first_response.status_code == 201
    assert second_response.status_code == 201

    assert first_response.json()["user_id"] == (
        order_data["user1"]
    )

    assert second_response.json()["user_id"] == (
        order_data["user2"]
    )

    assert first_response.json()["id"] != (
        second_response.json()["id"]
    )

    result = await db_session.execute(select(Order))

    assert len(result.scalars().all()) == 2


@pytest.mark.asyncio
async def test_order_price_does_not_change(
    api_client,
    db_session,
    order_data,
):
    user_id = order_data["user1"]
    movie_id = order_data["movie1"]

    await add_movies_to_cart(
        api_client,
        user_id,
        [movie_id],
    )

    response = await api_client.post(
        "/orders",
        headers=auth_headers(user_id),
    )

    assert response.status_code == 201

    order_id = response.json()["id"]

    # Change the catalog price after the order.
    movie = await db_session.get(Movie, movie_id)
    movie.price = Decimal("19.99")

    await db_session.commit()

    result = await db_session.execute(
        select(OrderItem).where(
            OrderItem.order_id == order_id
        )
    )

    saved_item = result.scalar_one()

    assert saved_item.price_at_order == Decimal("9.99")

    order = await db_session.get(Order, order_id)

    assert order.total_amount == Decimal("9.99")


@pytest.mark.asyncio
async def test_order_uses_price_at_checkout(
    api_client,
    db_session,
    order_data,
):
    user_id = order_data["user1"]
    movie_id = order_data["movie1"]

    await add_movies_to_cart(
        api_client,
        user_id,
        [movie_id],
    )

    # Price changes while movie is in the cart.
    movie = await db_session.get(Movie, movie_id)
    movie.price = Decimal("14.99")

    await db_session.commit()

    response = await api_client.post(
        "/orders",
        headers=auth_headers(user_id),
    )

    assert response.status_code == 201

    data = response.json()

    assert Decimal(
        data["total_amount"]
    ) == Decimal("14.99")

    assert Decimal(
        data["items"][0]["price_at_order"]
    ) == Decimal("14.99")

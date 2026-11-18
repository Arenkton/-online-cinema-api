from datetime import datetime, timezone
from decimal import Decimal

import pytest
import pytest_asyncio

from src.jwt_service import create_jwt_token
from src.models import (
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
        email="orders-get-first@example.com",
        hashed_password="test-password-hash",
        is_active=True,
        group=group,
    )

    second_user = User(
        email="orders-get-second@example.com",
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
    token = create_jwt_token(
        user_id,
        token_type,
    )

    return {
        "Authorization": f"Bearer {token}"
    }


async def create_test_order(
    db_session,
    user_id,
    movies,
    created_at=None,
):
    """
    movies: list of (movie_id, price_at_order).
    """
    order_items = [
        OrderItem(
            movie_id=movie_id,
            price_at_order=price,
        )
        for movie_id, price in movies
    ]

    total_amount = sum(
        (price for _, price in movies),
        Decimal("0.00"),
    )

    order = Order(
        user_id=user_id,
        status="pending",
        total_amount=total_amount,
        items=order_items,
    )

    if created_at is not None:
        order.created_at = created_at

    db_session.add(order)
    await db_session.flush()

    order_id = order.id

    await db_session.commit()

    return order_id


@pytest.mark.asyncio
async def test_get_orders_empty(
    api_client,
    order_data,
):
    response = await api_client.get(
        "/orders",
        headers=auth_headers(order_data["user1"]),
    )

    assert response.status_code == 200
    assert response.json() == []


@pytest.mark.asyncio
async def test_get_orders_only_own(
    api_client,
    db_session,
    order_data,
):
    first_order_id = await create_test_order(
        db_session,
        order_data["user1"],
        [
            (
                order_data["movie1"],
                Decimal("9.99"),
            )
        ],
    )

    second_order_id = await create_test_order(
        db_session,
        order_data["user2"],
        [
            (
                order_data["movie2"],
                Decimal("12.50"),
            )
        ],
    )

    response = await api_client.get(
        "/orders",
        headers=auth_headers(order_data["user1"]),
    )

    assert response.status_code == 200

    orders = response.json()

    assert len(orders) == 1
    assert orders[0]["id"] == first_order_id
    assert orders[0]["id"] != second_order_id
    assert orders[0]["user_id"] == order_data["user1"]


@pytest.mark.asyncio
async def test_get_orders_newest_first(
    api_client,
    db_session,
    order_data,
):
    older_order_id = await create_test_order(
        db_session,
        order_data["user1"],
        [(order_data["movie1"], Decimal("9.99"))],
        created_at=datetime(
            2026, 11, 16, 10, 0, tzinfo=timezone.utc
        ),
    )

    newer_order_id = await create_test_order(
        db_session,
        order_data["user1"],
        [(order_data["movie2"], Decimal("12.50"))],
        created_at=datetime(
            2026, 11, 17, 10, 0, tzinfo=timezone.utc
        ),
    )

    response = await api_client.get(
        "/orders",
        headers=auth_headers(order_data["user1"]),
    )

    assert response.status_code == 200

    order_ids = [
        order["id"]
        for order in response.json()
    ]

    assert order_ids == [
        newer_order_id,
        older_order_id,
    ]


@pytest.mark.asyncio
async def test_get_orders_includes_items_and_prices(
    api_client,
    db_session,
    order_data,
):
    await create_test_order(
        db_session,
        order_data["user1"],
        [
            (order_data["movie1"], Decimal("9.99")),
            (order_data["movie2"], Decimal("12.50")),
        ],
    )

    response = await api_client.get(
        "/orders",
        headers=auth_headers(order_data["user1"]),
    )

    assert response.status_code == 200

    orders = response.json()

    assert len(orders) == 1

    order = orders[0]

    assert order["status"] == "pending"
    assert order["created_at"] is not None
    assert Decimal(
        order["total_amount"]
    ) == Decimal("22.49")

    assert len(order["items"]) == 2

    items = {
        item["movie_id"]: item
        for item in order["items"]
    }

    assert Decimal(
        items[order_data["movie1"]]["price_at_order"]
    ) == Decimal("9.99")

    assert Decimal(
        items[order_data["movie2"]]["price_at_order"]
    ) == Decimal("12.50")


@pytest.mark.asyncio
async def test_get_order_details(
    api_client,
    db_session,
    order_data,
):
    user_id = order_data["user1"]

    order_id = await create_test_order(
        db_session,
        user_id,
        [(order_data["movie1"], Decimal("9.99"))],
    )

    response = await api_client.get(
        f"/orders/{order_id}",
        headers=auth_headers(user_id),
    )

    assert response.status_code == 200

    data = response.json()

    assert data["id"] == order_id
    assert data["user_id"] == user_id
    assert data["status"] == "pending"
    assert data["created_at"] is not None

    assert Decimal(
        data["total_amount"]
    ) == Decimal("9.99")

    assert len(data["items"]) == 1
    assert data["items"][0]["movie_id"] == (
        order_data["movie1"]
    )

    assert Decimal(
        data["items"][0]["price_at_order"]
    ) == Decimal("9.99")


@pytest.mark.asyncio
async def test_get_nonexistent_order(
    api_client,
    order_data,
):
    response = await api_client.get(
        "/orders/999999",
        headers=auth_headers(order_data["user1"]),
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Order not found"


@pytest.mark.asyncio
async def test_cannot_get_another_users_order(
    api_client,
    db_session,
    order_data,
):
    second_order_id = await create_test_order(
        db_session,
        order_data["user2"],
        [(order_data["movie1"], Decimal("9.99"))],
    )

    response = await api_client.get(
        f"/orders/{second_order_id}",
        headers=auth_headers(order_data["user1"]),
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Order not found"

    # The actual owner must still have access.
    owner_response = await api_client.get(
        f"/orders/{second_order_id}",
        headers=auth_headers(order_data["user2"]),
    )

    assert owner_response.status_code == 200


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "order_id",
    ["0", "-1", "abc"],
)
async def test_invalid_order_id(
    api_client,
    order_data,
    order_id,
):
    response = await api_client.get(
        f"/orders/{order_id}",
        headers=auth_headers(order_data["user1"]),
    )

    assert response.status_code == 422


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "path",
    ["/orders", "/orders/1"],
)
async def test_get_orders_without_auth(
    api_client,
    path,
):
    response = await api_client.get(path)

    assert response.status_code == 401


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "path",
    ["/orders", "/orders/1"],
)
async def test_get_orders_invalid_token(
    api_client,
    path,
):
    response = await api_client.get(
        path,
        headers={
            "Authorization": "Bearer invalid.jwt.token"
        },
    )

    assert response.status_code == 401


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "path",
    ["/orders", "/orders/1"],
)
async def test_refresh_token_cannot_access_orders(
    api_client,
    order_data,
    path,
):
    response = await api_client.get(
        path,
        headers=auth_headers(
            order_data["user1"],
            token_type="refresh",
        ),
    )

    assert response.status_code == 401


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "path",
    ["/orders", "/orders/1"],
)
async def test_inactive_user_cannot_get_orders(
    api_client,
    db_session,
    order_data,
    path,
):
    user = await db_session.get(
        User,
        order_data["user1"],
    )

    user.is_active = False
    await db_session.commit()

    response = await api_client.get(
        path,
        headers=auth_headers(order_data["user1"]),
    )

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_order_price_remains_unchanged(
    api_client,
    db_session,
    order_data,
):
    user_id = order_data["user1"]
    movie_id = order_data["movie1"]

    order_id = await create_test_order(
        db_session,
        user_id,
        [(movie_id, Decimal("9.99"))],
    )

    # The movie's current price changes.
    movie = await db_session.get(Movie, movie_id)
    movie.price = Decimal("29.99")

    await db_session.commit()

    response = await api_client.get(
        f"/orders/{order_id}",
        headers=auth_headers(user_id),
    )

    assert response.status_code == 200

    order = response.json()

    assert Decimal(
        order["total_amount"]
    ) == Decimal("9.99")

    assert Decimal(
        order["items"][0]["price_at_order"]
    ) == Decimal("9.99")

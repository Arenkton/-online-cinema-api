"""Order creation, cancellation and conflict API tests."""
from decimal import Decimal

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from src.models import (
    Cart,
    Certification,
    Movie,
    Order,
    OrderItem,
    Payment,
    User,
    UserGroup,
    UserGroupEnum,
)
from tests.helpers import (
    auth_headers,
    create_cart_with_movies,
    create_test_order,
    get_cart_items,
)


@pytest.fixture(autouse=True)
def jwt_secret(monkeypatch):
    monkeypatch.setenv(
        "JWT_SECRET_KEY", "test-secret-key-for-jwt-unit-tests-123456789"
    )


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


@pytest.mark.asyncio
async def test_cancel_pending_order_success(
    api_client,
    db_session,
    cart_data,
):
    user_id, movie_id = cart_data

    order = await create_test_order(
        db_session,
        user_id=user_id,
        movie_id=movie_id,
        order_status="pending",
    )

    response = await api_client.post(
        f"/orders/{order.id}/cancel",
        headers=auth_headers(user_id),
    )

    assert response.status_code == 200

    data = response.json()
    assert data["id"] == order.id
    assert data["status"] == "canceled"

    await db_session.refresh(order)
    assert order.status == "canceled"

    result = await db_session.execute(
        select(OrderItem).where(
            OrderItem.order_id == order.id
        )
    )
    items = result.scalars().all()

    # Canceling must not delete order history.
    assert len(items) == 1
    assert items[0].movie_id == movie_id


@pytest.mark.asyncio
async def test_cannot_cancel_paid_order(
    api_client,
    db_session,
    cart_data,
):
    user_id, movie_id = cart_data

    order = await create_test_order(
        db_session,
        user_id=user_id,
        movie_id=movie_id,
        order_status="paid",
    )

    response = await api_client.post(
        f"/orders/{order.id}/cancel",
        headers=auth_headers(user_id),
    )

    assert response.status_code == 409
    assert response.json()["detail"] == (
        "Only pending orders can be canceled"
    )

    await db_session.refresh(order)
    assert order.status == "paid"


@pytest.mark.asyncio
async def test_cannot_cancel_order_twice(
    api_client,
    db_session,
    cart_data,
):
    user_id, movie_id = cart_data

    order = await create_test_order(
        db_session,
        user_id=user_id,
        movie_id=movie_id,
        order_status="pending",
    )

    headers = auth_headers(user_id)
    url = f"/orders/{order.id}/cancel"

    first_response = await api_client.post(
        url,
        headers=headers,
    )
    second_response = await api_client.post(
        url,
        headers=headers,
    )

    assert first_response.status_code == 200
    assert second_response.status_code == 409

    await db_session.refresh(order)
    assert order.status == "canceled"


@pytest.mark.asyncio
async def test_cancel_nonexistent_order_returns_404(
    api_client,
    cart_data,
):
    user_id, _ = cart_data

    response = await api_client.post(
        "/orders/999999/cancel",
        headers=auth_headers(user_id),
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Order not found"


@pytest.mark.asyncio
async def test_cannot_cancel_another_users_order(
    api_client,
    db_session,
    cart_data,
):
    user_id, movie_id = cart_data

    user = await db_session.get(User, user_id)

    other_user = User(
        email="other-cancel-user@example.com",
        hashed_password="test-password-hash",
        is_active=True,
        group_id=user.group_id,
    )

    db_session.add(other_user)
    await db_session.flush()

    order = await create_test_order(
        db_session,
        user_id=other_user.id,
        movie_id=movie_id,
        order_status="pending",
    )

    response = await api_client.post(
        f"/orders/{order.id}/cancel",
        headers=auth_headers(user_id),
    )

    assert response.status_code == 404

    await db_session.refresh(order)
    assert order.status == "pending"


@pytest.mark.asyncio
async def test_cannot_cancel_order_with_active_checkout(
    api_client,
    db_session,
    cart_data,
):
    user_id, movie_id = cart_data

    order = await create_test_order(
        db_session,
        user_id=user_id,
        movie_id=movie_id,
        order_status="pending",
    )

    payment = Payment(
        user_id=user_id,
        order_id=order.id,
        status="pending",
        amount=Decimal("9.99"),
        external_payment_id="cs_test_active_checkout",
    )

    db_session.add(payment)
    await db_session.commit()

    response = await api_client.post(
        f"/orders/{order.id}/cancel",
        headers=auth_headers(user_id),
    )

    assert response.status_code == 409
    assert response.json()["detail"] == (
        "Order cannot be canceled while "
        "a Stripe Checkout Session is active"
    )

    await db_session.refresh(order)
    assert order.status == "pending"


@pytest.mark.asyncio
async def test_cancel_order_without_auth(
    api_client,
    db_session,
    cart_data,
):
    user_id, movie_id = cart_data

    order = await create_test_order(
        db_session,
        user_id=user_id,
        movie_id=movie_id,
        order_status="pending",
    )

    response = await api_client.post(
        f"/orders/{order.id}/cancel",
    )

    assert response.status_code == 401

    await db_session.refresh(order)
    assert order.status == "pending"






@pytest.mark.asyncio
async def test_order_excludes_purchased_movie(
    api_client,
    db_session,
    cart_data,
):
    user_id, purchased_movie_id = cart_data

    await create_test_order(
        db_session,
        user_id=user_id,
        movie_id=purchased_movie_id,
        order_status="paid",
    )

    original_movie = await db_session.get(
        Movie, purchased_movie_id
    )

    available_movie = Movie(
        name="Available Movie For Order",
        year=2025,
        time=110,
        imdb=7.5,
        votes=500,
        description="Movie not purchased yet",
        price=Decimal("14.99"),
        certification_id=original_movie.certification_id,
    )

    db_session.add(available_movie)
    await db_session.flush()

    cart_id = await create_cart_with_movies(
        db_session,
        user_id=user_id,
        movie_ids=[
            purchased_movie_id,
            available_movie.id,
        ],
    )

    response = await api_client.post(
        "/orders",
        headers=auth_headers(user_id),
    )

    assert response.status_code == 201

    new_order_id = response.json()["id"]

    order = await db_session.get(Order, new_order_id)

    assert order.status == "pending"
    assert order.total_amount == Decimal("14.99")

    result = await db_session.execute(
        select(OrderItem).where(
            OrderItem.order_id == new_order_id
        )
    )

    items = result.scalars().all()

    assert len(items) == 1
    assert items[0].movie_id == available_movie.id
    assert items[0].price_at_order == Decimal("14.99")

    # Both cart items must be removed after order creation.
    assert await get_cart_items(db_session, cart_id) == []


@pytest.mark.asyncio
async def test_order_all_movies_purchased_returns_409(
    api_client,
    db_session,
    cart_data,
):
    user_id, movie_id = cart_data

    await create_test_order(
        db_session,
        user_id=user_id,
        movie_id=movie_id,
        order_status="paid",
    )

    cart_id = await create_cart_with_movies(
        db_session,
        user_id=user_id,
        movie_ids=[movie_id],
    )

    response = await api_client.post(
        "/orders",
        headers=auth_headers(user_id),
    )

    assert response.status_code == 409
    assert response.json()["detail"] == (
        "All movies in cart are already purchased"
    )

    result = await db_session.execute(
        select(Order).where(Order.user_id == user_id)
    )

    orders = result.scalars().all()

    # Only the original paid order should exist.
    assert len(orders) == 1
    assert orders[0].status == "paid"

    # Failed order creation must not modify the cart.
    items = await get_cart_items(db_session, cart_id)

    assert len(items) == 1
    assert items[0].movie_id == movie_id


@pytest.mark.asyncio
async def test_other_users_purchase_does_not_block_order(
    api_client,
    db_session,
    cart_data,
):
    user_id, movie_id = cart_data

    user = await db_session.get(User, user_id)

    other_user = User(
        email="other-order-buyer@example.com",
        hashed_password="test-password-hash",
        is_active=True,
        group_id=user.group_id,
    )

    db_session.add(other_user)
    await db_session.flush()

    await create_test_order(
        db_session,
        user_id=other_user.id,
        movie_id=movie_id,
        order_status="paid",
    )

    cart_id = await create_cart_with_movies(
        db_session,
        user_id=user_id,
        movie_ids=[movie_id],
    )

    response = await api_client.post(
        "/orders",
        headers=auth_headers(user_id),
    )

    assert response.status_code == 201

    order_id = response.json()["id"]

    order = await db_session.get(Order, order_id)

    assert order.user_id == user_id
    assert order.status == "pending"
    assert order.total_amount == Decimal("9.99")

    result = await db_session.execute(
        select(OrderItem).where(
            OrderItem.order_id == order_id
        )
    )

    items = result.scalars().all()

    assert len(items) == 1
    assert items[0].movie_id == movie_id

    assert await get_cart_items(db_session, cart_id) == []


@pytest.mark.asyncio
async def test_pending_order_duplicate_returns_409(
    api_client,
    db_session,
    cart_data,
):
    user_id, movie_id = cart_data

    existing_order = await create_test_order(
        db_session,
        user_id=user_id,
        movie_id=movie_id,
        order_status="pending",
    )

    cart_id = await create_cart_with_movies(
        db_session,
        user_id=user_id,
        movie_ids=[movie_id],
    )

    response = await api_client.post(
        "/orders",
        headers=auth_headers(user_id),
    )

    assert response.status_code == 409
    assert response.json()["detail"] == (
        "Movie already exists in a pending order"
    )

    orders = (
        await db_session.execute(
            select(Order).where(Order.user_id == user_id)
        )
    ).scalars().all()

    assert len(orders) == 1
    assert orders[0].id == existing_order.id

    items = await get_cart_items(db_session, cart_id)

    assert len(items) == 1
    assert items[0].movie_id == movie_id


@pytest.mark.asyncio
async def test_canceled_order_does_not_block_new_order(
    api_client,
    db_session,
    cart_data,
):
    user_id, movie_id = cart_data

    await create_test_order(
        db_session,
        user_id=user_id,
        movie_id=movie_id,
        order_status="canceled",
    )

    await create_cart_with_movies(
        db_session,
        user_id=user_id,
        movie_ids=[movie_id],
    )

    response = await api_client.post(
        "/orders",
        headers=auth_headers(user_id),
    )

    assert response.status_code == 201

    order = await db_session.get(
        Order,
        response.json()["id"],
    )

    assert order.status == "pending"
    assert order.total_amount == Decimal("9.99")

    items = (
        await db_session.execute(
            select(OrderItem).where(
                OrderItem.order_id == order.id
            )
        )
    ).scalars().all()

    assert len(items) == 1
    assert items[0].movie_id == movie_id


@pytest.mark.asyncio
async def test_other_users_pending_order_does_not_block(
    api_client,
    db_session,
    cart_data,
):
    user_id, movie_id = cart_data

    user = await db_session.get(User, user_id)

    other_user = User(
        email="other-pending-order@example.com",
        hashed_password="test-password-hash",
        is_active=True,
        group_id=user.group_id,
    )

    db_session.add(other_user)
    await db_session.flush()

    await create_test_order(
        db_session,
        user_id=other_user.id,
        movie_id=movie_id,
        order_status="pending",
    )

    await create_cart_with_movies(
        db_session,
        user_id=user_id,
        movie_ids=[movie_id],
    )

    response = await api_client.post(
        "/orders",
        headers=auth_headers(user_id),
    )

    assert response.status_code == 201

    order = await db_session.get(
        Order,
        response.json()["id"],
    )

    assert order.user_id == user_id
    assert order.status == "pending"


@pytest.mark.asyncio
async def test_mixed_cart_with_pending_movie_returns_409(
    api_client,
    db_session,
    cart_data,
):
    user_id, pending_movie_id = cart_data

    original_movie = await db_session.get(
        Movie,
        pending_movie_id,
    )

    available_movie = Movie(
        name="Available Movie For Pending Test",
        year=2025,
        time=115,
        imdb=7.9,
        votes=400,
        description="Movie without pending orders",
        price=Decimal("19.99"),
        certification_id=original_movie.certification_id,
    )

    db_session.add(available_movie)
    await db_session.flush()

    await create_test_order(
        db_session,
        user_id=user_id,
        movie_id=pending_movie_id,
        order_status="pending",
    )

    cart_id = await create_cart_with_movies(
        db_session,
        user_id=user_id,
        movie_ids=[
            pending_movie_id,
            available_movie.id,
        ],
    )

    response = await api_client.post(
        "/orders",
        headers=auth_headers(user_id),
    )

    assert response.status_code == 409

    items = await get_cart_items(db_session, cart_id)

    assert len(items) == 2
    assert {item.movie_id for item in items} == {
        pending_movie_id,
        available_movie.id,
    }

    orders = (
        await db_session.execute(
            select(Order).where(Order.user_id == user_id)
        )
    ).scalars().all()

    # No additional order should be created.
    assert len(orders) == 1


@pytest.mark.asyncio
async def test_readding_movie_from_pending_order(
    api_client,
    db_session,
    cart_data,
):
    user_id, movie_id = cart_data
    headers = auth_headers(user_id)

    first_add = await api_client.post(
        "/cart/items",
        json={"movie_id": movie_id},
        headers=headers,
    )

    assert first_add.status_code == 201

    first_order = await api_client.post(
        "/orders",
        headers=headers,
    )

    assert first_order.status_code == 201

    # An order is pending, so the movie is not purchased yet.
    second_add = await api_client.post(
        "/cart/items",
        json={"movie_id": movie_id},
        headers=headers,
    )

    assert second_add.status_code == 201

    second_order = await api_client.post(
        "/orders",
        headers=headers,
    )

    assert second_order.status_code == 409
    assert second_order.json()["detail"] == (
        "Movie already exists in a pending order"
    )

    orders = (
        await db_session.execute(
            select(Order).where(Order.user_id == user_id)
        )
    ).scalars().all()

    assert len(orders) == 1
    assert orders[0].id == first_order.json()["id"]

    cart = await db_session.scalar(
        select(Cart).where(Cart.user_id == user_id)
    )

    items = await get_cart_items(db_session, cart.id)

    assert len(items) == 1
    assert items[0].movie_id == movie_id

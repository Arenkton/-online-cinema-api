from decimal import Decimal

import pytest
import pytest_asyncio
from sqlalchemy import select

from src.jwt_service import create_jwt_token
from src.models import (
    Cart,
    CartItem,
    Certification,
    Movie,
    User,
    UserGroup,
    UserGroupEnum,
    Order,
    OrderItem,
    Payment,
)


@pytest.fixture(autouse=True)
def jwt_secret(monkeypatch):
    monkeypatch.setenv(
        "JWT_SECRET_KEY",
        "test-secret-key-for-jwt-unit-tests-123456789",
    )


@pytest_asyncio.fixture
async def cart_data(db_session):
    group = UserGroup(name=UserGroupEnum.USER.value)
    certification = Certification(name="PG-13")

    user = User(
        email="cart-api@example.com",
        hashed_password="test-password-hash",
        is_active=True,
        group=group,
    )

    movie = Movie(
        name="Test Movie",
        year=2024,
        time=120,
        imdb=8.5,
        votes=1000,
        description="Movie for cart API tests",
        price=Decimal("9.99"),
        certification=certification,
    )

    db_session.add_all([user, movie])
    await db_session.commit()

    return user.id, movie.id


def auth_headers(user_id: int) -> dict:
    token = create_jwt_token(user_id, "access")
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_add_movie_to_cart_success(
    api_client,
    db_session,
    cart_data,
):
    user_id, movie_id = cart_data

    response = await api_client.post(
        "/cart/items",
        json={"movie_id": movie_id},
        headers=auth_headers(user_id),
    )

    assert response.status_code == 201

    data = response.json()

    assert data["id"] is not None
    assert data["movie_id"] == movie_id
    assert data["added_at"] is not None

    result = await db_session.execute(
        select(Cart).where(Cart.user_id == user_id)
    )

    cart = result.scalar_one()

    assert cart.id is not None

    result = await db_session.execute(
        select(CartItem).where(
            CartItem.cart_id == cart.id,
            CartItem.movie_id == movie_id,
        )
    )

    assert result.scalar_one().id == data["id"]


@pytest.mark.asyncio
async def test_duplicate_movie_returns_409(
    api_client,
    db_session,
    cart_data,
):
    user_id, movie_id = cart_data

    headers = auth_headers(user_id)
    payload = {"movie_id": movie_id}

    first_response = await api_client.post(
        "/cart/items",
        json=payload,
        headers=headers,
    )

    second_response = await api_client.post(
        "/cart/items",
        json=payload,
        headers=headers,
    )

    assert first_response.status_code == 201
    assert second_response.status_code == 409

    result = await db_session.execute(
        select(CartItem)
    )

    assert len(result.scalars().all()) == 1


@pytest.mark.asyncio
async def test_add_nonexistent_movie(
    api_client,
    db_session,
    cart_data,
):
    user_id, _ = cart_data

    response = await api_client.post(
        "/cart/items",
        json={"movie_id": 999999},
        headers=auth_headers(user_id),
    )

    assert response.status_code == 404

    result = await db_session.execute(
        select(Cart).where(Cart.user_id == user_id)
    )

    assert result.scalar_one_or_none() is None


@pytest.mark.asyncio
async def test_add_movie_without_auth(
    api_client,
    cart_data,
):
    _, movie_id = cart_data

    response = await api_client.post(
        "/cart/items",
        json={"movie_id": movie_id},
    )

    assert response.status_code == 401


@pytest.mark.asyncio
@pytest.mark.parametrize("movie_id", [0, -1, -100])
async def test_invalid_movie_id(
    api_client,
    cart_data,
    movie_id,
):
    user_id, _ = cart_data

    response = await api_client.post(
        "/cart/items",
        json={"movie_id": movie_id},
        headers=auth_headers(user_id),
    )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_missing_movie_id(
    api_client,
    cart_data,
):
    user_id, _ = cart_data

    response = await api_client.post(
        "/cart/items",
        json={},
        headers=auth_headers(user_id),
    )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_different_users_have_separate_carts(
    api_client,
    db_session,
    cart_data,
):
    first_user_id, movie_id = cart_data

    first_user = await db_session.get(User, first_user_id)

    second_user = User(
        email="second-cart@example.com",
        hashed_password="test-password-hash",
        is_active=True,
        group_id=first_user.group_id,
    )

    db_session.add(second_user)
    await db_session.commit()

    first_response = await api_client.post(
        "/cart/items",
        json={"movie_id": movie_id},
        headers=auth_headers(first_user_id),
    )

    second_response = await api_client.post(
        "/cart/items",
        json={"movie_id": movie_id},
        headers=auth_headers(second_user.id),
    )

    assert first_response.status_code == 201
    assert second_response.status_code == 201

    result = await db_session.execute(
        select(Cart)
    )

    carts = result.scalars().all()

    assert len(carts) == 2
    assert {cart.user_id for cart in carts} == {
        first_user_id,
        second_user.id,
    }


@pytest.mark.asyncio
async def test_inactive_user_cannot_add_movie(
    api_client,
    db_session,
    cart_data,
):
    user_id, movie_id = cart_data

    user = await db_session.get(User, user_id)

    user.is_active = False
    await db_session.commit()

    response = await api_client.post(
        "/cart/items",
        json={"movie_id": movie_id},
        headers=auth_headers(user_id),
    )

    assert response.status_code == 401


async def get_cart_items(db_session, cart_id):
    result = await db_session.execute(
        select(CartItem).where(CartItem.cart_id == cart_id)
    )
    return result.scalars().all()


@pytest.mark.asyncio
async def test_clear_cart_success(
    api_client,
    db_session,
    cart_data,
):
    user_id, movie_id = cart_data
    movie = await db_session.get(Movie, movie_id)

    second_movie = Movie(
        name="Second Test Movie",
        year=2025,
        time=110,
        imdb=7.8,
        votes=500,
        description="Second movie for cart tests",
        price=Decimal("14.99"),
        certification_id=movie.certification_id,
    )

    db_session.add(second_movie)
    await db_session.commit()

    headers = auth_headers(user_id)

    for current_movie_id in (movie_id, second_movie.id):
        response = await api_client.post(
            "/cart/items",
            json={"movie_id": current_movie_id},
            headers=headers,
        )
        assert response.status_code == 201

    cart = await db_session.scalar(
        select(Cart).where(Cart.user_id == user_id)
    )
    assert len(await get_cart_items(db_session, cart.id)) == 2

    response = await api_client.delete(
        "/cart",
        headers=headers,
    )

    assert response.status_code == 204
    assert response.content == b""
    assert await get_cart_items(db_session, cart.id) == []

    # The cart itself must not be deleted.
    assert await db_session.get(Cart, cart.id) is not None


@pytest.mark.asyncio
async def test_clear_empty_cart(
    api_client,
    db_session,
    cart_data,
):
    user_id, movie_id = cart_data
    headers = auth_headers(user_id)

    add_response = await api_client.post(
        "/cart/items",
        json={"movie_id": movie_id},
        headers=headers,
    )
    assert add_response.status_code == 201

    first_response = await api_client.delete(
        "/cart",
        headers=headers,
    )
    second_response = await api_client.delete(
        "/cart",
        headers=headers,
    )

    assert first_response.status_code == 204
    assert second_response.status_code == 204

    cart = await db_session.scalar(
        select(Cart).where(Cart.user_id == user_id)
    )

    assert await get_cart_items(db_session, cart.id) == []


@pytest.mark.asyncio
async def test_clear_cart_without_existing_cart(
    api_client,
    db_session,
    cart_data,
):
    user_id, _ = cart_data

    response = await api_client.delete(
        "/cart",
        headers=auth_headers(user_id),
    )

    assert response.status_code == 204

    cart = await db_session.scalar(
        select(Cart).where(Cart.user_id == user_id)
    )
    assert cart is None


@pytest.mark.asyncio
async def test_clear_cart_without_auth(
    api_client,
    db_session,
    cart_data,
):
    user_id, movie_id = cart_data

    add_response = await api_client.post(
        "/cart/items",
        json={"movie_id": movie_id},
        headers=auth_headers(user_id),
    )
    assert add_response.status_code == 201

    response = await api_client.delete("/cart")

    assert response.status_code == 401

    cart = await db_session.scalar(
        select(Cart).where(Cart.user_id == user_id)
    )

    assert len(await get_cart_items(db_session, cart.id)) == 1


@pytest.mark.asyncio
async def test_clear_cart_does_not_affect_other_user(
    api_client,
    db_session,
    cart_data,
):
    first_user_id, movie_id = cart_data

    first_user = await db_session.get(User, first_user_id)

    second_user = User(
        email="clear-cart-second@example.com",
        hashed_password="test-password-hash",
        is_active=True,
        group_id=first_user.group_id,
    )

    db_session.add(second_user)
    await db_session.commit()

    for user_id in (first_user_id, second_user.id):
        response = await api_client.post(
            "/cart/items",
            json={"movie_id": movie_id},
            headers=auth_headers(user_id),
        )
        assert response.status_code == 201

    clear_response = await api_client.delete(
        "/cart",
        headers=auth_headers(first_user_id),
    )
    assert clear_response.status_code == 204

    first_cart = await db_session.scalar(
        select(Cart).where(Cart.user_id == first_user_id)
    )
    second_cart = await db_session.scalar(
        select(Cart).where(Cart.user_id == second_user.id)
    )

    first_items = await get_cart_items(
        db_session, first_cart.id
    )
    second_items = await get_cart_items(
        db_session, second_cart.id
    )

    assert len(first_items) == 0
    assert len(second_items) == 1
    assert second_items[0].movie_id == movie_id


async def create_test_order(
    db_session,
    user_id: int,
    movie_id: int,
    order_status: str = "paid",
):
    order = Order(
        user_id=user_id,
        status=order_status,
        total_amount=Decimal("9.99"),
        items=[
            OrderItem(
                movie_id=movie_id,
                price_at_order=Decimal("9.99"),
            )
        ],
    )

    db_session.add(order)
    await db_session.commit()

    return order


@pytest.mark.asyncio
async def test_cannot_add_purchased_movie_to_cart(
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

    response = await api_client.post(
        "/cart/items",
        json={"movie_id": movie_id},
        headers=auth_headers(user_id),
    )

    assert response.status_code == 409
    assert response.json()["detail"] == (
        "Movie has already been purchased"
    )

    cart = await db_session.scalar(
        select(Cart).where(Cart.user_id == user_id)
    )
    assert cart is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "order_status",
    ["pending", "canceled"],
)
async def test_can_add_movie_from_unpaid_order(
    api_client,
    db_session,
    cart_data,
    order_status,
):
    user_id, movie_id = cart_data

    await create_test_order(
        db_session,
        user_id=user_id,
        movie_id=movie_id,
        order_status=order_status,
    )

    response = await api_client.post(
        "/cart/items",
        json={"movie_id": movie_id},
        headers=auth_headers(user_id),
    )

    assert response.status_code == 201
    assert response.json()["movie_id"] == movie_id


@pytest.mark.asyncio
async def test_other_users_purchase_does_not_block_cart(
    api_client,
    db_session,
    cart_data,
):
    user_id, movie_id = cart_data

    first_user = await db_session.get(User, user_id)

    other_user = User(
        email="purchased-by-other@example.com",
        hashed_password="test-password-hash",
        is_active=True,
        group_id=first_user.group_id,
    )

    db_session.add(other_user)
    await db_session.flush()

    await create_test_order(
        db_session,
        user_id=other_user.id,
        movie_id=movie_id,
        order_status="paid",
    )

    response = await api_client.post(
        "/cart/items",
        json={"movie_id": movie_id},
        headers=auth_headers(user_id),
    )

    assert response.status_code == 201
    assert response.json()["movie_id"] == movie_id


@pytest.mark.asyncio
async def test_purchased_movie_rejected_without_changing_cart(
    api_client,
    db_session,
    cart_data,
):
    user_id, movie_id = cart_data
    headers = auth_headers(user_id)

    first_response = await api_client.post(
        "/cart/items",
        json={"movie_id": movie_id},
        headers=headers,
    )

    assert first_response.status_code == 201
    original_item_id = first_response.json()["id"]

    await create_test_order(
        db_session,
        user_id=user_id,
        movie_id=movie_id,
        order_status="paid",
    )

    second_response = await api_client.post(
        "/cart/items",
        json={"movie_id": movie_id},
        headers=headers,
    )

    assert second_response.status_code == 409
    assert second_response.json()["detail"] == (
        "Movie has already been purchased"
    )

    cart = await db_session.scalar(
        select(Cart).where(Cart.user_id == user_id)
    )

    items = await get_cart_items(db_session, cart.id)

    assert len(items) == 1
    assert items[0].id == original_item_id
    assert items[0].movie_id == movie_id


async def create_cart_with_movies(
    db_session,
    user_id: int,
    movie_ids: list[int],
) -> int:
    cart = Cart(user_id=user_id)
    db_session.add(cart)
    await db_session.flush()

    db_session.add_all(
        [
            CartItem(
                cart_id=cart.id,
                movie_id=movie_id,
            )
            for movie_id in movie_ids
        ]
    )

    cart_id = cart.id
    await db_session.commit()

    return cart_id


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
async def test_canceled_order_cannot_create_payment(
    api_client,
    db_session,
    cart_data,
):
    user_id, movie_id = cart_data
    headers = auth_headers(user_id)

    order = await create_test_order(
        db_session,
        user_id=user_id,
        movie_id=movie_id,
        order_status="pending",
    )

    cancel_response = await api_client.post(
        f"/orders/{order.id}/cancel",
        headers=headers,
    )
    assert cancel_response.status_code == 200

    response = await api_client.post(
        "/payments",
        json={"order_id": order.id},
        headers=headers,
    )

    assert response.status_code == 409

    payment_id = await db_session.scalar(
        select(Payment.id).where(
            Payment.order_id == order.id
        )
    )
    assert payment_id is None


@pytest.mark.asyncio
async def test_canceled_order_cannot_start_checkout(
    api_client,
    db_session,
    cart_data,
):
    user_id, movie_id = cart_data
    headers = auth_headers(user_id)

    order = await create_test_order(
        db_session,
        user_id=user_id,
        movie_id=movie_id,
        order_status="pending",
    )

    payment_response = await api_client.post(
        "/payments",
        json={"order_id": order.id},
        headers=headers,
    )

    assert payment_response.status_code == 201
    payment_id = payment_response.json()["id"]

    cancel_response = await api_client.post(
        f"/orders/{order.id}/cancel",
        headers=headers,
    )
    assert cancel_response.status_code == 200

    checkout_response = await api_client.post(
        f"/payments/{payment_id}/checkout",
        headers=headers,
    )

    assert checkout_response.status_code == 409

    payment = await db_session.get(Payment, payment_id)
    await db_session.refresh(payment)
    await db_session.refresh(order)

    assert payment.external_payment_id is None
    assert order.status == "canceled"

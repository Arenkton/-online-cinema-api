"""Shopping cart API tests."""
from decimal import Decimal

import pytest
from sqlalchemy import select

from src.models import Cart, CartItem, Movie, User
from tests.helpers import auth_headers, create_test_order, get_cart_items


@pytest.fixture(autouse=True)
def jwt_secret(monkeypatch):
    monkeypatch.setenv(
        "JWT_SECRET_KEY", "test-secret-key-for-jwt-unit-tests-123456789"
    )


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

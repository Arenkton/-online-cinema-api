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

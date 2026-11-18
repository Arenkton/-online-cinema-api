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


TEST_SECRET = "test-secret-key-for-jwt-unit-tests-123456789"


@pytest.fixture(autouse=True)
def jwt_secret(monkeypatch):
    monkeypatch.setenv("JWT_SECRET_KEY", TEST_SECRET)


@pytest_asyncio.fixture
async def cart_data(db_session):
    group = UserGroup(name=UserGroupEnum.USER.value)
    certification = Certification(name="PG-13")

    first_user = User(
        email="delete-first@example.com",
        hashed_password="test-password-hash",
        is_active=True,
        group=group,
    )

    second_user = User(
        email="delete-second@example.com",
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
async def test_delete_movie_success(
    api_client,
    db_session,
    cart_data,
):
    user_id = cart_data["user1"]
    movie_id = cart_data["movie1"]

    cart_id = await create_cart_with_movies(
        db_session,
        user_id,
        [movie_id],
    )

    response = await api_client.delete(
        f"/cart/items/{movie_id}",
        headers=auth_headers(user_id),
    )

    assert response.status_code == 204
    assert response.content == b""

    result = await db_session.execute(
        select(CartItem).where(
            CartItem.cart_id == cart_id,
            CartItem.movie_id == movie_id,
        )
    )

    assert result.scalar_one_or_none() is None

    # The movie itself must not be deleted.
    movie = await db_session.get(Movie, movie_id)
    assert movie is not None


@pytest.mark.asyncio
async def test_delete_only_selected_movie(
    api_client,
    db_session,
    cart_data,
):
    user_id = cart_data["user1"]
    first_movie = cart_data["movie1"]
    second_movie = cart_data["movie2"]

    await create_cart_with_movies(
        db_session,
        user_id,
        [first_movie, second_movie],
    )

    response = await api_client.delete(
        f"/cart/items/{first_movie}",
        headers=auth_headers(user_id),
    )

    assert response.status_code == 204

    cart_response = await api_client.get(
        "/cart",
        headers=auth_headers(user_id),
    )

    assert cart_response.status_code == 200

    data = cart_response.json()

    assert len(data["items"]) == 1
    assert data["items"][0]["movie_id"] == second_movie
    assert Decimal(data["total_price"]) == Decimal("12.50")


@pytest.mark.asyncio
async def test_delete_movie_twice_returns_404(
    api_client,
    db_session,
    cart_data,
):
    user_id = cart_data["user1"]
    movie_id = cart_data["movie1"]

    await create_cart_with_movies(
        db_session,
        user_id,
        [movie_id],
    )

    first_response = await api_client.delete(
        f"/cart/items/{movie_id}",
        headers=auth_headers(user_id),
    )

    second_response = await api_client.delete(
        f"/cart/items/{movie_id}",
        headers=auth_headers(user_id),
    )

    assert first_response.status_code == 204
    assert second_response.status_code == 404
    assert second_response.json()["detail"] == (
        "Movie not found in cart"
    )


@pytest.mark.asyncio
async def test_delete_without_existing_cart(
    api_client,
    cart_data,
):
    response = await api_client.delete(
        f"/cart/items/{cart_data['movie1']}",
        headers=auth_headers(cart_data["user1"]),
    )

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_delete_movie_not_in_cart(
    api_client,
    db_session,
    cart_data,
):
    user_id = cart_data["user1"]

    await create_cart_with_movies(
        db_session,
        user_id,
        [cart_data["movie1"]],
    )

    response = await api_client.delete(
        f"/cart/items/{cart_data['movie2']}",
        headers=auth_headers(user_id),
    )

    assert response.status_code == 404

    cart_response = await api_client.get(
        "/cart",
        headers=auth_headers(user_id),
    )

    assert len(cart_response.json()["items"]) == 1


@pytest.mark.asyncio
async def test_cannot_delete_from_another_users_cart(
    api_client,
    db_session,
    cart_data,
):
    second_user_id = cart_data["user2"]
    movie_id = cart_data["movie1"]

    await create_cart_with_movies(
        db_session,
        second_user_id,
        [movie_id],
    )

    # First user tries to remove a movie
    # that exists only in the second user's cart.
    response = await api_client.delete(
        f"/cart/items/{movie_id}",
        headers=auth_headers(cart_data["user1"]),
    )

    assert response.status_code == 404

    second_cart = await api_client.get(
        "/cart",
        headers=auth_headers(second_user_id),
    )

    assert second_cart.status_code == 200
    assert len(second_cart.json()["items"]) == 1


@pytest.mark.asyncio
async def test_same_movie_in_two_carts(
    api_client,
    db_session,
    cart_data,
):
    movie_id = cart_data["movie1"]

    await create_cart_with_movies(
        db_session,
        cart_data["user1"],
        [movie_id],
    )

    await create_cart_with_movies(
        db_session,
        cart_data["user2"],
        [movie_id],
    )

    response = await api_client.delete(
        f"/cart/items/{movie_id}",
        headers=auth_headers(cart_data["user1"]),
    )

    assert response.status_code == 204

    first_cart = await api_client.get(
        "/cart",
        headers=auth_headers(cart_data["user1"]),
    )

    second_cart = await api_client.get(
        "/cart",
        headers=auth_headers(cart_data["user2"]),
    )

    assert first_cart.json()["items"] == []
    assert len(second_cart.json()["items"]) == 1
    assert second_cart.json()["items"][0]["movie_id"] == movie_id


@pytest.mark.asyncio
async def test_delete_without_auth(
    api_client,
    cart_data,
):
    response = await api_client.delete(
        f"/cart/items/{cart_data['movie1']}"
    )

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_delete_with_invalid_token(
    api_client,
    cart_data,
):
    response = await api_client.delete(
        f"/cart/items/{cart_data['movie1']}",
        headers={
            "Authorization": "Bearer invalid.jwt.token"
        },
    )

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_refresh_token_cannot_delete_movie(
    api_client,
    cart_data,
):
    response = await api_client.delete(
        f"/cart/items/{cart_data['movie1']}",
        headers=auth_headers(
            cart_data["user1"],
            token_type="refresh",
        ),
    )

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_inactive_user_cannot_delete_movie(
    api_client,
    db_session,
    cart_data,
):
    user_id = cart_data["user1"]

    await create_cart_with_movies(
        db_session,
        user_id,
        [cart_data["movie1"]],
    )

    user = await db_session.get(User, user_id)

    user.is_active = False
    await db_session.commit()

    response = await api_client.delete(
        f"/cart/items/{cart_data['movie1']}",
        headers=auth_headers(user_id),
    )

    assert response.status_code == 401


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "movie_id",
    ["0", "-1", "abc"],
)
async def test_invalid_movie_id(
    api_client,
    cart_data,
    movie_id,
):
    response = await api_client.delete(
        f"/cart/items/{movie_id}",
        headers=auth_headers(cart_data["user1"]),
    )

    assert response.status_code == 422

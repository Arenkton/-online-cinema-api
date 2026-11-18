from decimal import Decimal

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import selectinload

from src.models import (
    Cart,
    CartItem,
    Certification,
    Movie,
    User,
    UserGroup,
    UserGroupEnum,
)


@pytest_asyncio.fixture
async def user_and_movie(db_session):
    group = UserGroup(name=UserGroupEnum.USER.value)
    certification = Certification(name="PG-13")

    user = User(
        email="cart@example.com",
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
        description="Movie for cart tests",
        price=Decimal("9.99"),
        certification=certification,
    )

    db_session.add_all([user, movie])
    await db_session.commit()

    return user.id, movie.id


@pytest.mark.asyncio
async def test_create_cart(db_session, user_and_movie):
    user_id, _ = user_and_movie

    cart = Cart(user_id=user_id)

    db_session.add(cart)
    await db_session.commit()

    result = await db_session.execute(
        select(Cart)
        .options(selectinload(Cart.user))
        .where(Cart.user_id == user_id)
    )

    saved_cart = result.scalar_one()

    assert saved_cart.id is not None
    assert saved_cart.user_id == user_id
    assert saved_cart.user.id == user_id


@pytest.mark.asyncio
async def test_add_movie_to_cart(db_session, user_and_movie):
    user_id, movie_id = user_and_movie

    cart = Cart(user_id=user_id)
    item = CartItem(cart=cart, movie_id=movie_id)

    db_session.add(item)
    await db_session.commit()
    await db_session.refresh(item)

    assert item.id is not None
    assert item.cart_id == cart.id
    assert item.movie_id == movie_id
    assert item.added_at is not None

    result = await db_session.execute(
        select(Cart)
        .options(selectinload(Cart.items))
        .where(Cart.id == cart.id)
    )

    saved_cart = result.scalar_one()

    assert len(saved_cart.items) == 1
    assert saved_cart.items[0].movie_id == movie_id


@pytest.mark.asyncio
async def test_user_cannot_have_two_carts(
    db_session,
    user_and_movie,
):
    user_id, _ = user_and_movie

    db_session.add(Cart(user_id=user_id))
    await db_session.commit()

    db_session.add(Cart(user_id=user_id))

    with pytest.raises(IntegrityError):
        await db_session.commit()

    await db_session.rollback()


@pytest.mark.asyncio
async def test_duplicate_movie_in_cart(
    db_session,
    user_and_movie,
):
    user_id, movie_id = user_and_movie

    cart = Cart(user_id=user_id)
    db_session.add(cart)
    await db_session.commit()

    first_item = CartItem(
        cart_id=cart.id,
        movie_id=movie_id,
    )

    db_session.add(first_item)
    await db_session.commit()

    duplicate_item = CartItem(
        cart_id=cart.id,
        movie_id=movie_id,
    )

    db_session.add(duplicate_item)

    with pytest.raises(IntegrityError):
        await db_session.commit()

    await db_session.rollback()

from decimal import Decimal

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlalchemy.exc import IntegrityError

from src.models import (
    Certification,
    Movie,
    Order,
    OrderItem,
    User,
    UserGroup,
    UserGroupEnum,
)


@pytest_asyncio.fixture
async def order_data(db_session):
    group = UserGroup(name=UserGroupEnum.USER.value)
    certification = Certification(name="PG-13")

    user = User(
        email="orders@example.com",
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
        description="Movie for order tests",
        price=Decimal("9.99"),
        certification=certification,
    )

    db_session.add_all([user, movie])
    await db_session.commit()

    return user.id, movie.id


@pytest.mark.asyncio
async def test_create_order(db_session, order_data):
    user_id, movie_id = order_data

    order = Order(
        user_id=user_id,
        status="pending",
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

    result = await db_session.execute(
        select(Order)
        .options(selectinload(Order.items))
        .where(Order.id == order.id)
    )

    saved_order = result.scalar_one()

    assert saved_order.user_id == user_id
    assert saved_order.status == "pending"
    assert saved_order.created_at is not None
    assert saved_order.total_amount == Decimal("9.99")

    assert len(saved_order.items) == 1
    assert saved_order.items[0].movie_id == movie_id
    assert saved_order.items[0].price_at_order == Decimal("9.99")


@pytest.mark.asyncio
async def test_user_order_relationship(
    db_session,
    order_data,
):
    user_id, _ = order_data

    db_session.add(
        Order(
            user_id=user_id,
            status="pending",
            total_amount=Decimal("0.00"),
        )
    )

    await db_session.commit()

    result = await db_session.execute(
        select(User)
        .options(selectinload(User.orders))
        .where(User.id == user_id)
    )

    user = result.scalar_one()

    assert len(user.orders) == 1
    assert user.orders[0].status == "pending"


@pytest.mark.asyncio
async def test_order_price_does_not_change(
    db_session,
    order_data,
):
    user_id, movie_id = order_data

    order = Order(
        user_id=user_id,
        status="pending",
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

    movie = await db_session.get(Movie, movie_id)
    movie.price = Decimal("19.99")

    await db_session.commit()

    result = await db_session.execute(
        select(OrderItem).where(
            OrderItem.order_id == order.id
        )
    )

    saved_item = result.scalar_one()

    assert saved_item.price_at_order == Decimal("9.99")
    assert order.total_amount == Decimal("9.99")


@pytest.mark.asyncio
async def test_order_item_requires_price(
    db_session,
    order_data,
):
    user_id, movie_id = order_data

    order = Order(
        user_id=user_id,
        status="pending",
        items=[
            OrderItem(
                movie_id=movie_id,
                price_at_order=None,
            )
        ],
    )

    db_session.add(order)

    with pytest.raises(IntegrityError):
        await db_session.commit()

    await db_session.rollback()

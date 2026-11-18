from decimal import Decimal

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import selectinload

from src.models import (
    Certification,
    Movie,
    Order,
    OrderItem,
    Payment,
    PaymentItem,
    User,
    UserGroup,
    UserGroupEnum,
)


@pytest_asyncio.fixture
async def payment_data(db_session):
    group = UserGroup(name=UserGroupEnum.USER.value)
    certification = Certification(name="PG-13")

    user = User(
        email="payment@example.com",
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
        description="First payment test movie",
        price=Decimal("9.99"),
        certification=certification,
    )

    second_movie = Movie(
        name="Second Movie",
        year=2025,
        time=150,
        imdb=9.0,
        votes=2000,
        description="Second payment test movie",
        price=Decimal("12.50"),
        certification=certification,
    )

    db_session.add_all([user, first_movie, second_movie])
    await db_session.flush()

    order = Order(
        user_id=user.id,
        status="pending",
        total_amount=Decimal("22.49"),
        items=[
            OrderItem(
                movie_id=first_movie.id,
                price_at_order=Decimal("9.99"),
            ),
            OrderItem(
                movie_id=second_movie.id,
                price_at_order=Decimal("12.50"),
            ),
        ],
    )

    db_session.add(order)
    await db_session.flush()

    data = {
        "user_id": user.id,
        "order_id": order.id,
        "movie_id": first_movie.id,
        "order_item_ids": [item.id for item in order.items],
    }

    await db_session.commit()
    return data


@pytest.mark.asyncio
async def test_create_payment(db_session, payment_data):
    payment = Payment(
        user_id=payment_data["user_id"],
        order_id=payment_data["order_id"],
        status="pending",
        amount=Decimal("22.49"),
        items=[
            PaymentItem(
                order_item_id=payment_data["order_item_ids"][0],
                price_at_payment=Decimal("9.99"),
            ),
            PaymentItem(
                order_item_id=payment_data["order_item_ids"][1],
                price_at_payment=Decimal("12.50"),
            ),
        ],
    )

    db_session.add(payment)
    await db_session.flush()
    payment_id = payment.id
    await db_session.commit()

    result = await db_session.execute(
        select(Payment)
        .options(selectinload(Payment.items))
        .where(Payment.id == payment_id)
    )

    saved = result.scalar_one()

    assert saved.user_id == payment_data["user_id"]
    assert saved.order_id == payment_data["order_id"]
    assert saved.status == "pending"
    assert saved.amount == Decimal("22.49")
    assert saved.created_at is not None
    assert saved.external_payment_id is None

    assert len(saved.items) == 2

    prices = sorted(
        item.price_at_payment for item in saved.items
    )

    assert prices == [
        Decimal("9.99"),
        Decimal("12.50"),
    ]


@pytest.mark.asyncio
async def test_payment_relationships(db_session, payment_data):
    payment = Payment(
        user_id=payment_data["user_id"],
        order_id=payment_data["order_id"],
        status="pending",
        amount=Decimal("22.49"),
        external_payment_id="pi_test_123",
        items=[
            PaymentItem(
                order_item_id=payment_data["order_item_ids"][0],
                price_at_payment=Decimal("9.99"),
            ),
        ],
    )

    db_session.add(payment)
    await db_session.flush()
    payment_id = payment.id
    await db_session.commit()

    result = await db_session.execute(
        select(Payment)
        .options(
            selectinload(Payment.user),
            selectinload(Payment.order),
            selectinload(Payment.items).selectinload(
                PaymentItem.order_item
            ),
        )
        .where(Payment.id == payment_id)
    )

    saved = result.scalar_one()

    assert saved.user.id == payment_data["user_id"]
    assert saved.order.id == payment_data["order_id"]
    assert saved.external_payment_id == "pi_test_123"

    assert saved.items[0].order_item.id == (
        payment_data["order_item_ids"][0]
    )


@pytest.mark.asyncio
async def test_payment_price_does_not_change(
    db_session,
    payment_data,
):
    payment = Payment(
        user_id=payment_data["user_id"],
        order_id=payment_data["order_id"],
        status="pending",
        amount=Decimal("9.99"),
        items=[
            PaymentItem(
                order_item_id=payment_data["order_item_ids"][0],
                price_at_payment=Decimal("9.99"),
            ),
        ],
    )

    db_session.add(payment)
    await db_session.flush()
    payment_id = payment.id
    await db_session.commit()

    movie = await db_session.get(
        Movie,
        payment_data["movie_id"],
    )

    movie.price = Decimal("29.99")
    await db_session.commit()

    result = await db_session.execute(
        select(Payment)
        .options(selectinload(Payment.items))
        .where(Payment.id == payment_id)
    )

    saved = result.scalar_one()

    assert saved.amount == Decimal("9.99")
    assert saved.items[0].price_at_payment == Decimal("9.99")


@pytest.mark.asyncio
async def test_multiple_payment_attempts(
    db_session,
    payment_data,
):
    first = Payment(
        user_id=payment_data["user_id"],
        order_id=payment_data["order_id"],
        status="failed",
        amount=Decimal("22.49"),
    )

    second = Payment(
        user_id=payment_data["user_id"],
        order_id=payment_data["order_id"],
        status="pending",
        amount=Decimal("22.49"),
    )

    db_session.add_all([first, second])
    await db_session.commit()

    result = await db_session.execute(
        select(Order)
        .options(selectinload(Order.payments))
        .where(Order.id == payment_data["order_id"])
    )

    order = result.scalar_one()

    assert len(order.payments) == 2
    assert {payment.status for payment in order.payments} == {
        "failed",
        "pending",
    }


@pytest.mark.asyncio
async def test_payment_amount_is_required(
    db_session,
    payment_data,
):
    payment = Payment(
        user_id=payment_data["user_id"],
        order_id=payment_data["order_id"],
        status="pending",
        amount=None,
    )

    db_session.add(payment)

    with pytest.raises(IntegrityError):
        await db_session.commit()

    await db_session.rollback()


@pytest.mark.asyncio
async def test_payment_item_price_is_required(
    db_session,
    payment_data,
):
    payment = Payment(
        user_id=payment_data["user_id"],
        order_id=payment_data["order_id"],
        status="pending",
        amount=Decimal("9.99"),
        items=[
            PaymentItem(
                order_item_id=payment_data["order_item_ids"][0],
                price_at_payment=None,
            ),
        ],
    )

    db_session.add(payment)

    with pytest.raises(IntegrityError):
        await db_session.commit()

    await db_session.rollback()

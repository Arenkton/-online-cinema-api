from decimal import Decimal

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from src.jwt_service import create_jwt_token
from src.models import (
    Certification,
    Movie,
    Order,
    OrderItem,
    Payment,
    User,
    UserGroup,
    UserGroupEnum,
)


TEST_SECRET = "test-secret-key-for-jwt-unit-tests-123456789"


@pytest.fixture(autouse=True)
def jwt_secret(monkeypatch):
    monkeypatch.setenv("JWT_SECRET_KEY", TEST_SECRET)


@pytest_asyncio.fixture
async def payment_data(db_session):
    group = UserGroup(name=UserGroupEnum.USER.value)
    certification = Certification(name="PG-13")

    first_user = User(
        email="payments-first@example.com",
        hashed_password="test-password-hash",
        is_active=True,
        group=group,
    )

    second_user = User(
        email="payments-second@example.com",
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
        description="First payment API test movie",
        price=Decimal("9.99"),
        certification=certification,
    )

    second_movie = Movie(
        name="Second Movie",
        year=2025,
        time=150,
        imdb=9.0,
        votes=2000,
        description="Second payment API test movie",
        price=Decimal("12.50"),
        certification=certification,
    )

    db_session.add_all([
        first_user,
        second_user,
        first_movie,
        second_movie,
    ])

    await db_session.flush()

    order = Order(
        user_id=first_user.id,
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
        "user1": first_user.id,
        "user2": second_user.id,
        "order_id": order.id,
        "movie1": first_movie.id,
        "movie2": second_movie.id,
        "order_item_ids": [
            item.id for item in order.items
        ],
    }

    await db_session.commit()

    return data


def auth_headers(user_id, token_type="access"):
    token = create_jwt_token(user_id, token_type)

    return {
        "Authorization": f"Bearer {token}"
    }


async def send_payment_request(
    api_client,
    user_id,
    order_id,
):
    return await api_client.post(
        "/payments",
        json={"order_id": order_id},
        headers=auth_headers(user_id),
    )


@pytest.mark.asyncio
async def test_create_payment_success(
    api_client,
    db_session,
    payment_data,
):
    response = await send_payment_request(
        api_client,
        payment_data["user1"],
        payment_data["order_id"],
    )

    assert response.status_code == 201

    data = response.json()

    assert data["id"] is not None
    assert data["user_id"] == payment_data["user1"]
    assert data["order_id"] == payment_data["order_id"]
    assert data["status"] == "pending"
    assert data["created_at"] is not None
    assert data["external_payment_id"] is None

    assert Decimal(data["amount"]) == Decimal("22.49")
    assert len(data["items"]) == 2

    items_by_order_item = {
        item["order_item_id"]: item
        for item in data["items"]
    }

    first_id, second_id = payment_data["order_item_ids"]

    assert Decimal(
        items_by_order_item[first_id]["price_at_payment"]
    ) == Decimal("9.99")

    assert Decimal(
        items_by_order_item[second_id]["price_at_payment"]
    ) == Decimal("12.50")

    # Verify that payment and items were persisted.
    result = await db_session.execute(
        select(Payment)
        .options(selectinload(Payment.items))
        .where(Payment.id == data["id"])
    )

    saved_payment = result.scalar_one()

    assert saved_payment.status == "pending"
    assert saved_payment.amount == Decimal("22.49")
    assert len(saved_payment.items) == 2

    # Creating a payment must not mark the order as paid.
    order = await db_session.get(
        Order,
        payment_data["order_id"],
    )

    assert order.status == "pending"


@pytest.mark.asyncio
async def test_payment_uses_order_price_not_catalog_price(
    api_client,
    db_session,
    payment_data,
):
    movie = await db_session.get(
        Movie,
        payment_data["movie1"],
    )

    # The catalog price changes after order creation.
    movie.price = Decimal("29.99")
    await db_session.commit()

    response = await send_payment_request(
        api_client,
        payment_data["user1"],
        payment_data["order_id"],
    )

    assert response.status_code == 201

    data = response.json()

    assert Decimal(data["amount"]) == Decimal("22.49")

    items_by_order_item = {
        item["order_item_id"]: item
        for item in data["items"]
    }

    first_id = payment_data["order_item_ids"][0]

    assert Decimal(
        items_by_order_item[first_id]["price_at_payment"]
    ) == Decimal("9.99")


@pytest.mark.asyncio
async def test_duplicate_pending_payment_returns_409(
    api_client,
    db_session,
    payment_data,
):
    user_id = payment_data["user1"]
    order_id = payment_data["order_id"]

    first_response = await send_payment_request(
        api_client,
        user_id,
        order_id,
    )

    second_response = await send_payment_request(
        api_client,
        user_id,
        order_id,
    )

    assert first_response.status_code == 201
    assert second_response.status_code == 409

    result = await db_session.execute(
        select(Payment).where(
            Payment.order_id == order_id
        )
    )

    assert len(result.scalars().all()) == 1


@pytest.mark.asyncio
async def test_failed_payment_allows_new_attempt(
    api_client,
    db_session,
    payment_data,
):
    old_payment = Payment(
        user_id=payment_data["user1"],
        order_id=payment_data["order_id"],
        status="failed",
        amount=Decimal("22.49"),
    )

    db_session.add(old_payment)
    await db_session.commit()

    response = await send_payment_request(
        api_client,
        payment_data["user1"],
        payment_data["order_id"],
    )

    assert response.status_code == 201
    assert response.json()["status"] == "pending"

    result = await db_session.execute(
        select(Payment).where(
            Payment.order_id == payment_data["order_id"]
        )
    )

    payments = result.scalars().all()

    assert len(payments) == 2
    assert {p.status for p in payments} == {
        "failed",
        "pending",
    }


@pytest.mark.asyncio
async def test_existing_paid_payment_blocks_new_attempt(
    api_client,
    db_session,
    payment_data,
):
    payment = Payment(
        user_id=payment_data["user1"],
        order_id=payment_data["order_id"],
        status="paid",
        amount=Decimal("22.49"),
    )

    db_session.add(payment)
    await db_session.commit()

    response = await send_payment_request(
        api_client,
        payment_data["user1"],
        payment_data["order_id"],
    )

    assert response.status_code == 409


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "order_status",
    ["paid", "cancelled"],
)
async def test_non_pending_order_cannot_be_paid(
    api_client,
    db_session,
    payment_data,
    order_status,
):
    order = await db_session.get(
        Order,
        payment_data["order_id"],
    )

    order.status = order_status
    await db_session.commit()

    response = await send_payment_request(
        api_client,
        payment_data["user1"],
        payment_data["order_id"],
    )

    assert response.status_code == 409
    assert response.json()["detail"] == (
        "Order is not available for payment"
    )


@pytest.mark.asyncio
async def test_nonexistent_order_returns_404(
    api_client,
    payment_data,
):
    response = await send_payment_request(
        api_client,
        payment_data["user1"],
        999999,
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Order not found"


@pytest.mark.asyncio
async def test_cannot_pay_another_users_order(
    api_client,
    db_session,
    payment_data,
):
    response = await send_payment_request(
        api_client,
        payment_data["user2"],
        payment_data["order_id"],
    )

    assert response.status_code == 404

    result = await db_session.execute(
        select(Payment).where(
            Payment.order_id == payment_data["order_id"]
        )
    )

    assert result.scalars().all() == []


@pytest.mark.asyncio
async def test_order_without_items_returns_409(
    api_client,
    db_session,
    payment_data,
):
    empty_order = Order(
        user_id=payment_data["user1"],
        status="pending",
        total_amount=Decimal("0.00"),
    )

    db_session.add(empty_order)
    await db_session.commit()

    response = await send_payment_request(
        api_client,
        payment_data["user1"],
        empty_order.id,
    )

    assert response.status_code == 409
    assert response.json()["detail"] == (
        "Order has no items"
    )


@pytest.mark.asyncio
async def test_order_amount_mismatch_returns_409(
    api_client,
    db_session,
    payment_data,
):
    order = await db_session.get(
        Order,
        payment_data["order_id"],
    )

    order.total_amount = Decimal("20.00")
    await db_session.commit()

    response = await send_payment_request(
        api_client,
        payment_data["user1"],
        payment_data["order_id"],
    )

    assert response.status_code == 409
    assert response.json()["detail"] == (
        "Order amount is invalid"
    )

    result = await db_session.execute(select(Payment))

    assert result.scalars().all() == []


@pytest.mark.asyncio
async def test_order_without_total_returns_409(
    api_client,
    db_session,
    payment_data,
):
    order = await db_session.get(
        Order,
        payment_data["order_id"],
    )

    order.total_amount = None
    await db_session.commit()

    response = await send_payment_request(
        api_client,
        payment_data["user1"],
        payment_data["order_id"],
    )

    assert response.status_code == 409


@pytest.mark.asyncio
async def test_zero_amount_returns_409(
    api_client,
    db_session,
    payment_data,
):
    result = await db_session.execute(
        select(Order)
        .options(selectinload(Order.items))
        .where(Order.id == payment_data["order_id"])
    )

    order = result.scalar_one()

    order.total_amount = Decimal("0.00")

    for item in order.items:
        item.price_at_order = Decimal("0.00")

    await db_session.commit()

    response = await send_payment_request(
        api_client,
        payment_data["user1"],
        payment_data["order_id"],
    )

    assert response.status_code == 409


@pytest.mark.asyncio
async def test_create_payment_without_auth(api_client):
    response = await api_client.post(
        "/payments",
        json={"order_id": 1},
    )

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_create_payment_invalid_token(api_client):
    response = await api_client.post(
        "/payments",
        json={"order_id": 1},
        headers={
            "Authorization": "Bearer invalid.jwt.token"
        },
    )

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_refresh_token_cannot_create_payment(
    api_client,
    payment_data,
):
    response = await api_client.post(
        "/payments",
        json={"order_id": payment_data["order_id"]},
        headers=auth_headers(
            payment_data["user1"],
            token_type="refresh",
        ),
    )

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_inactive_user_cannot_create_payment(
    api_client,
    db_session,
    payment_data,
):
    user = await db_session.get(
        User,
        payment_data["user1"],
    )

    user.is_active = False
    await db_session.commit()

    response = await send_payment_request(
        api_client,
        payment_data["user1"],
        payment_data["order_id"],
    )

    assert response.status_code == 401


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "order_id",
    [0, -1, "abc"],
)
async def test_invalid_order_id(
    api_client,
    payment_data,
    order_id,
):
    response = await api_client.post(
        "/payments",
        json={"order_id": order_id},
        headers=auth_headers(payment_data["user1"]),
    )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_missing_order_id(
    api_client,
    payment_data,
):
    response = await api_client.post(
        "/payments",
        json={},
        headers=auth_headers(payment_data["user1"]),
    )

    assert response.status_code == 422

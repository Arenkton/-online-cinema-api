from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
import stripe
from sqlalchemy import delete, select

from src.jwt_service import create_jwt_token
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
from src.routers import payments as payments_router


TEST_SECRET = "test-secret-key-for-jwt-unit-tests-123456789"


@pytest.fixture(autouse=True)
def jwt_secret(monkeypatch):
    monkeypatch.setenv("JWT_SECRET_KEY", TEST_SECRET)


@pytest_asyncio.fixture
async def checkout_data(db_session):
    group = UserGroup(name=UserGroupEnum.USER.value)
    certification = Certification(name="PG-13")

    user1 = User(
        email="checkout-first@example.com",
        hashed_password="test-password-hash",
        is_active=True,
        group=group,
    )

    user2 = User(
        email="checkout-second@example.com",
        hashed_password="test-password-hash",
        is_active=True,
        group=group,
    )

    movie1 = Movie(
        name="Checkout Movie One",
        year=2024,
        time=120,
        imdb=8.5,
        votes=1000,
        description="First checkout movie",
        price=Decimal("9.99"),
        certification=certification,
    )

    movie2 = Movie(
        name="Checkout Movie Two",
        year=2025,
        time=130,
        imdb=9.0,
        votes=2000,
        description="Second checkout movie",
        price=Decimal("12.50"),
        certification=certification,
    )

    db_session.add_all([user1, user2, movie1, movie2])
    await db_session.flush()

    order = Order(
        user_id=user1.id,
        status="pending",
        total_amount=Decimal("22.49"),
        items=[
            OrderItem(
                movie_id=movie1.id,
                price_at_order=Decimal("9.99"),
            ),
            OrderItem(
                movie_id=movie2.id,
                price_at_order=Decimal("12.50"),
            ),
        ],
    )

    db_session.add(order)
    await db_session.flush()

    payment = Payment(
        user_id=user1.id,
        order_id=order.id,
        status="pending",
        amount=Decimal("22.49"),
        items=[
            PaymentItem(
                order_item_id=order.items[0].id,
                price_at_payment=Decimal("9.99"),
            ),
            PaymentItem(
                order_item_id=order.items[1].id,
                price_at_payment=Decimal("12.50"),
            ),
        ],
    )

    db_session.add(payment)
    await db_session.flush()

    data = {
        "user1": user1.id,
        "user2": user2.id,
        "order_id": order.id,
        "payment_id": payment.id,
        "movie1": movie1.id,
        "movie2": movie2.id,
    }

    await db_session.commit()
    return data


@pytest.fixture
def stripe_mock(monkeypatch):
    session = SimpleNamespace(
        id="cs_test_checkout_123",
        url="https://checkout.stripe.com/c/pay/test-session",
    )

    mock = AsyncMock(return_value=session)

    monkeypatch.setattr(
        payments_router,
        "create_checkout_session",
        mock,
    )

    return mock


def auth_headers(user_id, token_type="access"):
    token = create_jwt_token(user_id, token_type)

    return {
        "Authorization": f"Bearer {token}"
    }


async def request_checkout(
    api_client,
    user_id,
    payment_id,
):
    return await api_client.post(
        f"/payments/{payment_id}/checkout",
        headers=auth_headers(user_id),
    )


@pytest.mark.asyncio
async def test_create_checkout_session_success(
    api_client,
    db_session,
    checkout_data,
    stripe_mock,
):
    response = await request_checkout(
        api_client,
        checkout_data["user1"],
        checkout_data["payment_id"],
    )

    assert response.status_code == 200

    data = response.json()

    assert data["payment_id"] == checkout_data["payment_id"]
    assert data["session_id"] == "cs_test_checkout_123"
    assert data["checkout_url"].startswith(
        "https://checkout.stripe.com/"
    )

    stripe_mock.assert_awaited_once()

    call_kwargs = stripe_mock.await_args.kwargs

    assert call_kwargs["payment_id"] == checkout_data["payment_id"]
    assert call_kwargs["order_id"] == checkout_data["order_id"]

    line_items = call_kwargs["line_items"]

    assert len(line_items) == 2

    items_by_name = {
        item["price_data"]["product_data"]["name"]: item
        for item in line_items
    }

    first = items_by_name["Checkout Movie One"]
    second = items_by_name["Checkout Movie Two"]

    assert first["price_data"]["unit_amount"] == 999
    assert second["price_data"]["unit_amount"] == 1250

    assert first["price_data"]["currency"] == "pln"
    assert second["price_data"]["currency"] == "pln"

    assert first["quantity"] == 1
    assert second["quantity"] == 1

    # Verify the session ID was persisted.
    saved_session_id = await db_session.scalar(
        select(Payment.external_payment_id).where(
            Payment.id == checkout_data["payment_id"]
        )
    )

    assert saved_session_id == "cs_test_checkout_123"

    # Checkout creation must not mark anything as paid.
    payment = await db_session.get(
        Payment,
        checkout_data["payment_id"],
    )
    order = await db_session.get(
        Order,
        checkout_data["order_id"],
    )

    assert payment.status == "pending"
    assert order.status == "pending"


@pytest.mark.asyncio
async def test_checkout_uses_payment_price(
    api_client,
    db_session,
    checkout_data,
    stripe_mock,
):
    movie = await db_session.get(
        Movie,
        checkout_data["movie1"],
    )

    movie.price = Decimal("49.99")
    await db_session.commit()

    response = await request_checkout(
        api_client,
        checkout_data["user1"],
        checkout_data["payment_id"],
    )

    assert response.status_code == 200

    items = stripe_mock.await_args.kwargs["line_items"]

    amounts = sorted(
        item["price_data"]["unit_amount"]
        for item in items
    )

    # Original payment prices, not current catalog prices.
    assert amounts == [999, 1250]


@pytest.mark.asyncio
async def test_duplicate_checkout_returns_409(
    api_client,
    checkout_data,
    stripe_mock,
):
    first = await request_checkout(
        api_client,
        checkout_data["user1"],
        checkout_data["payment_id"],
    )

    second = await request_checkout(
        api_client,
        checkout_data["user1"],
        checkout_data["payment_id"],
    )

    assert first.status_code == 200
    assert second.status_code == 409

    stripe_mock.assert_awaited_once()


@pytest.mark.asyncio
async def test_nonexistent_payment_returns_404(
    api_client,
    checkout_data,
    stripe_mock,
):
    response = await request_checkout(
        api_client,
        checkout_data["user1"],
        999999,
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Payment not found"

    stripe_mock.assert_not_awaited()


@pytest.mark.asyncio
async def test_cannot_checkout_another_users_payment(
    api_client,
    checkout_data,
    stripe_mock,
):
    response = await request_checkout(
        api_client,
        checkout_data["user2"],
        checkout_data["payment_id"],
    )

    assert response.status_code == 404
    stripe_mock.assert_not_awaited()


@pytest.mark.asyncio
async def test_checkout_with_existing_session_returns_409(
    api_client,
    db_session,
    checkout_data,
    stripe_mock,
):
    payment = await db_session.get(
        Payment,
        checkout_data["payment_id"],
    )

    payment.external_payment_id = "cs_test_existing"
    await db_session.commit()

    response = await request_checkout(
        api_client,
        checkout_data["user1"],
        checkout_data["payment_id"],
    )

    assert response.status_code == 409
    stripe_mock.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "payment_status",
    ["failed", "paid"],
)
async def test_non_pending_payment_returns_409(
    api_client,
    db_session,
    checkout_data,
    stripe_mock,
    payment_status,
):
    payment = await db_session.get(
        Payment,
        checkout_data["payment_id"],
    )

    payment.status = payment_status
    await db_session.commit()

    response = await request_checkout(
        api_client,
        checkout_data["user1"],
        checkout_data["payment_id"],
    )

    assert response.status_code == 409
    stripe_mock.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "order_status",
    ["paid", "cancelled"],
)
async def test_non_pending_order_returns_409(
    api_client,
    db_session,
    checkout_data,
    stripe_mock,
    order_status,
):
    order = await db_session.get(
        Order,
        checkout_data["order_id"],
    )

    order.status = order_status
    await db_session.commit()

    response = await request_checkout(
        api_client,
        checkout_data["user1"],
        checkout_data["payment_id"],
    )

    assert response.status_code == 409
    stripe_mock.assert_not_awaited()


@pytest.mark.asyncio
async def test_checkout_without_items_returns_409(
    api_client,
    db_session,
    checkout_data,
    stripe_mock,
):
    await db_session.execute(
        delete(PaymentItem).where(
            PaymentItem.payment_id == checkout_data["payment_id"]
        )
    )
    await db_session.commit()

    # Clear cached ORM relationships after bulk delete.
    db_session.expire_all()

    response = await request_checkout(
        api_client,
        checkout_data["user1"],
        checkout_data["payment_id"],
    )

    assert response.status_code == 409
    stripe_mock.assert_not_awaited()


@pytest.mark.asyncio
async def test_checkout_amount_mismatch_returns_409(
    api_client,
    db_session,
    checkout_data,
    stripe_mock,
):
    payment = await db_session.get(
        Payment,
        checkout_data["payment_id"],
    )

    payment.amount = Decimal("20.00")
    await db_session.commit()

    response = await request_checkout(
        api_client,
        checkout_data["user1"],
        checkout_data["payment_id"],
    )

    assert response.status_code == 409
    stripe_mock.assert_not_awaited()


@pytest.mark.asyncio
async def test_checkout_invalid_item_price_returns_409(
    api_client,
    db_session,
    checkout_data,
    stripe_mock,
):
    item_id = await db_session.scalar(
        select(PaymentItem.id).where(
            PaymentItem.payment_id == checkout_data["payment_id"]
        ).limit(1)
    )

    item = await db_session.get(PaymentItem, item_id)
    item.price_at_payment = Decimal("0.00")
    await db_session.commit()

    response = await request_checkout(
        api_client,
        checkout_data["user1"],
        checkout_data["payment_id"],
    )

    assert response.status_code == 409
    stripe_mock.assert_not_awaited()


@pytest.mark.asyncio
async def test_stripe_error_returns_502(
    api_client,
    db_session,
    checkout_data,
    stripe_mock,
):
    stripe_mock.side_effect = stripe.APIError(
        "Temporary Stripe error"
    )

    response = await request_checkout(
        api_client,
        checkout_data["user1"],
        checkout_data["payment_id"],
    )

    assert response.status_code == 502
    assert response.json()["detail"] == (
        "Unable to create Stripe session"
    )

    saved_session_id = await db_session.scalar(
        select(Payment.external_payment_id).where(
            Payment.id == checkout_data["payment_id"]
        )
    )

    assert saved_session_id is None


@pytest.mark.asyncio
async def test_stripe_without_checkout_url_returns_502(
    api_client,
    db_session,
    checkout_data,
    stripe_mock,
):
    stripe_mock.return_value = SimpleNamespace(
        id="cs_test_without_url",
        url=None,
    )

    response = await request_checkout(
        api_client,
        checkout_data["user1"],
        checkout_data["payment_id"],
    )

    assert response.status_code == 502

    saved_session_id = await db_session.scalar(
        select(Payment.external_payment_id).where(
            Payment.id == checkout_data["payment_id"]
        )
    )

    assert saved_session_id is None


@pytest.mark.asyncio
async def test_checkout_without_auth(
    api_client,
    checkout_data,
    stripe_mock,
):
    response = await api_client.post(
        f"/payments/{checkout_data['payment_id']}/checkout"
    )

    assert response.status_code == 401
    stripe_mock.assert_not_awaited()


@pytest.mark.asyncio
async def test_checkout_with_invalid_token(
    api_client,
    checkout_data,
    stripe_mock,
):
    response = await api_client.post(
        f"/payments/{checkout_data['payment_id']}/checkout",
        headers={
            "Authorization": "Bearer invalid.jwt.token"
        },
    )

    assert response.status_code == 401
    stripe_mock.assert_not_awaited()


@pytest.mark.asyncio
async def test_refresh_token_cannot_start_checkout(
    api_client,
    checkout_data,
    stripe_mock,
):
    response = await api_client.post(
        f"/payments/{checkout_data['payment_id']}/checkout",
        headers=auth_headers(
            checkout_data["user1"],
            token_type="refresh",
        ),
    )

    assert response.status_code == 401
    stripe_mock.assert_not_awaited()


@pytest.mark.asyncio
async def test_inactive_user_cannot_start_checkout(
    api_client,
    db_session,
    checkout_data,
    stripe_mock,
):
    user = await db_session.get(
        User,
        checkout_data["user1"],
    )

    user.is_active = False
    await db_session.commit()

    response = await request_checkout(
        api_client,
        checkout_data["user1"],
        checkout_data["payment_id"],
    )

    assert response.status_code == 401
    stripe_mock.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "payment_id",
    ["0", "-1", "abc"],
)
async def test_invalid_checkout_payment_id(
    api_client,
    checkout_data,
    stripe_mock,
    payment_id,
):
    response = await request_checkout(
        api_client,
        checkout_data["user1"],
        payment_id,
    )

    assert response.status_code == 422
    stripe_mock.assert_not_awaited()


@pytest.mark.asyncio
async def test_zero_payment_amount_returns_409(
    api_client,
    db_session,
    checkout_data,
    stripe_mock,
):
    payment = await db_session.get(
        Payment,
        checkout_data["payment_id"],
    )

    payment.amount = Decimal("0.00")
    await db_session.commit()

    response = await request_checkout(
        api_client,
        checkout_data["user1"],
        checkout_data["payment_id"],
    )

    assert response.status_code == 409
    assert response.json()["detail"] == "Invalid payment amount"

    stripe_mock.assert_not_awaited()

from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
import stripe

from src.models import (
    Order,
    Payment,
    User,
    UserGroup,
    UserGroupEnum,
)
from tests.helpers import auth_headers, create_test_order


@pytest.fixture(autouse=True)
def jwt_secret(monkeypatch):
    monkeypatch.setenv(
        "JWT_SECRET_KEY",
        "test-secret-key-for-jwt-unit-tests-123456789",
    )


@pytest_asyncio.fixture
async def refund_data(db_session, cart_data):
    buyer_id, movie_id = cart_data

    order = await create_test_order(
        db_session,
        user_id=buyer_id,
        movie_id=movie_id,
        order_status="paid",
    )

    payment = Payment(
        user_id=buyer_id,
        order_id=order.id,
        status="paid",
        amount=Decimal("9.99"),
        external_payment_id="cs_test_refund",
        stripe_payment_intent_id="pi_test_refund",
    )

    admin = User(
        email="refund-admin@example.com",
        hashed_password="test-password-hash",
        is_active=True,
        group=UserGroup(name=UserGroupEnum.ADMIN.value),
    )

    db_session.add_all([payment, admin])
    await db_session.commit()

    return {
        "buyer_id": buyer_id,
        "admin_id": admin.id,
        "payment_id": payment.id,
        "order_id": order.id,
    }


def make_refund(status="succeeded"):
    return SimpleNamespace(
        id="re_test_refund",
        payment_intent="pi_test_refund",
        amount=999,
        currency="pln",
        status=status,
    )


@pytest.mark.asyncio
async def test_refund_success(
    api_client, db_session, refund_data, monkeypatch
):
    stripe_mock = AsyncMock(
        return_value=make_refund()
    )
    monkeypatch.setattr(
        "src.routers.admin_payments.create_stripe_refund",
        stripe_mock,
    )

    response = await api_client.post(
        f"/admin/payments/{refund_data['payment_id']}/refund",
        headers=auth_headers(refund_data["admin_id"]),
    )

    assert response.status_code == 200
    assert response.json()["refund_status"] == "succeeded"
    assert response.json()["payment_status"] == "refunded"
    assert response.json()["order_status"] == "refunded"

    stripe_mock.assert_awaited_once_with(
        payment_id=refund_data["payment_id"],
        payment_intent_id="pi_test_refund",
    )

    payment = await db_session.get(
        Payment, refund_data["payment_id"]
    )
    order = await db_session.get(
        Order, refund_data["order_id"]
    )

    await db_session.refresh(payment)
    await db_session.refresh(order)

    assert payment.stripe_refund_id == "re_test_refund"
    assert payment.status == "refunded"
    assert order.status == "refunded"


@pytest.mark.asyncio
async def test_pending_refund_does_not_change_order_status(
    api_client, db_session, refund_data, monkeypatch
):
    monkeypatch.setattr(
        "src.routers.admin_payments.create_stripe_refund",
        AsyncMock(return_value=make_refund("pending")),
    )

    response = await api_client.post(
        f"/admin/payments/{refund_data['payment_id']}/refund",
        headers=auth_headers(refund_data["admin_id"]),
    )

    assert response.status_code == 200
    assert response.json()["refund_status"] == "pending"
    assert response.json()["payment_status"] == "paid"
    assert response.json()["order_status"] == "paid"


@pytest.mark.asyncio
async def test_cannot_refund_twice(
    api_client, refund_data, monkeypatch
):
    stripe_mock = AsyncMock(
        return_value=make_refund()
    )
    monkeypatch.setattr(
        "src.routers.admin_payments.create_stripe_refund",
        stripe_mock,
    )

    url = (
        f"/admin/payments/{refund_data['payment_id']}/refund"
    )
    headers = auth_headers(refund_data["admin_id"])

    first = await api_client.post(url, headers=headers)
    second = await api_client.post(url, headers=headers)

    assert first.status_code == 200
    assert second.status_code == 409
    assert stripe_mock.await_count == 1


@pytest.mark.asyncio
async def test_cannot_refund_pending_payment(
    api_client, db_session, refund_data, monkeypatch
):
    payment = await db_session.get(
        Payment, refund_data["payment_id"]
    )
    order = await db_session.get(
        Order, refund_data["order_id"]
    )

    payment.status = "pending"
    order.status = "pending"
    await db_session.commit()

    stripe_mock = AsyncMock()
    monkeypatch.setattr(
        "src.routers.admin_payments.create_stripe_refund",
        stripe_mock,
    )

    response = await api_client.post(
        f"/admin/payments/{payment.id}/refund",
        headers=auth_headers(refund_data["admin_id"]),
    )

    assert response.status_code == 409
    stripe_mock.assert_not_awaited()


@pytest.mark.asyncio
async def test_regular_user_cannot_refund(
    api_client, refund_data
):
    response = await api_client.post(
        f"/admin/payments/{refund_data['payment_id']}/refund",
        headers=auth_headers(refund_data["buyer_id"]),
    )

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_moderator_cannot_refund(
    api_client, db_session, refund_data
):
    moderator = User(
        email="refund-moderator@example.com",
        hashed_password="test-password-hash",
        is_active=True,
        group=UserGroup(name=UserGroupEnum.MODERATOR.value),
    )
    db_session.add(moderator)
    await db_session.commit()

    response = await api_client.post(
        f"/admin/payments/{refund_data['payment_id']}/refund",
        headers=auth_headers(moderator.id),
    )

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_refund_requires_auth(
    api_client, refund_data
):
    response = await api_client.post(
        f"/admin/payments/{refund_data['payment_id']}/refund"
    )

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_refund_nonexistent_payment(
    api_client, refund_data
):
    response = await api_client.post(
        "/admin/payments/999999/refund",
        headers=auth_headers(refund_data["admin_id"]),
    )

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_stripe_refund_failure(
    api_client, db_session, refund_data, monkeypatch
):
    monkeypatch.setattr(
        "src.routers.admin_payments.create_stripe_refund",
        AsyncMock(
            side_effect=stripe.StripeError("Stripe unavailable")
        ),
    )

    response = await api_client.post(
        f"/admin/payments/{refund_data['payment_id']}/refund",
        headers=auth_headers(refund_data["admin_id"]),
    )

    assert response.status_code == 502

    payment = await db_session.get(
        Payment, refund_data["payment_id"]
    )
    await db_session.refresh(payment)

    assert payment.status == "paid"
    assert payment.stripe_refund_id is None


@pytest.mark.asyncio
async def test_refund_recovers_payment_intent(
    api_client, db_session, refund_data, monkeypatch
):
    payment = await db_session.get(
        Payment, refund_data["payment_id"]
    )
    payment.stripe_payment_intent_id = None
    await db_session.commit()

    intent_mock = AsyncMock(
        return_value="pi_test_refund"
    )
    monkeypatch.setattr(
        "src.routers.admin_payments.get_payment_intent_id",
        intent_mock,
    )
    monkeypatch.setattr(
        "src.routers.admin_payments.create_stripe_refund",
        AsyncMock(return_value=make_refund()),
    )

    response = await api_client.post(
        f"/admin/payments/{payment.id}/refund",
        headers=auth_headers(refund_data["admin_id"]),
    )

    assert response.status_code == 200
    intent_mock.assert_awaited_once_with(
        "cs_test_refund"
    )

    await db_session.refresh(payment)
    assert payment.stripe_payment_intent_id == "pi_test_refund"

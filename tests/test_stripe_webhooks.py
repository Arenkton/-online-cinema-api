import hashlib
import hmac
import json
import time
from decimal import Decimal

import pytest
import pytest_asyncio

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


WEBHOOK_SECRET = "whsec_test_webhook_secret"


@pytest.fixture(autouse=True)
def webhook_secret(monkeypatch):
    monkeypatch.setenv(
        "STRIPE_WEBHOOK_SECRET",
        WEBHOOK_SECRET,
    )


@pytest_asyncio.fixture
async def webhook_data(db_session):
    group = UserGroup(name=UserGroupEnum.USER.value)
    certification = Certification(name="PG-13")

    user = User(
        email="stripe-webhook@example.com",
        hashed_password="test-password-hash",
        is_active=True,
        group=group,
    )

    movie = Movie(
        name="Webhook Test Movie",
        year=2024,
        time=120,
        imdb=8.5,
        votes=1000,
        description="Movie for webhook tests",
        price=Decimal("9.99"),
        certification=certification,
    )

    db_session.add_all([user, movie])
    await db_session.flush()

    order = Order(
        user_id=user.id,
        status="pending",
        total_amount=Decimal("9.99"),
        items=[
            OrderItem(
                movie_id=movie.id,
                price_at_order=Decimal("9.99"),
            ),
        ],
    )

    db_session.add(order)
    await db_session.flush()

    payment = Payment(
        user_id=user.id,
        order_id=order.id,
        status="pending",
        amount=Decimal("9.99"),
        external_payment_id="cs_test_webhook_123",
    )

    db_session.add(payment)
    await db_session.flush()

    data = {
        "payment_id": payment.id,
        "order_id": order.id,
        "session_id": payment.external_payment_id,
    }

    await db_session.commit()
    return data


def make_event(
    webhook_data,
    event_type="checkout.session.completed",
    payment_status="paid",
):
    payment_id = webhook_data["payment_id"]
    order_id = webhook_data["order_id"]

    return {
        "id": "evt_test_123",
        "object": "event",
        "type": event_type,
        "data": {
            "object": {
                "id": webhook_data["session_id"],
                "object": "checkout.session",
                "mode": "payment",
                "currency": "pln",
                "amount_total": 999,
                "payment_status": payment_status,
                "client_reference_id": str(payment_id),
                "metadata": {
                    "payment_id": str(payment_id),
                    "order_id": str(order_id),
                },
            },
        },
    }


def sign_event(
    event,
    secret=WEBHOOK_SECRET,
    timestamp=None,
):
    if timestamp is None:
        timestamp = int(time.time())

    payload = json.dumps(
        event,
        separators=(",", ":"),
    ).encode("utf-8")

    signed_payload = (
        f"{timestamp}.".encode("utf-8") + payload
    )

    signature = hmac.new(
        secret.encode("utf-8"),
        signed_payload,
        hashlib.sha256,
    ).hexdigest()

    headers = {
        "Stripe-Signature": (
            f"t={timestamp},v1={signature}"
        ),
        "Content-Type": "application/json",
    }

    return payload, headers


async def send_event(api_client, event):
    payload, headers = sign_event(event)

    return await api_client.post(
        "/webhooks/stripe",
        content=payload,
        headers=headers,
    )


async def get_statuses(db_session, webhook_data):
    payment = await db_session.get(
        Payment,
        webhook_data["payment_id"],
    )

    order = await db_session.get(
        Order,
        webhook_data["order_id"],
    )

    await db_session.refresh(payment)
    await db_session.refresh(order)

    return payment.status, order.status


@pytest.mark.asyncio
async def test_completed_payment_marks_order_paid(
    api_client,
    db_session,
    webhook_data,
):
    event = make_event(webhook_data)

    response = await send_event(api_client, event)

    assert response.status_code == 200
    assert response.json() == {
        "received": True,
        "processed": True,
    }

    assert await get_statuses(
        db_session,
        webhook_data,
    ) == ("paid", "paid")


@pytest.mark.asyncio
async def test_async_payment_succeeded(
    api_client,
    db_session,
    webhook_data,
):
    event = make_event(
        webhook_data,
        event_type="checkout.session.async_payment_succeeded",
    )

    response = await send_event(api_client, event)

    assert response.status_code == 200

    assert await get_statuses(
        db_session,
        webhook_data,
    ) == ("paid", "paid")


@pytest.mark.asyncio
async def test_completed_but_unpaid_does_not_confirm_order(
    api_client,
    db_session,
    webhook_data,
):
    event = make_event(
        webhook_data,
        payment_status="unpaid",
    )

    response = await send_event(api_client, event)

    assert response.status_code == 200
    assert response.json()["processed"] is False

    assert await get_statuses(
        db_session,
        webhook_data,
    ) == ("pending", "pending")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("event_type", "expected_status"),
    [
        ("checkout.session.async_payment_failed", "failed"),
        ("checkout.session.expired", "expired"),
    ],
)
async def test_failed_or_expired_checkout(
    api_client,
    db_session,
    webhook_data,
    event_type,
    expected_status,
):
    event = make_event(
        webhook_data,
        event_type=event_type,
        payment_status="unpaid",
    )

    response = await send_event(api_client, event)

    assert response.status_code == 200
    assert response.json()["processed"] is True

    assert await get_statuses(
        db_session,
        webhook_data,
    ) == (expected_status, "pending")


@pytest.mark.asyncio
async def test_duplicate_success_event_is_idempotent(
    api_client,
    db_session,
    webhook_data,
):
    event = make_event(webhook_data)

    first_response = await send_event(api_client, event)
    second_response = await send_event(api_client, event)

    assert first_response.status_code == 200
    assert first_response.json()["processed"] is True

    assert second_response.status_code == 200
    assert second_response.json()["processed"] is False

    assert await get_statuses(
        db_session,
        webhook_data,
    ) == ("paid", "paid")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "event_type",
    [
        "checkout.session.async_payment_failed",
        "checkout.session.expired",
    ],
)
async def test_duplicate_unsuccessful_event(
    api_client,
    db_session,
    webhook_data,
    event_type,
):
    event = make_event(
        webhook_data,
        event_type=event_type,
        payment_status="unpaid",
    )

    first_response = await send_event(api_client, event)
    second_response = await send_event(api_client, event)

    assert first_response.status_code == 200
    assert first_response.json()["processed"] is True

    assert second_response.status_code == 200
    assert second_response.json()["processed"] is False


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "event_type",
    [
        "checkout.session.async_payment_failed",
        "checkout.session.expired",
    ],
)
async def test_failure_cannot_overwrite_paid_payment(
    api_client,
    db_session,
    webhook_data,
    event_type,
):
    payment = await db_session.get(
        Payment,
        webhook_data["payment_id"],
    )
    order = await db_session.get(
        Order,
        webhook_data["order_id"],
    )

    payment.status = "paid"
    order.status = "paid"
    await db_session.commit()

    event = make_event(
        webhook_data,
        event_type=event_type,
        payment_status="unpaid",
    )

    response = await send_event(api_client, event)

    assert response.status_code == 200
    assert response.json()["processed"] is False

    assert await get_statuses(
        db_session,
        webhook_data,
    ) == ("paid", "paid")


@pytest.mark.asyncio
async def test_unhandled_event_is_ignored(
    api_client,
    db_session,
    webhook_data,
):
    event = make_event(
        webhook_data,
        event_type="customer.created",
    )

    response = await send_event(api_client, event)

    assert response.status_code == 200
    assert response.json() == {
        "received": True,
        "processed": False,
    }

    assert await get_statuses(
        db_session,
        webhook_data,
    ) == ("pending", "pending")


@pytest.mark.asyncio
async def test_invalid_signature_returns_400(
    api_client,
    db_session,
    webhook_data,
):
    event = make_event(webhook_data)

    payload, headers = sign_event(
        event,
        secret="whsec_wrong_secret",
    )

    response = await api_client.post(
        "/webhooks/stripe",
        content=payload,
        headers=headers,
    )

    assert response.status_code == 400

    assert await get_statuses(
        db_session,
        webhook_data,
    ) == ("pending", "pending")


@pytest.mark.asyncio
async def test_tampered_payload_returns_400(
    api_client,
    db_session,
    webhook_data,
):
    event = make_event(webhook_data)

    payload, headers = sign_event(event)

    tampered_payload = payload.replace(
        b'"amount_total":999',
        b'"amount_total":1000',
    )

    assert tampered_payload != payload

    response = await api_client.post(
        "/webhooks/stripe",
        content=tampered_payload,
        headers=headers,
    )

    assert response.status_code == 400

    assert await get_statuses(
        db_session,
        webhook_data,
    ) == ("pending", "pending")


@pytest.mark.asyncio
async def test_missing_signature_returns_400(
    api_client,
    webhook_data,
):
    event = make_event(webhook_data)

    payload, _ = sign_event(event)

    response = await api_client.post(
        "/webhooks/stripe",
        content=payload,
        headers={"Content-Type": "application/json"},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == (
        "Missing Stripe-Signature header"
    )


@pytest.mark.asyncio
async def test_expired_signature_returns_400(
    api_client,
    webhook_data,
):
    event = make_event(webhook_data)

    payload, headers = sign_event(
        event,
        timestamp=int(time.time()) - 3600,
    )

    response = await api_client.post(
        "/webhooks/stripe",
        content=payload,
        headers=headers,
    )

    assert response.status_code == 400


@pytest.mark.asyncio
async def test_missing_webhook_secret_returns_503(
    api_client,
    webhook_data,
    monkeypatch,
):
    monkeypatch.delenv(
        "STRIPE_WEBHOOK_SECRET",
        raising=False,
    )

    event = make_event(webhook_data)

    response = await send_event(api_client, event)

    assert response.status_code == 503
    assert response.json()["detail"] == (
        "Stripe webhook is not configured"
    )


@pytest.mark.asyncio
async def test_missing_session_id_returns_400(
    api_client,
    webhook_data,
):
    event = make_event(webhook_data)
    event["data"]["object"].pop("id")

    response = await send_event(api_client, event)

    assert response.status_code == 400
    assert response.json()["detail"] == (
        "Missing Checkout Session ID"
    )


@pytest.mark.asyncio
async def test_unknown_session_returns_503(
    api_client,
    db_session,
    webhook_data,
):
    event = make_event(webhook_data)
    event["data"]["object"]["id"] = (
        "cs_test_unknown_session"
    )

    response = await send_event(api_client, event)

    assert response.status_code == 503
    assert response.json()["detail"] == (
        "Payment not yet available"
    )

    assert await get_statuses(
        db_session,
        webhook_data,
    ) == ("pending", "pending")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "invalid_field",
    [
        "mode",
        "currency",
        "amount_total",
        "client_reference_id",
        "payment_id",
        "order_id",
    ],
)
async def test_mismatched_stripe_data_returns_409(
    api_client,
    db_session,
    webhook_data,
    invalid_field,
):
    event = make_event(webhook_data)
    session = event["data"]["object"]

    invalid_values = {
        "mode": "subscription",
        "currency": "usd",
        "amount_total": 1000,
        "client_reference_id": "incorrect",
    }

    if invalid_field in ("payment_id", "order_id"):
        session["metadata"][invalid_field] = "incorrect"
    else:
        session[invalid_field] = invalid_values[invalid_field]

    response = await send_event(api_client, event)

    assert response.status_code == 409
    assert response.json()["detail"] == (
        "Stripe payment data mismatch"
    )

    assert await get_statuses(
        db_session,
        webhook_data,
    ) == ("pending", "pending")


@pytest.mark.asyncio
async def test_invalid_stored_amount_returns_409(
    api_client,
    db_session,
    webhook_data,
):
    payment = await db_session.get(
        Payment,
        webhook_data["payment_id"],
    )

    payment.amount = Decimal("0.00")
    await db_session.commit()

    event = make_event(webhook_data)

    response = await send_event(api_client, event)

    assert response.status_code == 409
    assert response.json()["detail"] == (
        "Invalid stored payment amount"
    )


@pytest.mark.asyncio
async def test_order_amount_mismatch_returns_409(
    api_client,
    db_session,
    webhook_data,
):
    order = await db_session.get(
        Order,
        webhook_data["order_id"],
    )

    order.total_amount = Decimal("19.99")
    await db_session.commit()

    event = make_event(webhook_data)

    response = await send_event(api_client, event)

    assert response.status_code == 409
    assert response.json()["detail"] == (
        "Stripe payment data mismatch"
    )


@pytest.mark.asyncio
async def test_success_after_failed_payment_returns_409(
    api_client,
    db_session,
    webhook_data,
):
    payment = await db_session.get(
        Payment,
        webhook_data["payment_id"],
    )

    payment.status = "failed"
    await db_session.commit()

    event = make_event(webhook_data)

    response = await send_event(api_client, event)

    assert response.status_code == 409
    assert response.json()["detail"] == (
        "Unexpected payment state"
    )

    assert await get_statuses(
        db_session,
        webhook_data,
    ) == ("failed", "pending")


@pytest.mark.asyncio
async def test_inconsistent_paid_state_returns_409(
    api_client,
    db_session,
    webhook_data,
):
    payment = await db_session.get(
        Payment,
        webhook_data["payment_id"],
    )

    payment.status = "paid"
    await db_session.commit()

    event = make_event(webhook_data)

    response = await send_event(api_client, event)

    assert response.status_code == 409
    assert response.json()["detail"] == (
        "Unexpected payment state"
    )

    assert await get_statuses(
        db_session,
        webhook_data,
    ) == ("paid", "pending")

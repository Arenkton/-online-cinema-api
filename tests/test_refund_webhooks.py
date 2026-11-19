from decimal import Decimal

import pytest
import pytest_asyncio

from src.models import Order, Payment
from tests.helpers import create_test_order


@pytest_asyncio.fixture
async def refund_webhook_data(db_session, cart_data):
    user_id, movie_id = cart_data

    order = await create_test_order(
        db_session,
        user_id=user_id,
        movie_id=movie_id,
        order_status="paid",
    )

    payment = Payment(
        user_id=user_id,
        order_id=order.id,
        status="paid",
        amount=Decimal("9.99"),
        external_payment_id="cs_test_refund_webhook",
        stripe_payment_intent_id="pi_test_refund_webhook",
        stripe_refund_id="re_test_refund_webhook",
        refund_status="pending",
    )

    db_session.add(payment)
    await db_session.commit()

    return {
        "payment_id": payment.id,
        "order_id": order.id,
    }


@pytest.fixture
def send_refund_webhook(api_client, monkeypatch):
    monkeypatch.setenv(
        "STRIPE_WEBHOOK_SECRET",
        "whsec_test_refund",
    )

    async def send(
        payment_id,
        refund_status="succeeded",
        event_type="refund.updated",
        refund_id="re_test_refund_webhook",
        payment_intent="pi_test_refund_webhook",
        amount=999,
        currency="pln",
        metadata=None,
    ):
        if metadata is None:
            metadata = {
                "payment_id": str(payment_id),
            }

        event = {
            "id": "evt_test_refund",
            "type": event_type,
            "data": {
                "object": {
                    "id": refund_id,
                    "object": "refund",
                    "status": refund_status,
                    "payment_intent": payment_intent,
                    "amount": amount,
                    "currency": currency,
                    "metadata": metadata,
                },
            },
        }

        monkeypatch.setattr(
            "src.routers.stripe_webhooks."
            "stripe.Webhook.construct_event",
            lambda *args, **kwargs: event,
        )

        return await api_client.post(
            "/webhooks/stripe",
            content=b"{}",
            headers={"stripe-signature": "test"},
        )

    return send


@pytest.mark.asyncio
async def test_refund_webhook_success(
    db_session,
    refund_webhook_data,
    send_refund_webhook,
):
    response = await send_refund_webhook(
        refund_webhook_data["payment_id"],
        refund_status="succeeded",
    )

    assert response.status_code == 200

    payment = await db_session.get(
        Payment,
        refund_webhook_data["payment_id"],
    )
    order = await db_session.get(
        Order,
        refund_webhook_data["order_id"],
    )

    await db_session.refresh(payment)
    await db_session.refresh(order)

    assert payment.refund_status == "succeeded"
    assert payment.status == "refunded"
    assert order.status == "refunded"


@pytest.mark.asyncio
async def test_refund_webhook_failed(
    db_session,
    refund_webhook_data,
    send_refund_webhook,
):
    response = await send_refund_webhook(
        refund_webhook_data["payment_id"],
        refund_status="failed",
        event_type="refund.failed",
    )

    assert response.status_code == 200

    payment = await db_session.get(
        Payment,
        refund_webhook_data["payment_id"],
    )
    order = await db_session.get(
        Order,
        refund_webhook_data["order_id"],
    )

    await db_session.refresh(payment)
    await db_session.refresh(order)

    assert payment.refund_status == "failed"
    assert payment.status == "paid"
    assert order.status == "paid"


@pytest.mark.asyncio
async def test_refund_webhook_pending(
    db_session,
    refund_webhook_data,
    send_refund_webhook,
):
    response = await send_refund_webhook(
        refund_webhook_data["payment_id"],
        refund_status="pending",
    )

    assert response.status_code == 200

    payment = await db_session.get(
        Payment,
        refund_webhook_data["payment_id"],
    )
    order = await db_session.get(
        Order,
        refund_webhook_data["order_id"],
    )

    await db_session.refresh(payment)
    await db_session.refresh(order)

    assert payment.refund_status == "pending"
    assert payment.status == "paid"
    assert order.status == "paid"


@pytest.mark.asyncio
async def test_duplicate_refund_webhook(
    db_session,
    refund_webhook_data,
    send_refund_webhook,
):
    payment_id = refund_webhook_data["payment_id"]

    first = await send_refund_webhook(payment_id)
    second = await send_refund_webhook(payment_id)

    assert first.status_code == 200
    assert second.status_code == 200

    payment = await db_session.get(Payment, payment_id)
    await db_session.refresh(payment)

    assert payment.status == "refunded"
    assert payment.refund_status == "succeeded"


@pytest.mark.asyncio
async def test_old_pending_event_does_not_revert_refund(
    db_session,
    refund_webhook_data,
    send_refund_webhook,
):
    payment_id = refund_webhook_data["payment_id"]

    success = await send_refund_webhook(
        payment_id,
        refund_status="succeeded",
    )

    old_event = await send_refund_webhook(
        payment_id,
        refund_status="pending",
    )

    assert success.status_code == 200
    assert old_event.status_code == 200
    assert old_event.json()["processed"] is False

    payment = await db_session.get(Payment, payment_id)
    await db_session.refresh(payment)

    assert payment.status == "refunded"
    assert payment.refund_status == "succeeded"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "overrides",
    [
        {"amount": 1000},
        {"currency": "eur"},
        {"payment_intent": "pi_wrong_payment"},
    ],
)
async def test_refund_webhook_rejects_mismatched_data(
    db_session,
    refund_webhook_data,
    send_refund_webhook,
    overrides,
):
    payment_id = refund_webhook_data["payment_id"]

    response = await send_refund_webhook(
        payment_id,
        **overrides,
    )

    assert response.status_code == 409

    payment = await db_session.get(Payment, payment_id)
    await db_session.refresh(payment)

    assert payment.status == "paid"
    assert payment.refund_status == "pending"


@pytest.mark.asyncio
async def test_unrelated_refund_is_ignored(
    db_session,
    refund_webhook_data,
    send_refund_webhook,
):
    payment_id = refund_webhook_data["payment_id"]

    response = await send_refund_webhook(
        payment_id,
        refund_id="re_another_refund",
    )

    assert response.status_code == 200
    assert response.json()["processed"] is False

    payment = await db_session.get(Payment, payment_id)
    await db_session.refresh(payment)

    assert payment.refund_status == "pending"

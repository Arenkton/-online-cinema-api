from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from src import stripe_service


@pytest.mark.parametrize(
    ("amount", "expected"),
    [
        (Decimal("9.99"), 999),
        (Decimal("12.50"), 1250),
        (Decimal("0.01"), 1),
        (Decimal("100.00"), 10000),
    ],
)
def test_to_minor_units(amount, expected):
    assert stripe_service.to_minor_units(amount) == expected


@pytest.mark.parametrize(
    "amount",
    [
        Decimal("0.00"),
        Decimal("-1.00"),
        Decimal("9.999"),
        Decimal("0.001"),
    ],
)
def test_to_minor_units_rejects_invalid_amount(amount):
    with pytest.raises(ValueError):
        stripe_service.to_minor_units(amount)


@pytest.mark.asyncio
async def test_create_checkout_session_calls_stripe(
    monkeypatch,
):
    monkeypatch.setenv(
        "STRIPE_SECRET_KEY",
        "sk_test_unit_test_key",
    )
    monkeypatch.setenv("STRIPE_CURRENCY", "pln")
    monkeypatch.setenv(
        "STRIPE_SUCCESS_URL",
        "http://127.0.0.1:8000/success",
    )
    monkeypatch.setenv(
        "STRIPE_CANCEL_URL",
        "http://127.0.0.1:8000/cancel",
    )

    fake_session = SimpleNamespace(
        id="cs_test_123",
        url="https://checkout.stripe.com/test",
    )

    client = MagicMock()

    client.v1.checkout.sessions.create_async = AsyncMock(
        return_value=fake_session,
    )

    client_constructor = MagicMock(return_value=client)

    monkeypatch.setattr(
        stripe_service,
        "StripeClient",
        client_constructor,
    )

    line_items = [
        {
            "price_data": {
                "currency": "pln",
                "product_data": {
                    "name": "Test Movie",
                },
                "unit_amount": 999,
            },
            "quantity": 1,
        }
    ]

    result = await stripe_service.create_checkout_session(
        payment_id=10,
        order_id=20,
        line_items=line_items,
    )

    assert result.id == "cs_test_123"

    client_constructor.assert_called_once_with(
        "sk_test_unit_test_key"
    )

    create_mock = client.v1.checkout.sessions.create_async
    create_mock.assert_awaited_once()

    call = create_mock.await_args

    params = call.args[0]

    assert params["mode"] == "payment"
    assert params["line_items"] == line_items
    assert params["client_reference_id"] == "10"
    assert params["metadata"]["payment_id"] == "10"
    assert params["metadata"]["order_id"] == "20"

    assert params["success_url"] == (
        "http://127.0.0.1:8000/success"
    )

    assert params["cancel_url"] == (
        "http://127.0.0.1:8000/cancel"
    )

    assert call.kwargs["options"]["idempotency_key"] == (
        "checkout-payment-10"
    )


@pytest.mark.asyncio
async def test_checkout_service_rejects_live_key(
    monkeypatch,
):
    monkeypatch.setenv(
        "STRIPE_SECRET_KEY",
        "sk_live_not_allowed",
    )

    with pytest.raises(
        RuntimeError,
        match="Valid Stripe test secret key is required",
    ):
        await stripe_service.create_checkout_session(
            payment_id=1,
            order_id=1,
            line_items=[],
        )


@pytest.mark.asyncio
async def test_checkout_service_requires_urls(
    monkeypatch,
):
    monkeypatch.setenv(
        "STRIPE_SECRET_KEY",
        "sk_test_unit_test_key",
    )

    monkeypatch.setenv("STRIPE_CURRENCY", "pln")
    monkeypatch.delenv("STRIPE_SUCCESS_URL", raising=False)
    monkeypatch.delenv("STRIPE_CANCEL_URL", raising=False)

    with pytest.raises(
        RuntimeError,
        match="Stripe redirect URLs are not configured",
    ):
        await stripe_service.create_checkout_session(
            payment_id=1,
            order_id=1,
            line_items=[],
        )

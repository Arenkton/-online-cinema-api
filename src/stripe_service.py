import os
from decimal import Decimal

from stripe import StripeClient


def to_minor_units(amount: Decimal) -> int:
    value = amount * 100

    if (
        amount <= 0
        or value != value.to_integral_value()
    ):
        raise ValueError("Invalid payment amount")

    return int(value)


async def create_checkout_session(
    payment_id: int,
    order_id: int,
    line_items: list[dict],
):
    secret_key = os.getenv("STRIPE_SECRET_KEY")

    if not secret_key or not secret_key.startswith("sk_test_"):
        raise RuntimeError(
            "Valid Stripe test secret key is required"
        )

    currency = os.getenv("STRIPE_CURRENCY", "pln").lower()

    if currency not in {"pln", "eur", "usd"}:
        raise RuntimeError(
            "Unsupported two-decimal test currency"
        )

    success_url = os.getenv("STRIPE_SUCCESS_URL")
    cancel_url = os.getenv("STRIPE_CANCEL_URL")

    if not success_url or not cancel_url:
        raise RuntimeError(
            "Stripe redirect URLs are not configured"
        )

    client = StripeClient(secret_key)

    return await client.v1.checkout.sessions.create_async(
        {
            "mode": "payment",
            "line_items": line_items,
            "success_url": success_url,
            "cancel_url": cancel_url,
            "client_reference_id": str(payment_id),
            "metadata": {
                "payment_id": str(payment_id),
                "order_id": str(order_id),
            },
        },
        options={
            "idempotency_key": f"checkout-payment-{payment_id}",
        },
    )


async def get_payment_intent_id(
    checkout_session_id: str,
) -> str:
    secret_key = os.getenv("STRIPE_SECRET_KEY")

    if not secret_key or not secret_key.startswith("sk_test_"):
        raise RuntimeError(
            "Valid Stripe test secret key is required"
        )

    client = StripeClient(secret_key)

    session = await client.v1.checkout.sessions.retrieve_async(
        checkout_session_id,
    )

    payment_intent = session.payment_intent

    if isinstance(payment_intent, str):
        return payment_intent

    intent_id = getattr(payment_intent, "id", None)

    if not intent_id:
        raise ValueError(
            "Checkout Session has no PaymentIntent"
        )

    return intent_id


async def create_stripe_refund(
    payment_id: int,
    payment_intent_id: str,
):
    secret_key = os.getenv("STRIPE_SECRET_KEY")

    if not secret_key or not secret_key.startswith("sk_test_"):
        raise RuntimeError(
            "Valid Stripe test secret key is required"
        )

    client = StripeClient(secret_key)

    return await client.v1.refunds.create_async(
        {
            "payment_intent": payment_intent_id,
            "reason": "requested_by_customer",
            "metadata": {
                "payment_id": str(payment_id),
            },
        },
        options={
            "idempotency_key": (
                f"refund-payment-{payment_id}"
            ),
        },
    )

import os

import stripe
from fastapi import(
    APIRouter,
    Depends,
    HTTPException,
    Request,
    BackgroundTasks,
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.database import get_db
from src.models import(
    Payment,
    Movie,
    OrderItem,
    User,
)
from src.stripe_service import to_minor_units
from src.email_service import send_order_confirmation_email


router = APIRouter(
    prefix="/webhooks",
    tags=["Stripe Webhooks"],
)

HANDLED_EVENTS = {
    "checkout.session.completed",
    "checkout.session.async_payment_succeeded",
    "checkout.session.async_payment_failed",
    "checkout.session.expired",
}


@router.post("/stripe")
async def stripe_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    # 1. Get webhook signing secret.
    webhook_secret = os.getenv("STRIPE_WEBHOOK_SECRET")

    if not webhook_secret:
        raise HTTPException(
            status_code=503,
            detail="Stripe webhook is not configured",
        )

    # 2. Verify Stripe signature.
    payload = await request.body()
    signature = request.headers.get("Stripe-Signature")

    if not signature:
        raise HTTPException(
            status_code=400,
            detail="Missing Stripe-Signature header",
        )

    try:
        event = stripe.Webhook.construct_event(
            payload,
            signature,
            webhook_secret,
        )
    except (
        ValueError,
        stripe.SignatureVerificationError,
    ) as exc:
        raise HTTPException(
            status_code=400,
            detail="Invalid Stripe webhook signature or payload",
        ) from exc

    event_type = event["type"]

    # Ignore events that we do not handle.
    if event_type not in HANDLED_EVENTS:
        return {
            "received": True,
            "processed": False,
        }

    # 3. Find payment by Stripe Checkout Session ID.
    session = event["data"]["object"].to_dict()
    session_id = session.get("id")

    if not session_id:
        raise HTTPException(
            status_code=400,
            detail="Missing Checkout Session ID",
        )

    result = await db.execute(
        select(Payment)
        .options(selectinload(Payment.order))
        .where(
            Payment.external_payment_id == session_id
        )
        .with_for_update()
    )

    payment = result.scalar_one_or_none()

    if payment is None:
        raise HTTPException(
            status_code=503,
            detail="Payment not yet available",
        )

    order = payment.order

    # 4. Validate payment amount and Stripe metadata.
    try:
        expected_amount = to_minor_units(payment.amount)
    except (ValueError, TypeError) as exc:
        raise HTTPException(
            status_code=409,
            detail="Invalid stored payment amount",
        ) from exc

    metadata = session.get("metadata") or {}

    if (
        session.get("mode") != "payment"
        or session.get("currency") != "pln"
        or session.get("amount_total") != expected_amount
        or session.get("client_reference_id") != str(payment.id)
        or metadata.get("payment_id") != str(payment.id)
        or metadata.get("order_id") != str(order.id)
        or payment.user_id != order.user_id
        or payment.order_id != order.id
        or payment.amount != order.total_amount
    ):
        raise HTTPException(
            status_code=409,
            detail="Stripe payment data mismatch",
        )

    confirmation_email = None


    # 5. Handle successful payment.
    confirmation_email = None

    if event_type in {
        "checkout.session.completed",
        "checkout.session.async_payment_succeeded",
    }:
        if session.get("payment_status") != "paid":
            return {
                "received": True,
                "processed": False,
            }

        # Already processed successfully.
        if payment.status == "paid" and order.status == "paid":
            return {
                "received": True,
                "processed": False,
            }

        if (
            payment.status != "pending"
            or order.status != "pending"
        ):
            raise HTTPException(
                status_code=409,
                detail="Unexpected payment state",
            )

        payment.status = "paid"
        order.status = "paid"

        # Prepare confirmation email only for new successful payments.
        recipient = await db.scalar(
            select(User.email).where(
                User.id == order.user_id
            )
        )

        result = await db.execute(
            select(
                Movie.name,
                OrderItem.price_at_order,
            )
            .join(
                OrderItem,
                OrderItem.movie_id == Movie.id,
            )
            .where(
                OrderItem.order_id == order.id
            )
        )

        movies = list(result.all())

        if recipient:
            confirmation_email = {
                "recipient": recipient,
                "order_id": order.id,
                "movies": movies,
                "total_amount": order.total_amount,
            }

    # 6. Handle failed or expired Checkout Session.
    elif event_type in {
        "checkout.session.async_payment_failed",
        "checkout.session.expired",
    }:
        # Never overwrite a successful payment.
        if payment.status != "pending":
            return {
                "received": True,
                "processed": False,
            }

        if order.status != "pending":
            return {
                "received": True,
                "processed": False,
            }

        if event_type == "checkout.session.async_payment_failed":
            payment.status = "failed"
        else:
            payment.status = "expired"

    # 7. Save changes.
    await db.commit()

    # 8. Schedule email only after successful commit.
    if confirmation_email is not None:
        background_tasks.add_task(
            send_order_confirmation_email,
            **confirmation_email,
        )

    return {
        "received": True,
        "processed": True,
    }

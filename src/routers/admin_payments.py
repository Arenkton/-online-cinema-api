import stripe

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Path,
    Query,
    status,
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.auth_dependencies import (
    get_current_staff,
    get_current_admin,
)
from src.database import get_db
from src.models import Payment, User
from src.schemas import PaymentRead, RefundRead
from src.stripe_service import (
    create_stripe_refund,
    get_payment_intent_id,
    to_minor_units,
)

router = APIRouter(
    prefix="/admin/payments",
    tags=["Admin Payments"],
    dependencies=[Depends(get_current_staff)],
)


@router.get(
    "",
    response_model=list[PaymentRead],
    status_code=status.HTTP_200_OK,
    summary="List all payments",
)
async def list_all_payments(
    payment_status: str | None = Query(
        default=None,
        alias="status",
    ),
    user_id: int | None = Query(
        default=None,
        gt=0,
    ),
    limit: int = Query(
        default=20,
        ge=1,
        le=100,
    ),
    offset: int = Query(
        default=0,
        ge=0,
    ),
    db: AsyncSession = Depends(get_db),
):
    query = (
        select(Payment)
        .options(
            selectinload(Payment.order),
            selectinload(Payment.items),
        )
    )

    if payment_status is not None:
        query = query.where(
            Payment.status == payment_status
        )

    if user_id is not None:
        query = query.where(
            Payment.user_id == user_id
        )

    query = (
        query
        .order_by(Payment.id.desc())
        .limit(limit)
        .offset(offset)
    )

    result = await db.execute(query)

    return result.scalars().all()


@router.get(
    "/{payment_id}",
    response_model=PaymentRead,
    status_code=status.HTTP_200_OK,
    summary="Get any payment details",
)
async def get_admin_payment_details(
    payment_id: int = Path(gt=0),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Payment)
        .options(
            selectinload(Payment.order),
            selectinload(Payment.items),
        )
        .where(Payment.id == payment_id)
    )

    payment = result.scalar_one_or_none()

    if payment is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Payment not found",
        )

    return payment


@router.post(
    "/{payment_id}/refund",
    response_model=RefundRead,
    status_code=status.HTTP_200_OK,
    summary="Refund a payment",
)
async def refund_payment(
    payment_id: int = Path(gt=0),
    db: AsyncSession = Depends(get_db),
    current_admin: User = Depends(get_current_admin),
):
    result = await db.execute(
        select(Payment)
        .options(selectinload(Payment.order))
        .where(Payment.id == payment_id)
        .with_for_update()
    )

    payment = result.scalar_one_or_none()

    if payment is None:
        raise HTTPException(
            status_code=404,
            detail="Payment not found",
        )

    order = payment.order

    if (
        payment.status != "paid"
        or order.status != "paid"
    ):
        raise HTTPException(
            status_code=409,
            detail="Only paid orders can be refunded",
        )

    if (
        payment.refund_status is not None
        or payment.stripe_refund_id is not None
    ):
        raise HTTPException(
            status_code=409,
            detail="Refund already requested",
        )

    if (
        payment.stripe_payment_intent_id is None
        and payment.external_payment_id is None
    ):
        raise HTTPException(
            status_code=409,
            detail="Stripe payment reference is missing",
        )

    try:
        payment_intent_id = (
            payment.stripe_payment_intent_id
        )

        if payment_intent_id is None:
            payment_intent_id = await get_payment_intent_id(
                payment.external_payment_id
            )

        refund = await create_stripe_refund(
            payment_id=payment.id,
            payment_intent_id=payment_intent_id,
        )

    except ValueError as exc:
        raise HTTPException(
            status_code=409,
            detail=str(exc),
        ) from exc

    except stripe.StripeError as exc:
        raise HTTPException(
            status_code=502,
            detail="Stripe refund request failed",
        ) from exc

    # Validate the refund returned by Stripe.
    if (
        refund.payment_intent != payment_intent_id
        or refund.amount != to_minor_units(payment.amount)
        or refund.currency != "pln"
    ):
        raise HTTPException(
            status_code=502,
            detail="Stripe refund data mismatch",
        )

    payment.stripe_payment_intent_id = payment_intent_id
    payment.stripe_refund_id = refund.id
    payment.refund_status = refund.status or "pending"

    if refund.status == "succeeded":
        payment.status = "refunded"
        order.status = "refunded"

    await db.commit()

    return RefundRead(
        payment_id=payment.id,
        refund_id=refund.id,
        refund_status=payment.refund_status,
        payment_status=payment.status,
        order_status=order.status,
    )

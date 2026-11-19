import stripe

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    status,
    Path
)
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from src.auth_dependencies import get_current_user
from src.crud import (
    PaymentConflictError,
    create_payment_from_order,
)
from src.database import get_db
from src.models import (
    User,
    Payment,
    PaymentItem,
    Order,
    OrderItem,
)
from src.schemas import(
    PaymentCreate,
    PaymentRead,
    CheckoutSessionRead,
)
from src.stripe_service import (
    create_checkout_session,
    to_minor_units,
)


router = APIRouter(
    prefix="/payments",
    tags=["Payments"],
)


@router.post(
    "",
    response_model=PaymentRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create payment",
    description=(
        "Creates a pending payment attempt "
        "for an authenticated user's order."
    ),
)
async def create_payment(
    data: PaymentCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        payment = await create_payment_from_order(
            db=db,
            user_id=current_user.id,
            order_id=data.order_id,
        )
    except PaymentConflictError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc

    if payment is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Order not found",
        )

    return payment


@router.post(
    "/{payment_id}/checkout",
    response_model=CheckoutSessionRead,
    status_code=status.HTTP_200_OK,
)
async def start_checkout(
    payment_id: int = Path(gt=0),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(Payment)
        .options(
            selectinload(Payment.order),
            selectinload(Payment.items)
            .selectinload(PaymentItem.order_item)
            .selectinload(OrderItem.movie),
        )
        .where(
            Payment.id == payment_id,
            Payment.user_id == current_user.id,
        )
    )

    payment = result.scalar_one_or_none()

    if payment is None:
        raise HTTPException(
            status_code=404,
            detail="Payment not found",
        )

    if (
        payment.status != "pending"
        or payment.order.status != "pending"
        or payment.external_payment_id is not None
    ):
        raise HTTPException(
            status_code=409,
            detail="Payment is not available for checkout",
        )

    try:
        line_items = [
            {
                "price_data": {
                    "currency": "pln",
                    "product_data": {
                        "name": item.order_item.movie.name,
                    },
                    "unit_amount": to_minor_units(
                        item.price_at_payment
                    ),
                },
                "quantity": 1,
            }
            for item in payment.items
        ]
    except ValueError as exc:
        raise HTTPException(
            status_code=409,
            detail="Invalid payment amount",
        ) from exc


    try:
        expected_amount = to_minor_units(payment.amount)
    except (ValueError, TypeError) as exc:
        raise HTTPException(
            status_code=409,
            detail="Invalid payment amount",
        ) from exc

    if (
        not line_items
        or any(
            item.order_item.order_id != payment.order_id
            for item in payment.items
        )
        or sum(
            item["price_data"]["unit_amount"]
            for item in line_items
        ) != expected_amount
    ):
        raise HTTPException(
            status_code=409,
            detail="Payment items do not match amount",
        )

    try:
        session = await create_checkout_session(
            payment_id=payment.id,
            order_id=payment.order_id,
            line_items=line_items,
        )
    except stripe.StripeError as exc:
        raise HTTPException(
            status_code=502,
            detail="Unable to create Stripe session",
        ) from exc

    if not session.url:
        raise HTTPException(
            status_code=502,
            detail="Stripe did not return a checkout URL",
        )

    payment.external_payment_id = session.id
    await db.commit()

    return CheckoutSessionRead(
        payment_id=payment.id,
        session_id=session.id,
        checkout_url=session.url,
    )


@router.get(
    "",
    response_model=list[PaymentRead],
    status_code=status.HTTP_200_OK,
    summary="Get payment history",
    description=(
        "Returns all payments belonging "
        "to the authenticated user."
    ),
)
async def get_payment_history(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(Payment)
        .options(
            selectinload(Payment.order),
            selectinload(Payment.items),
        )
        .where(
            Payment.user_id == current_user.id,
        )
        .order_by(Payment.id.desc())
    )

    return result.scalars().all()


@router.get(
    "/{payment_id}",
    response_model=PaymentRead,
    status_code=status.HTTP_200_OK,
    summary="Get payment details",
    description=(
        "Returns a payment belonging "
        "to the authenticated user."
    ),
)
async def get_payment_details(
    payment_id: int = Path(gt=0),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(Payment)
        .options(
            selectinload(Payment.order),
            selectinload(Payment.items),
        )
        .where(
            Payment.id == payment_id,
            Payment.user_id == current_user.id,
        )
    )

    payment = result.scalar_one_or_none()

    if payment is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Payment not found",
        )

    return payment

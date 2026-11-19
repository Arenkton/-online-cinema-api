"""Shared builders for cart, order and payment API tests."""
from decimal import Decimal

from sqlalchemy import select

from src.jwt_service import create_jwt_token
from src.models import Cart, CartItem, Order, OrderItem


def auth_headers(user_id: int, token_type: str = "access") -> dict[str, str]:
    token = create_jwt_token(user_id, token_type)
    return {"Authorization": f"Bearer {token}"}


async def get_cart_items(db_session, cart_id: int):
    result = await db_session.execute(
        select(CartItem).where(CartItem.cart_id == cart_id)
    )
    return result.scalars().all()


async def create_test_order(
    db_session,
    user_id: int,
    movie_id: int,
    order_status: str = "paid",
) -> Order:
    order = Order(
        user_id=user_id,
        status=order_status,
        total_amount=Decimal("9.99"),
        items=[
            OrderItem(
                movie_id=movie_id,
                price_at_order=Decimal("9.99"),
            )
        ],
    )
    db_session.add(order)
    await db_session.commit()
    return order


async def create_cart_with_movies(
    db_session,
    user_id: int,
    movie_ids: list[int],
) -> int:
    cart = Cart(user_id=user_id)
    db_session.add(cart)
    await db_session.flush()
    db_session.add_all(
        [CartItem(cart_id=cart.id, movie_id=movie_id)
         for movie_id in movie_ids]
    )
    cart_id = cart.id
    await db_session.commit()
    return cart_id

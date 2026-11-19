
from fastapi import FastAPI

from src.routers import (
    admin_payments,
    auth,
    cart,
    certifications,
    directors,
    genres,
    movies,
    orders,
    payments,
    stars,
    stripe_webhooks,
)


app = FastAPI(
    title="Online Cinema API",
    summary="REST API for an online movie store",
    description=(
        "Online Cinema API provides functionality for "
        "browsing movies, managing users, shopping carts, "
        "orders, and payments.\n\n"
        "## Authentication\n"
        "Protected endpoints require a JWT access token "
        "using the Bearer authentication scheme.\n\n"
        "## Shopping\n"
        "Users can add movies to their carts, create orders, "
        "and view purchase history.\n\n"
        "## Payments\n"
        "Payments are processed using Stripe Checkout. "
        "The API also supports payment history, "
        "administrative payment management, and refunds.\n\n"
        "## Access Control\n"
        "Administrative operations are restricted "
        "according to user roles."
    ),
    version="0.1.0",
)


app.include_router(auth.router)
app.include_router(movies.router)
app.include_router(certifications.router)
app.include_router(genres.router)
app.include_router(stars.router)
app.include_router(directors.router)
app.include_router(cart.router)
app.include_router(orders.router)
app.include_router(payments.router)
app.include_router(admin_payments.router)
app.include_router(stripe_webhooks.router)

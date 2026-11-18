from fastapi import FastAPI

from src.routers import (
    users,
    movies,
    certifications,
    genres,
    stars,
    directors,
    auth,
    cart,
    orders,
)
app = FastAPI()


app.include_router(users.router)
app.include_router(movies.router)

app.include_router(certifications.router)

app.include_router(genres.router)

app.include_router(stars.router)

app.include_router(directors.router)

app.include_router(auth.router)

app.include_router(cart.router)

app.include_router(orders.router)

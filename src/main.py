from fastapi import FastAPI
from src.routers import (
    users,
    movies,
    certifications,
    genres,
    stars,
    directors
)

app = FastAPI()


app.include_router(users.router)
app.include_router(movies.router)

app.include_router(certifications.router)

app.include_router(genres.router)

app.include_router(stars.router)

app.include_router(directors.router)

import os

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    create_async_engine,
)
from sqlalchemy.orm import sessionmaker


SQLALCHEMY_DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "sqlite+aiosqlite:///./online_cinema.db",
)

SQL_ECHO = os.getenv(
    "SQL_ECHO",
    "false",
).lower() in {"true", "1", "yes", "on"}


engine = create_async_engine(
    SQLALCHEMY_DATABASE_URL,
    echo=SQL_ECHO,
)

SessionLocal = sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_db():
    async with SessionLocal() as session:
        yield session

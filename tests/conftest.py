import pytest_asyncio

from decimal import Decimal
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    create_async_engine,
    async_sessionmaker,
)
from sqlalchemy.pool import StaticPool

from src.models import (
    Base,
    Certification,
    Movie,
    User,
    UserGroup,
    UserGroupEnum,
)

from httpx import ASGITransport, AsyncClient

from src.database import get_db
from src.main import app


@pytest_asyncio.fixture
async def db_session():
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        poolclass=StaticPool,
    )

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    try:
        async with session_factory() as session:
            yield session
    finally:
        await engine.dispose()


@pytest_asyncio.fixture
async def api_client(db_session):
    """Use the test database instead of the local application database."""
    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(
            transport=transport, base_url="http://testserver"
        ) as client:
            yield client
    finally:
        app.dependency_overrides.pop(get_db, None)


@pytest_asyncio.fixture
async def cart_data(db_session):
    group = UserGroup(
        name=UserGroupEnum.USER.value
    )

    certification = Certification(name="PG-13")

    user = User(
        email="cart-api@example.com",
        hashed_password="test-password-hash",
        is_active=True,
        group=group,
    )

    movie = Movie(
        name="Test Movie",
        year=2024,
        time=120,
        imdb=8.5,
        votes=1000,
        description="Movie for cart API tests",
        price=Decimal("9.99"),
        certification=certification,
    )

    db_session.add_all([user, movie])
    await db_session.commit()

    return user.id, movie.id

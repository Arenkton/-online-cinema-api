import hashlib
import secrets

from datetime import datetime, timedelta, timezone

from sqlalchemy import select, delete
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.models import (
    Movie,
    Genre,
    Certification,
    Star,
    Director,
    User,
    UserGroup,
    UserGroupEnum,
    ActivationToken,
    RefreshToken,
    Cart,
    CartItem,
)

from src.schemas import (
    MovieCreate,
    MovieUpdate,
    GenreCreate,
    GenreUpdate,
    CertificationCreate,
    CertificationUpdate,
    StarCreate,
    StarUpdate,
    DirectorCreate,
    DirectorUpdate,
    UserCreate,
)

from src.security import hash_password
from src.jwt_service import (
    create_jwt_token,
    decode_jwt_token,
)


async def create_movie(
    db: AsyncSession,
    movie: MovieCreate
) -> Movie:
    movie_data = movie.model_dump(
        exclude={
            "genre_ids",
            "star_ids",
            "director_ids"
        }
    )

    new_movie = Movie(**movie_data)

    result = await db.execute(
        select(Genre).where(
            Genre.id.in_(movie.genre_ids)
        )
    )

    genres = result.scalars().all()

    if {genre.id for genre in genres} != set(movie.genre_ids):
        raise ValueError("Some genres do not exist")

    new_movie.genres = genres

    result = await db.execute(
        select(Star).where(
            Star.id.in_(movie.star_ids)
        )
    )

    stars = result.scalars().all()

    if {star.id for star in stars} != set(movie.star_ids):
        raise ValueError("Some stars do not exist")

    new_movie.stars = stars

    result = await db.execute(
        select(Director).where(
            Director.id.in_(movie.director_ids)
        )
    )

    directors = result.scalars().all()

    if {director.id for director in directors} != set(movie.director_ids):
        raise ValueError("Some directors do not exist")

    new_movie.directors = directors

    db.add(new_movie)

    new_movie.genres = genres
    new_movie.stars = stars
    new_movie.directors = directors

    await db.commit()

    result = await db.execute(
        select(Movie)
        .options(
            selectinload(Movie.genres),
            selectinload(Movie.stars),
            selectinload(Movie.directors)
        )
        .where(Movie.id == new_movie.id)
    )

    return result.scalar_one()


async def get_movie(
    db: AsyncSession,
    movie_id: int
) -> Movie | None:
    result = await db.execute(
        select(Movie)
        .options(
            selectinload(Movie.genres),
            selectinload(Movie.stars),
            selectinload(Movie.directors)
        )
        .where(Movie.id == movie_id)
    )

    return result.scalar_one_or_none()


async def get_movies(db: AsyncSession) -> list[Movie]:
    result = await db.execute(
        select(Movie).options(
            selectinload(Movie.genres),
            selectinload(Movie.stars),
            selectinload(Movie.directors)
        )
    )

    return list(result.scalars().all())


async def update_movie(
    db: AsyncSession,
    movie_id: int,
    movie: MovieUpdate
) -> Movie | None:
    db_movie = await get_movie(db, movie_id)

    if db_movie is None:
        return None

    update_data = movie.model_dump(exclude_unset=True)

    genre_ids = update_data.pop("genre_ids", None)
    star_ids = update_data.pop("star_ids", None)
    director_ids = update_data.pop("director_ids", None)

    for field, value in update_data.items():
        setattr(db_movie, field, value)

    if genre_ids is not None:
        result = await db.execute(
            select(Genre).where(
                Genre.id.in_(genre_ids)
            )
        )

        genres = result.scalars().all()

        if {genre.id for genre in genres} != set(genre_ids):
            raise ValueError("Some genres do not exist")

        db_movie.genres = genres

    if star_ids is not None:
        result = await db.execute(
            select(Star).where(
                Star.id.in_(star_ids)
            )
        )

        stars = result.scalars().all()

        if {star.id for star in stars} != set(star_ids):
            raise ValueError("Some stars do not exist")

        db_movie.stars = stars

    if director_ids is not None:
        result = await db.execute(
            select(Director).where(
                Director.id.in_(director_ids)
            )
        )

        directors = result.scalars().all()

        if {director.id for director in directors} != set(director_ids):
            raise ValueError("Some directors do not exist")

        db_movie.directors = directors

    await db.commit()
    return await get_movie(db, movie_id)


async def delete_movie(
    db: AsyncSession,
    movie_id: int
) -> Movie | None:
    db_movie = await get_movie(db, movie_id)

    if db_movie is None:
        return None

    await db.delete(db_movie)
    await db.commit()

    return db_movie


async def create_genre(db: AsyncSession, genre: GenreCreate) -> Genre:
    new_genre = Genre(**genre.model_dump())

    db.add(new_genre)

    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise

    await db.refresh(new_genre)

    return new_genre


async def get_genre(
    db: AsyncSession,
    genre_id: int
) -> Genre | None:
    result = await db.execute(
        select(Genre).where(Genre.id == genre_id)
    )
    return result.scalar_one_or_none()


async def get_genres(db: AsyncSession) -> list[Genre]:
    result = await db.execute(select(Genre).order_by(Genre.name))

    return result.scalars().all()


async def update_genre(
    db: AsyncSession,
    genre_id: int,
    genre: GenreUpdate
) -> Genre | None:
    db_genre = await get_genre(db, genre_id)

    if db_genre is None:
        return None

    update_data = genre.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(db_genre, field, value)

    await db.commit()
    await db.refresh(db_genre)

    return db_genre


async def delete_genre(
    db: AsyncSession,
    genre_id: int
) -> Genre | None:
    db_genre = await get_genre(db, genre_id)

    if db_genre is None:
        return None

    await db.delete(db_genre)
    await db.commit()

    return db_genre


async def create_certification(
    db: AsyncSession,
    certification: CertificationCreate
) -> Certification:
    new_certification = Certification(**certification.model_dump())

    db.add(new_certification)

    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise

    await db.refresh(new_certification)

    return new_certification


async def get_certification(
        db: AsyncSession,
        certification_id: int
) -> Certification | None:
    result = await db.execute(select(Certification).where(Certification.id == certification_id))

    return result.scalar_one_or_none()


async def get_certifications(db: AsyncSession) -> list[Certification]:
    result = await db.execute(select(Certification).order_by(Certification.id))

    return result.scalars().all()


async def update_certification(
    db: AsyncSession,
    certification_id: int,
    certification: CertificationUpdate
) -> Certification | None:
    db_certification = await get_certification(db, certification_id)

    if db_certification is None:
        return None

    update_data = certification.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(db_certification, field, value)

    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise

    await db.refresh(db_certification)

    return db_certification


async def create_star(
    db: AsyncSession,
    star: StarCreate
) -> Star:
    new_star = Star(**star.model_dump())
    db.add(new_star)

    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise

    await db.refresh(new_star)
    return new_star


async def get_star(
    db: AsyncSession,
    star_id: int
) -> Star | None:
    result = await db.execute(
        select(Star).where(Star.id == star_id)
    )
    return result.scalar_one_or_none()


async def get_stars(
    db: AsyncSession
) -> list[Star]:
    result = await db.execute(
        select(Star).order_by(Star.name)
    )
    return list(result.scalars().all())


async def update_star(
    db: AsyncSession,
    star_id: int,
    star: StarUpdate
) -> Star | None:
    db_star = await get_star(db, star_id)

    if db_star is None:
        return None

    update_data = star.model_dump(exclude_unset=True)

    if "name" in update_data and update_data["name"] is None:
        raise ValueError("Star name cannot be null")

    for field, value in update_data.items():
        setattr(db_star, field, value)

    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise

    await db.refresh(db_star)
    return db_star


async def delete_star(
    db: AsyncSession,
    star_id: int
) -> Star | None:
    db_star = await get_star(db, star_id)

    if db_star is None:
        return None

    try:
        await db.delete(db_star)
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise

    return db_star


async def create_director(
    db: AsyncSession,
    director: DirectorCreate
) -> Director:
    new_director = Director(**director.model_dump())
    db.add(new_director)

    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise

    await db.refresh(new_director)
    return new_director


async def get_director(
    db: AsyncSession,
    director_id: int
) -> Director | None:
    result = await db.execute(
        select(Director).where(Director.id == director_id)
    )
    return result.scalar_one_or_none()


async def get_directors(
    db: AsyncSession
) -> list[Director]:
    result = await db.execute(
        select(Director).order_by(Director.name)
    )
    return list(result.scalars().all())


async def update_director(
    db: AsyncSession,
    director_id: int,
    director: DirectorUpdate
) -> Director | None:
    db_director = await get_director(db, director_id)

    if db_director is None:
        return None

    update_data = director.model_dump(exclude_unset=True)

    if "name" in update_data and update_data["name"] is None:
        raise ValueError("Director name cannot be null")

    for field, value in update_data.items():
        setattr(db_director, field, value)

    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise

    await db.refresh(db_director)
    return db_director


async def delete_director(
    db: AsyncSession,
    director_id: int
) -> Director | None:
    db_director = await get_director(db, director_id)

    if db_director is None:
        return None

    try:
        await db.delete(db_director)
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise

    return db_director


async def get_user_by_email(
    db: AsyncSession,
    email: str
) -> User | None:
    result = await db.execute(
        select(User).where(User.email == email)
    )

    return result.scalar_one_or_none()


async def create_user(
    db: AsyncSession,
    user: UserCreate
) -> tuple[User, str]:
    email = user.email.strip().lower()

    existing_user = await get_user_by_email(db, email)

    if existing_user is not None:
        raise ValueError("Email already registered")

    result = await db.execute(
        select(UserGroup).where(
            UserGroup.name == UserGroupEnum.USER.value
        )
    )

    user_group = result.scalar_one_or_none()

    if user_group is None:
        raise ValueError("Default user group not found")

    raw_token = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(
        raw_token.encode("utf-8")
    ).hexdigest()

    new_user = User(
        email=email,
        hashed_password=hash_password(user.password),
        is_active=False,
        group_id=user_group.id
    )

    try:
        db.add(new_user)
        await db.flush()

        activation_token = ActivationToken(
            user_id=new_user.id,
            token=token_hash,
            expires_at=(
                datetime.now(timezone.utc)
                + timedelta(hours=24)
            )
        )

        db.add(activation_token)

        await db.commit()
        await db.refresh(new_user)

    except Exception:
        await db.rollback()
        raise

    return new_user, raw_token


async def activate_user(
    db: AsyncSession,
    raw_token: str,
) -> bool:
    token_hash = hashlib.sha256(
        raw_token.encode("utf-8")
    ).hexdigest()

    result = await db.execute(
        select(ActivationToken, User)
        .join(
            User,
            ActivationToken.user_id == User.id,
        )
        .where(ActivationToken.token == token_hash)
    )

    record = result.one_or_none()

    if record is None:
        return False

    activation_token, user = record

    expires_at = activation_token.expires_at

    # SQLite may return a naive datetime.
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(
            tzinfo=timezone.utc
        )

    if expires_at <= datetime.now(timezone.utc):
        return False

    user.is_active = True

    try:
        await db.delete(activation_token)
        await db.commit()
    except Exception:
        await db.rollback()
        raise

    return True


async def resend_activation_token(
    db: AsyncSession,
    email: str,
) -> tuple[str, str] | None:
    user = await get_user_by_email(
        db,
        email.strip().lower(),
    )

    if user is None or user.is_active:
        return None

    result = await db.execute(
        select(ActivationToken).where(
            ActivationToken.user_id == user.id
        )
    )

    activation = result.scalar_one_or_none()
    now = datetime.now(timezone.utc)

    if activation is not None:
        expires_at = activation.expires_at

        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(
                tzinfo=timezone.utc
            )

        # Tokens are valid for 24 hours.
        # Allow a new token after a 5-minute cooldown.
        if expires_at > now + timedelta(
            hours=23,
            minutes=55,
        ):
            return None

    raw_token = secrets.token_urlsafe(32)

    token_hash = hashlib.sha256(
        raw_token.encode("utf-8")
    ).hexdigest()

    new_expiration = now + timedelta(hours=24)

    if activation is None:
        activation = ActivationToken(
            user_id=user.id,
            token=token_hash,
            expires_at=new_expiration,
        )
        db.add(activation)
    else:
        activation.token = token_hash
        activation.expires_at = new_expiration

    try:
        await db.commit()
    except Exception:
        await db.rollback()
        raise

    return user.email, raw_token


async def save_refresh_token(
    db: AsyncSession,
    user_id: int,
    raw_token: str,
) -> None:
    payload = decode_jwt_token(
        raw_token,
        expected_type="refresh",
    )

    token_hash = hashlib.sha256(
        raw_token.encode("utf-8")
    ).hexdigest()

    expires_at = datetime.fromtimestamp(
        payload["exp"],
        tz=timezone.utc,
    )

    refresh_token = RefreshToken(
        user_id=user_id,
        token=token_hash,
        expires_at=expires_at,
    )

    db.add(refresh_token)

    try:
        await db.commit()
    except Exception:
        await db.rollback()
        raise


async def rotate_refresh_token(
    db: AsyncSession,
    raw_token: str,
) -> tuple[str, str] | None:
    payload = decode_jwt_token(
        raw_token,
        expected_type="refresh",
    )

    try:
        user_id = int(payload["sub"])
    except (ValueError, TypeError):
        return None

    if user_id <= 0 or str(user_id) != payload["sub"]:
        return None

    user = await db.get(User, user_id)

    if user is None or not user.is_active:
        return None

    old_token_hash = hashlib.sha256(
        raw_token.encode("utf-8")
    ).hexdigest()

    new_access = create_jwt_token(
        user_id=user_id,
        token_type="access",
    )

    new_refresh = create_jwt_token(
        user_id=user_id,
        token_type="refresh",
    )

    new_refresh_hash = hashlib.sha256(
        new_refresh.encode("utf-8")
    ).hexdigest()

    new_payload = decode_jwt_token(
        new_refresh,
        expected_type="refresh",
    )

    expires_at = datetime.fromtimestamp(
        new_payload["exp"],
        tz=timezone.utc,
    )

    try:
        result = await db.execute(
            delete(RefreshToken)
            .where(
                RefreshToken.user_id == user_id,
                RefreshToken.token == old_token_hash,
                RefreshToken.expires_at
                > datetime.now(timezone.utc),
            )
            .returning(RefreshToken.id)
        )

        deleted_token_id = result.scalar_one_or_none()

        if deleted_token_id is None:
            await db.rollback()
            return None

        db.add(
            RefreshToken(
                user_id=user_id,
                token=new_refresh_hash,
                expires_at=expires_at,
            )
        )

        await db.commit()

    except Exception:
        await db.rollback()
        raise

    return new_access, new_refresh


async def revoke_refresh_token(
    db: AsyncSession,
    raw_token: str,
) -> bool:
    payload = decode_jwt_token(
        raw_token,
        expected_type="refresh",
    )

    try:
        user_id = int(payload["sub"])
    except (ValueError, TypeError):
        return False

    if user_id <= 0 or str(user_id) != payload["sub"]:
        return False

    token_hash = hashlib.sha256(
        raw_token.encode("utf-8")
    ).hexdigest()

    try:
        result = await db.execute(
            delete(RefreshToken)
            .where(
                RefreshToken.user_id == user_id,
                RefreshToken.token == token_hash,
            )
            .returning(RefreshToken.id)
        )

        deleted_id = result.scalar_one_or_none()

        if deleted_id is None:
            await db.rollback()
            return False

        await db.commit()

    except Exception:
        await db.rollback()
        raise

    return True


async def add_movie_to_cart(
    db: AsyncSession,
    user_id: int,
    movie_id: int,
) -> CartItem | None:
    result = await db.execute(
        select(Cart).where(Cart.user_id == user_id)
    )
    cart = result.scalar_one_or_none()

    if cart is None:
        cart = Cart(user_id=user_id)
        db.add(cart)
        await db.flush()

    result = await db.execute(
        select(CartItem).where(
            CartItem.cart_id == cart.id,
            CartItem.movie_id == movie_id,
        )
    )

    existing_item = result.scalar_one_or_none()

    if existing_item is not None:
        await db.rollback()
        return None

    item = CartItem(
        cart_id=cart.id,
        movie_id=movie_id,
    )

    db.add(item)

    try:
        await db.commit()
    except Exception:
        await db.rollback()
        raise

    await db.refresh(item)
    return item


async def get_cart_items(
    db: AsyncSession,
    user_id: int,
) -> list[CartItem]:
    result = await db.execute(
        select(CartItem)
        .join(Cart, CartItem.cart_id == Cart.id)
        .options(
            selectinload(CartItem.movie)
        )
        .where(Cart.user_id == user_id)
        .order_by(
            CartItem.added_at,
            CartItem.id,
        )
    )

    return list(result.scalars().all())

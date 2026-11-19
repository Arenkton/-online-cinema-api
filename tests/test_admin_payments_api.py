"""Admin and moderator payment management API tests."""
from decimal import Decimal

import pytest
from src.models import Payment, User, UserGroup, UserGroupEnum
from tests.helpers import auth_headers, create_test_order


@pytest.fixture(autouse=True)
def jwt_secret(monkeypatch):
    monkeypatch.setenv(
        "JWT_SECRET_KEY", "test-secret-key-for-jwt-unit-tests-123456789"
    )


async def create_staff_user(db_session, role: UserGroupEnum) -> User:
    """Create a separate authorized user with the requested staff role."""
    group = UserGroup(name=role.value)
    user = User(
        email=f"{role.value.lower()}-payment-admin@example.com",
        hashed_password="test-password-hash",
        is_active=True,
        group=group,
    )
    db_session.add(user)
    await db_session.commit()
    return user


async def create_payment_record(
    db_session,
    user_id: int,
    movie_id: int,
    payment_status: str = "pending",
) -> Payment:
    """Seed a payment independently of payment-creation route restrictions."""
    order_status = "paid" if payment_status == "paid" else "pending"
    order = await create_test_order(
        db_session,
        user_id=user_id,
        movie_id=movie_id,
        order_status=order_status,
    )
    payment = Payment(
        user_id=user_id,
        order_id=order.id,
        status=payment_status,
        amount=Decimal("9.99"),
    )
    db_session.add(payment)
    await db_session.commit()
    return payment


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "role",
    [UserGroupEnum.ADMIN, UserGroupEnum.MODERATOR],
)
async def test_staff_can_list_and_view_all_payments(
    api_client, db_session, cart_data, role,
):
    user_id, movie_id = cart_data
    payment = await create_payment_record(db_session, user_id, movie_id)
    staff = await create_staff_user(db_session, role)

    history = await api_client.get(
        "/admin/payments",
        headers=auth_headers(staff.id),
    )
    details = await api_client.get(
        f"/admin/payments/{payment.id}",
        headers=auth_headers(staff.id),
    )

    assert history.status_code == 200
    assert [row["id"] for row in history.json()] == [payment.id]
    assert details.status_code == 200
    assert details.json()["id"] == payment.id
    assert details.json()["user_id"] == user_id
    assert details.json()["order_id"] == payment.order_id


@pytest.mark.asyncio
async def test_regular_user_is_forbidden_from_admin_payments(
    api_client, db_session, cart_data,
):
    user_id, movie_id = cart_data
    payment = await create_payment_record(db_session, user_id, movie_id)
    headers = auth_headers(user_id)

    history = await api_client.get("/admin/payments", headers=headers)
    details = await api_client.get(
        f"/admin/payments/{payment.id}", headers=headers
    )

    assert history.status_code == 403
    assert details.status_code == 403
    assert history.json()["detail"] == "Admin or moderator access required"


@pytest.mark.asyncio
async def test_admin_payment_routes_require_authentication(api_client):
    history = await api_client.get("/admin/payments")
    details = await api_client.get("/admin/payments/1")

    assert history.status_code == 401
    assert details.status_code == 401


@pytest.mark.asyncio
async def test_invalid_jwt_cannot_access_admin_payments(api_client):
    response = await api_client.get(
        "/admin/payments",
        headers={"Authorization": "Bearer invalid.jwt.token"},
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_inactive_admin_cannot_access_admin_payments(
    api_client, db_session,
):
    admin = await create_staff_user(db_session, UserGroupEnum.ADMIN)
    admin.is_active = False
    await db_session.commit()

    response = await api_client.get(
        "/admin/payments",
        headers=auth_headers(admin.id),
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_admin_can_filter_payments_by_status(
    api_client, db_session, cart_data,
):
    user_id, movie_id = cart_data
    paid = await create_payment_record(
        db_session, user_id, movie_id, payment_status="paid"
    )
    pending = await create_payment_record(
        db_session, user_id, movie_id, payment_status="pending"
    )
    admin = await create_staff_user(db_session, UserGroupEnum.ADMIN)

    response = await api_client.get(
        "/admin/payments",
        params={"status": "paid"},
        headers=auth_headers(admin.id),
    )

    assert response.status_code == 200
    ids = [row["id"] for row in response.json()]
    assert ids == [paid.id]
    assert pending.id not in ids


@pytest.mark.asyncio
async def test_admin_can_filter_payments_by_user(
    api_client, db_session, cart_data,
):
    first_user_id, movie_id = cart_data
    first_payment = await create_payment_record(
        db_session, first_user_id, movie_id
    )

    first_user = await db_session.get(User, first_user_id)
    second_user = User(
        email="second-admin-payments-user@example.com",
        hashed_password="test-password-hash",
        is_active=True,
        group_id=first_user.group_id,
    )
    db_session.add(second_user)
    await db_session.commit()
    second_payment = await create_payment_record(
        db_session, second_user.id, movie_id
    )

    admin = await create_staff_user(db_session, UserGroupEnum.ADMIN)
    response = await api_client.get(
        "/admin/payments",
        params={"user_id": second_user.id},
        headers=auth_headers(admin.id),
    )

    assert response.status_code == 200
    assert [row["id"] for row in response.json()] == [second_payment.id]
    assert first_payment.id != second_payment.id


@pytest.mark.asyncio
async def test_admin_can_combine_status_and_user_filters(
    api_client, db_session, cart_data,
):
    user_id, movie_id = cart_data
    paid = await create_payment_record(
        db_session, user_id, movie_id, payment_status="paid"
    )
    await create_payment_record(
        db_session, user_id, movie_id, payment_status="pending"
    )
    admin = await create_staff_user(db_session, UserGroupEnum.ADMIN)

    response = await api_client.get(
        "/admin/payments",
        params={"user_id": user_id, "status": "paid"},
        headers=auth_headers(admin.id),
    )

    assert response.status_code == 200
    assert [row["id"] for row in response.json()] == [paid.id]


@pytest.mark.asyncio
async def test_admin_payments_pagination_is_descending(
    api_client, db_session, cart_data,
):
    user_id, movie_id = cart_data
    payments = []
    for payment_status in ("failed", "expired", "pending"):
        payment = await create_payment_record(
            db_session, user_id, movie_id, payment_status=payment_status
        )
        payments.append(payment.id)

    admin = await create_staff_user(db_session, UserGroupEnum.ADMIN)
    response = await api_client.get(
        "/admin/payments",
        params={"limit": 1, "offset": 1},
        headers=auth_headers(admin.id),
    )

    assert response.status_code == 200
    assert [row["id"] for row in response.json()] == [
        sorted(payments, reverse=True)[1]
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "params",
    [
        {"limit": 0},
        {"limit": 101},
        {"offset": -1},
        {"user_id": 0},
    ],
)
async def test_admin_payments_invalid_query_parameters_return_422(
    api_client, db_session, params,
):
    admin = await create_staff_user(db_session, UserGroupEnum.ADMIN)
    response = await api_client.get(
        "/admin/payments",
        params=params,
        headers=auth_headers(admin.id),
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_admin_get_unknown_payment_returns_404(
    api_client, db_session,
):
    admin = await create_staff_user(db_session, UserGroupEnum.ADMIN)
    response = await api_client.get(
        "/admin/payments/999999",
        headers=auth_headers(admin.id),
    )
    assert response.status_code == 404
    assert response.json()["detail"] == "Payment not found"


@pytest.mark.asyncio
async def test_admin_get_invalid_payment_id_returns_422(
    api_client, db_session,
):
    admin = await create_staff_user(db_session, UserGroupEnum.ADMIN)
    response = await api_client.get(
        "/admin/payments/0",
        headers=auth_headers(admin.id),
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_admin_payment_history_empty(api_client, db_session):
    admin = await create_staff_user(db_session, UserGroupEnum.ADMIN)
    response = await api_client.get(
        "/admin/payments",
        headers=auth_headers(admin.id),
    )
    assert response.status_code == 200
    assert response.json() == []

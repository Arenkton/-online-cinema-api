# Online Cinema API

A REST API for an online movie store, built with **FastAPI** and asynchronous **SQLAlchemy**. The application supports movie catalog management, user authentication, shopping carts, orders, Stripe test payments, and refunds.

## Features

- Movie catalog with movies, genres, directors, stars, and age certifications.
- Account registration, email activation, login, refresh-token rotation, and logout.
- JWT-based authentication and role-based access to administrative payment operations.
- Shopping cart and order management, with checks against duplicate purchases.
- Stripe Checkout for test payments, payment history, administrative payment views, and refunds.
- Stripe webhooks for payment and refund status updates.
- Activation and order-confirmation emails; Mailpit can capture outgoing email in development.
- Interactive API documentation through Swagger UI and ReDoc.
- Alembic migrations and automated tests with Pytest.

## Tech stack

- Python 3.12+ (the supplied Dockerfile uses Python 3.14)
- FastAPI, Uvicorn, Pydantic
- SQLAlchemy (async), aiosqlite, SQLite, Alembic
- Poetry
- PyJWT and Argon2
- Stripe Python SDK and Stripe CLI
- Pytest, pytest-asyncio, pytest-cov, Flake8
- Docker and Docker Compose

## Quick start with Docker

**Requirements:** Docker Desktop with Docker Compose.

1. Copy the example environment configuration (Windows CMD):

   ```cmd
   copy .env.example .env
   ```

   On macOS/Linux use `cp .env.example .env`.

2. Edit `.env`. In particular, set a strong `JWT_SECRET_KEY` and use **test-mode** Stripe credentials if testing payments. Do not commit `.env`.

3. Build and start the API:

   ```cmd
   docker compose up --build -d
   ```

4. Inspect the application:

   ```cmd
   docker compose ps
   docker compose logs --tail=100 api
   ```

5. Open [Swagger UI](http://localhost:8000/docs).

The API container runs `alembic upgrade head` before starting Uvicorn. SQLite data is stored in the named `cinema_sqlite` volume and survives normal container restarts.

Useful commands:

```cmd
docker compose exec api alembic current
docker compose logs -f api
docker compose down
```

**Caution:** `docker compose down -v` also removes the named database volume and its data. Docker uses a separate SQLite database from the local Poetry setup.

## Local development with Poetry

**Requirements:** Python 3.12+ and Poetry 2.x.

```cmd
poetry install
copy .env.example .env
poetry run alembic upgrade head
poetry run uvicorn src.main:app --reload
```

Edit `.env` before launching the server. For local SQLite development, set `DATABASE_URL=sqlite+aiosqlite:///./online_cinema.db` (or omit it if the application's default is unchanged). Local API: <http://127.0.0.1:8000>.

## Environment variables

Set these in `.env`, using `.env.example` as the starting point. Values below are descriptions, **not credentials**.

| Variable | Purpose |
| --- | --- |
| `DATABASE_URL` | SQLAlchemy async database URL. Docker Compose configures SQLite at `/app/data/online_cinema.db`. |
| `JWT_SECRET_KEY` | Secret used to sign JWTs; use a random value of at least 32 characters. |
| `PUBLIC_API_BASE_URL` | Public base URL used when creating activation links. |
| `SMTP_HOST` | SMTP server hostname; see the Mailpit section. |
| `SMTP_PORT` | SMTP server port (Mailpit defaults to `1025`). |
| `SMTP_FROM` | Sender email address if required by the email service. |
| `STRIPE_SECRET_KEY` | Stripe **test-mode** secret key (`sk_test_...`). |
| `STRIPE_WEBHOOK_SECRET` | Signing secret (`whsec_...`) for the Stripe webhook endpoint. |
| `STRIPE_CURRENCY` | Checkout currency; the current refund validation expects `pln`. |
| `STRIPE_SUCCESS_URL` | Browser redirect after Checkout success. |
| `STRIPE_CANCEL_URL` | Browser redirect after Checkout cancellation. |

The sample `STRIPE_SUCCESS_URL` and `STRIPE_CANCEL_URL` may point to Swagger during development. They are placeholders rather than dedicated frontend success/cancel pages.

Never commit real API keys, webhook secrets, or `.env` files. Keep `.env` listed in `.gitignore` and `.dockerignore`.

## API documentation

When the application is running:

- Swagger UI: <http://localhost:8000/docs>
- ReDoc: <http://localhost:8000/redoc>
- OpenAPI JSON: <http://localhost:8000/openapi.json>

Swagger UI can be used to try endpoints. For protected routes, click **Authorize** and supply your JWT **access** token using the HTTP Bearer scheme.

### Main endpoint groups

| Group | Example endpoints | Purpose |
| --- | --- | --- |
| Authentication | `POST /auth/register`, `POST /auth/login`, `POST /auth/refresh`, `POST /auth/logout`, `GET /auth/me` | Accounts and sessions |
| Catalog | `/movies`, `/genres`, `/directors`, `/stars`, `/certifications` | Movie information and related entities |
| Shopping cart | `/cart`, `/cart/items` | Cart management |
| Orders | `POST /orders`, `GET /orders`, `POST /orders/{order_id}/cancel` | Order creation and history |
| Payments | `POST /payments`, `GET /payments`, `POST /payments/{payment_id}/checkout` | Payment creation, history, Checkout |
| Administration | `GET /admin/payments`, `POST /admin/payments/{payment_id}/refund` | Administrative payment management |
| Webhooks | `POST /webhooks/stripe` | Stripe event processing |

Refer to Swagger for all supported methods, request bodies, and response schemas.

## JWT authentication

A new account is registered as inactive until its activation link is used. Activation links expire after **24 hours**, and activation email requests are rate-limited to one every **5 minutes**.

| Endpoint | Method | Description |
| --- | --- | --- |
| `/auth/register` | `POST` | Register a user and request an activation email |
| `/auth/activate` | `GET` | Activate an account using a one-time token |
| `/auth/resend-activation` | `POST` | Request another activation email |
| `/auth/login` | `POST` | Get access and refresh tokens |
| `/auth/me` | `GET` | Get the authenticated user |
| `/auth/refresh` | `POST` | Rotate the refresh token and issue a new token pair |
| `/auth/logout` | `POST` | Revoke a refresh token |

**Token lifetimes:** access token **15 minutes**; refresh token **7 days**. Refresh tokens are stored as SHA-256 hashes in the database. Refresh rotation revokes the previous refresh token, and logout revokes the supplied refresh token. Already-issued access tokens remain valid until they expire.

Send an access token as:

```http
Authorization: Bearer <access_token>
```

## Email testing with Mailpit

Mailpit captures development emails without delivering them to real recipients.

### When running FastAPI locally

Start Mailpit using Docker (Windows CMD):

```cmd
docker run -d --name online-cinema-mailpit -p 127.0.0.1:1025:1025 -p 127.0.0.1:8025:8025 axllent/mailpit
```

Configure the locally running API:

```dotenv
SMTP_HOST=127.0.0.1
SMTP_PORT=1025
PUBLIC_API_BASE_URL=http://127.0.0.1:8000
```

Open the [Mailpit web interface](http://127.0.0.1:8025). To start an existing Mailpit container again:

```cmd
docker start online-cinema-mailpit
```

### When FastAPI runs inside Docker Compose

**Do not use `SMTP_HOST=127.0.0.1` inside the API container**: it refers to the API container itself, not the Mailpit container or your Windows PC.

For container-to-container email testing, add Mailpit to `compose.yaml` as another service, for example:

```yaml
services:
  mailpit:
    image: axllent/mailpit:latest
    ports:
      - "127.0.0.1:8025:8025"
```

Set `SMTP_HOST=mailpit` and `SMTP_PORT=1025` in the API container's environment, then recreate the services with `docker compose up -d --build`. Docker Compose service-name DNS allows the API to reach Mailpit on its internal SMTP port. This is an **optional addition**; it is not included in the initial API-only Compose configuration. If Mailpit is already running separately on port `8025`, stop it first to avoid a port conflict.

## Stripe payments (test mode)

The API integrates with Stripe Checkout using test-mode credentials. A typical purchase flow is:

1. Authenticate and add movies to the cart.
2. Create an order with `POST /orders`.
3. Create its payment with `POST /payments`.
4. Create a Stripe Checkout Session with `POST /payments/{payment_id}/checkout` and open the returned `checkout_url`.
5. Complete a **test** payment; the verified Stripe webhook updates the local payment/order statuses.
6. View payment history with `GET /payments`.

An administrator can request a full refund through `POST /admin/payments/{payment_id}/refund`. Refund and checkout events are processed by the Stripe webhook handler. Do not use real payment-card information for development tests.

For local webhook forwarding, run Stripe CLI in another terminal:

```cmd
stripe login
stripe listen --forward-to localhost:8000/webhooks/stripe
```

Copy the `whsec_...` signing secret printed by Stripe CLI into `STRIPE_WEBHOOK_SECRET` and restart the API if its environment changed. A commonly used Stripe test card is `4242 4242 4242 4242`, with a future expiry date and any valid CVC, in Stripe test mode.

**Note:** Payments and refunds are intended for development/test evaluation; this project documentation does not claim production-grade payment reconciliation or fault tolerance.

## Testing and code quality

Run tests:

```cmd
poetry run pytest -q
```

Run coverage:

```cmd
poetry run pytest --cov=src --cov-report=term-missing
```

Check code style:

```cmd
poetry run flake8 src tests
```

The tests use isolated, in-memory SQLite databases and mock external services where appropriate.

## Project layout

```text
online-cinema/
├── alembic/                 # Database migration scripts
├── src/
│   ├── routers/             # API endpoints
│   ├── models.py            # SQLAlchemy models
│   ├── schemas.py           # Pydantic schemas
│   ├── crud.py              # Database operations
│   ├── database.py          # Async database configuration
│   └── main.py              # FastAPI app and router registration
├── tests/                   # Automated tests
├── Dockerfile
├── compose.yaml
├── .env.example
├── pyproject.toml
├── poetry.lock
└── README.md
```

## Development notes

- Local development and Docker Compose use different SQLite database files by default.
- Schema changes should be recorded as Alembic migrations and committed to version control.
- Check `docker compose logs --tail=100 api` if the application container fails to start.
- The `.env.example` file must contain placeholders only; never publish live secrets.

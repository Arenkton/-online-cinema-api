
## Email testing with Mailpit

The project uses Mailpit for local email testing.

Start Mailpit using Docker:

```cmd
docker run -d --name online-cinema-mailpit -p 127.0.0.1:1025:1025 -p 127.0.0.1:8025:8025 axllent/mailpit
```

Mailpit web interface:
http://127.0.0.1:8025

SMTP configuration:
- SMTP_HOST=127.0.0.1
- SMTP_PORT=1025
- PUBLIC_API_BASE_URL=http://127.0.0.1:8000

To restart an existing container:

```cmd
docker start online-cinema-mailpit
```

Authentication endpoints:
- POST /auth/register
- GET /auth/activate
- POST /auth/resend-activation

Activation links expire after 24 hours.

## JWT Authentication

The API uses JWT authentication with access and refresh tokens.

### Token lifetime

- Access Token: 15 minutes
- Refresh Token: 7 days

### Authentication endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | /auth/register | Register a new user |
| GET | /auth/activate | Activate an account |
| POST | /auth/resend-activation | Request a new activation email |
| POST | /auth/login | Obtain access and refresh tokens |
| GET | /auth/me | Get the authenticated user |
| POST | /auth/refresh | Rotate the refresh token |
| POST | /auth/logout | Revoke a refresh token |

### JWT configuration

Set the JWT_SECRET_KEY environment variable before running the API.

The secret must contain at least 32 characters.

Never commit the secret key to Git.

### Authorization

Protected endpoints require an HTTP header:

Authorization: Bearer <access_token>

### Refresh token rotation

Every successful refresh request issues a new token pair
and revokes the previous refresh token.

Refresh tokens are stored as SHA-256 hashes in the database.

### Logout

Logout revokes the supplied refresh token.

An already issued access token remains valid until expiration
(up to 15 minutes).

### Testing

Run all tests:

    poetry run pytest -q

Check code coverage:

    poetry run pytest --cov=src --cov-report=term-missing

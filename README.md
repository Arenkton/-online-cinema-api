
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

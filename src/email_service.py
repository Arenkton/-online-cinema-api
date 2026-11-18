import os
import smtplib

from email.message import EmailMessage
from urllib.parse import urlencode


def send_activation_email(
    recipient: str,
    token: str,
) -> None:
    base_url = os.getenv(
        "PUBLIC_API_BASE_URL",
        "http://127.0.0.1:8000",
    ).rstrip("/")

    query = urlencode({"token": token})
    activation_url = f"{base_url}/auth/activate?{query}"

    message = EmailMessage()
    message["Subject"] = "Activate your Online Cinema account"
    message["From"] = os.getenv(
        "SMTP_FROM",
        "noreply@onlinecinema.local",
    )
    message["To"] = recipient

    message.set_content(
        "Welcome to Online Cinema!\n\n"
        "Activate your account using this link:\n"
        f"{activation_url}\n\n"
        "This link expires in 24 hours."
    )

    smtp_host = os.getenv("SMTP_HOST", "127.0.0.1")
    smtp_port = int(os.getenv("SMTP_PORT", "1025"))

    with smtplib.SMTP(
        smtp_host,
        smtp_port,
        timeout=10,
    ) as smtp:
        smtp.send_message(message)

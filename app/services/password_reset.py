"""Password reset token creation and optional email delivery."""
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
import logging
import secrets
import smtplib

from flask import current_app, url_for

from app.extensions import db

logger = logging.getLogger(__name__)


def create_password_reset_token(user):
    token = secrets.token_urlsafe(48)
    expires_at = datetime.now(timezone.utc) + timedelta(
        minutes=current_app.config["PASSWORD_RESET_EXPIRATION_MINUTES"]
    )
    user.reset_password_token = token
    user.reset_password_expires_at = expires_at.replace(tzinfo=None)
    db.session.commit()
    return token


def clear_password_reset_token(user):
    user.reset_password_token = None
    user.reset_password_expires_at = None


def password_reset_url(token):
    return url_for("auth.reset_password", token=token, _external=True)


def send_password_reset_email(user, token):
    reset_url = password_reset_url(token)
    smtp_host = current_app.config.get("SMTP_HOST")
    if not smtp_host:
        logger.warning("Password reset link for %s: %s", user.email, reset_url)
        return False

    message = EmailMessage()
    message["Subject"] = "Reset your MoveDefense password"
    message["From"] = current_app.config["SMTP_FROM"]
    message["To"] = user.email
    message.set_content(
        "Use this link to reset your MoveDefense password. "
        "It expires in "
        f"{current_app.config['PASSWORD_RESET_EXPIRATION_MINUTES']} minutes.\n\n"
        f"{reset_url}\n"
    )

    with smtplib.SMTP(current_app.config["SMTP_HOST"], current_app.config["SMTP_PORT"]) as server:
        if current_app.config.get("SMTP_USE_TLS", True):
            server.starttls()
        username = current_app.config.get("SMTP_USERNAME")
        password = current_app.config.get("SMTP_PASSWORD")
        if username and password:
            server.login(username, password)
        server.send_message(message)
    return True

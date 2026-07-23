"""
Email service.

Sends transactional emails via SMTP (async-safe by running the
blocking smtplib calls in a thread pool executor).

All HTML templates live in this module for simplicity.  A full
template engine (Jinja2) can be wired in later without changing
the service API.
"""

from __future__ import annotations

import asyncio
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from functools import partial

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)


class EmailService:
    """
    Thin SMTP wrapper.

    Usage::

        email_svc = EmailService()
        await email_svc.send_password_reset(
            to_email="user@example.com",
            reset_url="https://app.example.com/reset?token=abc123",
        )
    """

    def __init__(self) -> None:
        self._cfg = settings.email

    # ------------------------------------------------------------------
    # Internal send helper
    # ------------------------------------------------------------------

    def _send_sync(self, msg: MIMEMultipart) -> None:
        """Blocking SMTP send — called from a thread pool."""
        with smtplib.SMTP(self._cfg.host, self._cfg.port) as server:
            if self._cfg.tls:
                server.starttls()
            if self._cfg.user and self._cfg.password:
                server.login(self._cfg.user, self._cfg.password)
            server.send_message(msg)

    async def send(
        self,
        *,
        to_email: str,
        subject: str,
        html_body: str,
        text_body: str | None = None,
    ) -> None:
        """
        Compose and send an email asynchronously.

        Falls back to a plain-text body if html_body is given and
        *text_body* is None.
        """
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = f"{self._cfg.from_name} <{self._cfg.from_email}>"
        msg["To"] = to_email

        plain = text_body or _strip_html(html_body)
        msg.attach(MIMEText(plain, "plain"))
        msg.attach(MIMEText(html_body, "html"))

        loop = asyncio.get_running_loop()
        try:
            await loop.run_in_executor(None, partial(self._send_sync, msg))
            logger.info("Email sent", to=to_email, subject=subject)
        except Exception as exc:
            # Log but don't crash the request — callers must decide if
            # a failed email is fatal.
            logger.error(
                "Failed to send email",
                to=to_email,
                subject=subject,
                error=str(exc),
            )
            raise

    # ------------------------------------------------------------------
    # Transactional email methods
    # ------------------------------------------------------------------

    async def send_password_reset(
        self,
        *,
        to_email: str,
        reset_url: str,
        expires_minutes: int = 60,
    ) -> None:
        """Send a password-reset email with the provided reset URL."""
        subject = f"{settings.app_name} — Password Reset"
        html = _PASSWORD_RESET_TEMPLATE.format(
            app_name=settings.app_name,
            reset_url=reset_url,
            expires_minutes=expires_minutes,
        )
        await self.send(to_email=to_email, subject=subject, html_body=html)

    async def send_email_verification(
        self,
        *,
        to_email: str,
        verify_url: str,
    ) -> None:
        """Send an account-verification email."""
        subject = f"{settings.app_name} — Verify Your Email"
        html = _EMAIL_VERIFICATION_TEMPLATE.format(
            app_name=settings.app_name,
            verify_url=verify_url,
        )
        await self.send(to_email=to_email, subject=subject, html_body=html)

    async def send_welcome(
        self,
        *,
        to_email: str,
        full_name: str,
    ) -> None:
        """Send a welcome email after account creation."""
        subject = f"Welcome to {settings.app_name}"
        html = _WELCOME_TEMPLATE.format(
            app_name=settings.app_name,
            full_name=full_name,
        )
        await self.send(to_email=to_email, subject=subject, html_body=html)

    async def send_notification(
        self,
        *,
        to_email: str,
        full_name: str,
        title: str,
        message: str,
        notification_type: str = "INFO",
        priority: str = "NORMAL",
    ) -> None:
        """Send a notification email."""
        subject = f"{settings.app_name} — {title}"
        html = _NOTIFICATION_TEMPLATE.format(
            app_name=settings.app_name,
            full_name=full_name,
            title=title,
            message=message,
            notification_type=notification_type,
            priority=priority,
        )
        await self.send(to_email=to_email, subject=subject, html_body=html)


# ---------------------------------------------------------------------------
# HTML email templates
# ---------------------------------------------------------------------------

_BASE_STYLE = """
  font-family: Arial, sans-serif;
  max-width: 600px;
  margin: 0 auto;
  padding: 24px;
  background: #f9f9f9;
"""

_PASSWORD_RESET_TEMPLATE = """
<div style="{style}">
  <h2 style="color:#1a73e8">{app_name}</h2>
  <h3>Password Reset Request</h3>
  <p>We received a request to reset the password for your account.</p>
  <p>Click the button below to reset your password. This link expires in
     <strong>{expires_minutes} minutes</strong>.</p>
  <p style="text-align:center;margin:32px 0">
    <a href="{reset_url}"
       style="background:#1a73e8;color:#fff;padding:12px 28px;
              border-radius:4px;text-decoration:none;font-weight:bold">
      Reset Password
    </a>
  </p>
  <p>If you did not request a password reset, ignore this email — your
     password will remain unchanged.</p>
  <hr style="border:none;border-top:1px solid #ddd;margin:24px 0">
  <p style="font-size:12px;color:#777">
    This is an automated message from {app_name}. Please do not reply.
  </p>
</div>
""".replace("{style}", _BASE_STYLE)

_EMAIL_VERIFICATION_TEMPLATE = """
<div style="{style}">
  <h2 style="color:#1a73e8">{app_name}</h2>
  <h3>Verify Your Email Address</h3>
  <p>Thank you for registering! Please verify your email address by clicking
     the button below.</p>
  <p style="text-align:center;margin:32px 0">
    <a href="{verify_url}"
       style="background:#1a73e8;color:#fff;padding:12px 28px;
              border-radius:4px;text-decoration:none;font-weight:bold">
      Verify Email
    </a>
  </p>
  <hr style="border:none;border-top:1px solid #ddd;margin:24px 0">
  <p style="font-size:12px;color:#777">
    This is an automated message from {app_name}. Please do not reply.
  </p>
</div>
""".replace("{style}", _BASE_STYLE)

_WELCOME_TEMPLATE = """
<div style="{style}">
  <h2 style="color:#1a73e8">{app_name}</h2>
  <h3>Welcome, {full_name}!</h3>
  <p>Your account has been successfully created. You can now log in and
     start using {app_name}.</p>
  <hr style="border:none;border-top:1px solid #ddd;margin:24px 0">
  <p style="font-size:12px;color:#777">
    This is an automated message from {app_name}. Please do not reply.
  </p>
</div>
""".replace("{style}", _BASE_STYLE)


_NOTIFICATION_TEMPLATE = """
<div style="{style}">
  <h2 style="color:#1a73e8">{app_name}</h2>
  <h3>{title}</h3>
  <p>Hello {full_name},</p>
  <p>{message}</p>
  <p style="font-size:12px;color:#888">
    Type: {notification_type} | Priority: {priority}
  </p>
  <hr style="border:none;border-top:1px solid #ddd;margin:24px 0">
  <p style="font-size:12px;color:#777">
    This is an automated notification from {app_name}. Please do not reply.
  </p>
</div>
""".replace("{style}", _BASE_STYLE)


# ---------------------------------------------------------------------------
# Utility
# ---------------------------------------------------------------------------


def _strip_html(html: str) -> str:
    """Very basic HTML → plain text (for MIMEText fallback)."""
    import re

    clean = re.sub(r"<[^>]+>", "", html)
    return "\n".join(line.strip() for line in clean.splitlines() if line.strip())


# Module-level singleton
email_service = EmailService()

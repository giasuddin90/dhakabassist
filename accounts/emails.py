"""Emails about accounts."""

import logging

from django.conf import settings
from django.contrib.auth.tokens import default_token_generator
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode

from core.mail import send_email

from .tokens import email_confirmation_token

logger = logging.getLogger(__name__)


def send_welcome(user):
    """Email a student added by staff a link to choose their password.

    The link is a normal password-reset link, so it expires and works once
    like any other.
    """
    send_email(
        f"Your {settings.SITE['name']} account",
        "accounts/email/welcome.txt",
        {
            "user": user,
            "site": settings.SITE,
            "base_url": settings.SITE["base_url"],
            "uid": urlsafe_base64_encode(force_bytes(user.pk)),
            "token": default_token_generator.make_token(user),
        },
        to=[user.email],
        fail_silently=True,
    )


def send_confirmation(user):
    """Email a new student the link that confirms their address.

    Skipped while the last one is under `EMAIL_RESEND_SECONDS` old.
    A failed send is logged rather than raised (by the mail thread, or here
    if handing it over fails): the student still lands on the "check your
    email" page, which offers to send the link again.
    """
    if not user.claim_confirmation_send():
        logger.info("Skipped a confirmation email to user %s sent too soon", user.pk)
        return
    try:
        send_email(
            f"Confirm your {settings.SITE['name']} email",
            "accounts/email/confirm_email.txt",
            {
                "user": user,
                "base_url": settings.SITE["base_url"],
                "uid": urlsafe_base64_encode(force_bytes(user.pk)),
                "token": email_confirmation_token.make_token(user),
            },
            to=[user.email],
        )
    except OSError:  # smtplib.SMTPException is an OSError
        logger.exception("Could not send the confirmation email to user %s", user.pk)

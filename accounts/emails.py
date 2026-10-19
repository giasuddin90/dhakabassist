"""Emails about accounts."""

import logging

from django.conf import settings
from django.contrib.auth.tokens import default_token_generator
from django.core.mail import EmailMessage
from django.template.loader import render_to_string
from django.utils import translation
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode

from .tokens import email_confirmation_token

logger = logging.getLogger(__name__)


def send_welcome(user):
    """Email a student added by staff a link to choose their password.

    The link is a normal password-reset link, so it expires and works once
    like any other.
    """
    with translation.override(user.language):
        _send_welcome(user)


def _send_welcome(user):
    body = render_to_string(
        "accounts/email/welcome.txt",
        {
            "user": user,
            "site": settings.SITE,
            "base_url": settings.SITE["base_url"],
            "uid": urlsafe_base64_encode(force_bytes(user.pk)),
            "token": default_token_generator.make_token(user),
        },
    )
    EmailMessage(
        subject=translation.gettext("Your %(site)s account") % {"site": settings.SITE["name"]},
        body=body,
        to=[user.email],
    ).send(fail_silently=True)


def send_confirmation(user):
    """Email a new student the link that confirms their address.

    A failed send is logged rather than raised: the student still lands on
    the "check your email" page, which offers to send the link again.
    """
    with translation.override(user.language):
        body = render_to_string(
            "accounts/email/confirm_email.txt",
            {
                "user": user,
                "base_url": settings.SITE["base_url"],
                "uid": urlsafe_base64_encode(force_bytes(user.pk)),
                "token": email_confirmation_token.make_token(user),
            },
        )
        subject = translation.gettext("Confirm your %(site)s email") % {
            "site": settings.SITE["name"]
        }
    try:
        EmailMessage(subject=subject, body=body, to=[user.email]).send()
    except OSError:  # smtplib.SMTPException is an OSError
        logger.exception("Could not send the confirmation email to user %s", user.pk)

"""Emails about accounts."""

from django.conf import settings
from django.contrib.auth.tokens import default_token_generator
from django.core.mail import EmailMessage
from django.template.loader import render_to_string
from django.utils import translation
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode


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

"""Emails about orders."""

from django.conf import settings
from django.core.mail import EmailMessage
from django.template.loader import render_to_string
from django.utils import translation


def send_receipt(order):
    """Email the student their receipt. Never blocks the enrolment."""
    # In the student's language, whatever page (or callback) triggered it.
    with translation.override(order.student.language):
        _send_receipt(order)


def _send_receipt(order):
    body = render_to_string(
        "orders/email/receipt.txt",
        {"order": order, "site": settings.SITE, "base_url": settings.SITE["base_url"]},
    )
    EmailMessage(
        subject=translation.gettext("Your %(site)s receipt · %(reference)s")
        % {"site": settings.SITE["name"], "reference": order.reference},
        body=body,
        to=[order.student.email],
    ).send(fail_silently=True)

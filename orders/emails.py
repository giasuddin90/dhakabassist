"""Emails about orders."""

from django.conf import settings
from django.core.mail import EmailMessage
from django.template.loader import render_to_string


def send_receipt(order):
    """Email the student their receipt. Never blocks the enrolment."""
    body = render_to_string(
        "orders/email/receipt.txt",
        {"order": order, "site": settings.SITE, "base_url": settings.SITE["base_url"]},
    )
    EmailMessage(
        subject=f"Your {settings.SITE['name']} receipt · {order.reference}",
        body=body,
        to=[order.student.email],
    ).send(fail_silently=True)

"""Emails about orders."""

from django.conf import settings

from core.mail import send_email


def send_receipt(order):
    """Email the student their receipt. Never blocks the enrolment."""
    send_email(
        f"Your {settings.SITE['name']} receipt · {order.reference}",
        "orders/email/receipt.txt",
        {"order": order, "site": settings.SITE, "base_url": settings.SITE["base_url"]},
        to=[order.student.email],
        fail_silently=True,
    )

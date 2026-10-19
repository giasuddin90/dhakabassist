"""Purchases and the enrolment they unlock.

No card data is stored. An order keeps only what is needed to reconcile with
the gateway: the method chosen, the gateway's own reference, and the amount.
"""

import secrets

from django.conf import settings
from django.db import models, transaction
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from courses.models import Course, Enrollment, TimeStampedModel


class PaymentMethod(models.TextChoices):
    BKASH = "bkash", _("bKash")
    NAGAD = "nagad", _("Nagad")
    CARD = "card", _("Visa or Mastercard")
    INTERNATIONAL = "intl", _("International card")


PAYMENT_METHOD_HINTS = {
    PaymentMethod.BKASH: _("Pay from your bKash wallet"),
    PaymentMethod.NAGAD: _("Pay from your Nagad wallet"),
    PaymentMethod.CARD: _("Bangladeshi debit and credit cards"),
    PaymentMethod.INTERNATIONAL: _("Cards issued outside Bangladesh, charged in BDT"),
}


# `Order.gateway` for a payment staff recorded by hand (bKash or Nagad Send
# Money, cash) rather than one a gateway reported.
MANUAL_GATEWAY = "manual"


def generate_reference():
    """A short, non-sequential order number safe to show and quote."""
    return f"DB-{secrets.randbelow(90000) + 10000}"


class Order(TimeStampedModel):
    class Status(models.TextChoices):
        PENDING = "pending", _("Pending")
        PAID = "paid", _("Paid")
        FAILED = "failed", _("Failed")
        REFUNDED = "refunded", _("Refunded")

    reference = models.CharField(
        _("order number"), max_length=20, unique=True, default=generate_reference
    )
    student = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=_("student"),
        on_delete=models.PROTECT,
        related_name="orders",
    )
    course = models.ForeignKey(
        Course, verbose_name=_("course"), on_delete=models.PROTECT, related_name="orders"
    )
    amount = models.DecimalField(_("amount (BDT)"), max_digits=10, decimal_places=2)
    method = models.CharField(
        _("payment method"), max_length=12, choices=PaymentMethod.choices
    )
    status = models.CharField(
        _("status"), max_length=10, choices=Status.choices, default=Status.PENDING
    )
    gateway = models.CharField(_("gateway"), max_length=30, blank=True)
    gateway_reference = models.CharField(
        _("gateway reference"), max_length=100, blank=True, db_index=True
    )
    # Verification token echoed back by the gateway callback, so a forged
    # callback for someone else's order cannot mark it paid.
    callback_token = models.CharField(_("callback token"), max_length=64, blank=True)
    paid_at = models.DateTimeField(_("paid at"), null=True, blank=True)
    failure_reason = models.CharField(_("failure reason"), max_length=200, blank=True)

    class Meta:
        verbose_name = _("order")
        verbose_name_plural = _("orders")
        ordering = ("-created_at",)
        indexes = [models.Index(fields=("status", "-created_at"))]

    def __str__(self):
        return f"{self.reference} · {self.student} · {self.get_status_display()}"

    def save(self, *args, **kwargs):
        if not self.callback_token:
            self.callback_token = secrets.token_urlsafe(32)
        while Order.objects.filter(reference=self.reference).exclude(pk=self.pk).exists():
            self.reference = generate_reference()
        super().save(*args, **kwargs)

    @property
    def amount_display(self):
        """The amount as it appears in listings; a refund shows as negative."""
        from pages.templatetags.money import taka

        return taka(-self.amount if self.status == self.Status.REFUNDED else self.amount)

    @transaction.atomic
    def mark_paid(self, gateway_reference=""):
        """Record payment and enrol the student. Safe to call twice."""
        if self.status == self.Status.PAID:
            return False
        self.status = self.Status.PAID
        self.paid_at = timezone.now()
        self.failure_reason = ""
        if gateway_reference:
            self.gateway_reference = gateway_reference
        self.save(
            update_fields=[
                "status",
                "paid_at",
                "failure_reason",
                "gateway_reference",
                "updated_at",
            ]
        )
        self.enrol()
        return True

    def enrol(self):
        """Open the course this order paid for."""
        Enrollment.objects.update_or_create(
            student=self.student,
            course=self.course,
            defaults={"is_active": True, "granted_manually": False},
        )

    def set_course_access(self, enabled):
        """Open or close the course on a paid order by hand from /manage/.

        Closing it keeps the order paid, e.g. while a payment is disputed.
        """
        if self.status != self.Status.PAID:
            return
        if enabled:
            self.enrol()
        else:
            Enrollment.revoke(self.student, [self.course])

    @transaction.atomic
    def mark_refunded(self):
        """Record a refund issued in the gateway and withdraw the paid access.

        A manual grant is left alone: it was given for its own reason, not
        bought with this order.
        """
        order = Order.objects.select_for_update().get(pk=self.pk)
        if order.status != self.Status.PAID:
            return False
        self.status = order.status = self.Status.REFUNDED
        order.save(update_fields=["status", "updated_at"])
        self.withdraw_paid_access()
        return True

    @transaction.atomic
    def change_status(self, status):
        """Set the status by hand from /manage/ and keep course access in step.

        Paid enrols the student, as a gateway payment would. Leaving paid
        withdraws the access this order bought, as a refund would.
        """
        if status == self.Status.PAID:
            return self.mark_paid()
        order = Order.objects.select_for_update().get(pk=self.pk)
        if order.status == status:
            return False
        was_paid = order.status == self.Status.PAID
        self.status = status
        if status != self.Status.REFUNDED:
            # A refunded order was paid once; a pending or failed one never was.
            self.paid_at = None
        self.save(update_fields=["status", "paid_at", "updated_at"])
        if was_paid:
            self.withdraw_paid_access()
        return True

    def withdraw_paid_access(self):
        """Close the enrolment this order paid for.

        Kept when a manual grant or another paid order for the same course
        still covers it.
        """
        still_paid = (
            Order.objects.filter(
                student_id=self.student_id, course_id=self.course_id, status=self.Status.PAID
            )
            .exclude(pk=self.pk)
            .exists()
        )
        if not still_paid:
            Enrollment.objects.filter(
                student_id=self.student_id, course_id=self.course_id, granted_manually=False
            ).update(is_active=False)

    def mark_failed(self, reason=""):
        # A late "fail" or "cancel" callback must not undo a confirmed payment.
        if self.status == self.Status.PAID:
            return
        self.status = self.Status.FAILED
        self.failure_reason = reason[:200]
        self.save(update_fields=["status", "failure_reason", "updated_at"])

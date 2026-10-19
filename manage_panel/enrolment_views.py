"""Who may study what, changed by hand from /manage/.

Granting, revoking, recording a payment taken outside the gateway and
refunding all end in the same place: an `Enrollment` row, the only thing
`courses.access` reads. The gateway path enrols through `Order.mark_paid`
too, so both kinds of payment behave alike.
"""

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.views.decorators.http import require_POST

from courses.models import Course, Enrollment
from orders.emails import send_receipt
from orders.models import MANUAL_GATEWAY, Order

from .forms import ManualPaymentForm
from .views import staff_required

User = get_user_model()


@staff_required
@require_POST
def student_grant(request, pk):
    """Grant a course without a payment — refunds, comps, support fixes."""
    student = get_object_or_404(User, pk=pk, is_staff=False)
    course = get_object_or_404(Course, slug=request.POST.get("course", ""))
    Enrollment.objects.update_or_create(
        student=student,
        course=course,
        defaults={"is_active": True, "granted_manually": True},
    )
    messages.success(
        request, f"{student.get_full_name()} now has access to “{course.title}”."
    )
    return redirect(request.POST.get("next") or reverse("manage:students"))


@staff_required
@require_POST
def student_revoke(request, pk):
    """Withdraw one course. Orders stay as they are; refund those separately."""
    student = get_object_or_404(User, pk=pk, is_staff=False)
    course = get_object_or_404(Course, slug=request.POST.get("course", ""))
    Enrollment.objects.filter(student=student, course=course).update(is_active=False)
    messages.success(
        request, f"{student.get_full_name()} no longer has access to “{course.title}”."
    )
    return redirect(request.POST.get("next") or reverse("manage:students"))


@staff_required
@require_POST
def student_record_payment(request, pk):
    """Record a payment taken outside the gateway and enrol the student."""
    student = get_object_or_404(User, pk=pk, is_staff=False)
    form = ManualPaymentForm(request.POST, student=student)
    if not form.is_valid():
        errors = " ".join(e for field in form.errors.values() for e in field)
        messages.error(request, f"The payment was not recorded. {errors}")
    else:
        with transaction.atomic():
            order = form.save(commit=False)
            order.student = student
            order.gateway = MANUAL_GATEWAY
            order.save()
            order.mark_paid()
        send_receipt(order)
        messages.success(
            request,
            f"Order {order.reference} recorded. {student.get_full_name()} "
            f"now has access to “{order.course.title}”.",
        )
    return redirect(request.POST.get("next") or reverse("manage:students"))


@staff_required
@require_POST
def order_refund(request, reference):
    """Record a refund already issued in the gateway, and withdraw paid access."""
    order = get_object_or_404(Order.objects.select_related("course"), reference=reference)
    if order.mark_refunded():
        messages.success(
            request, f"Order {order.reference} is refunded and its course access withdrawn."
        )
    else:
        messages.warning(request, f"Order {order.reference} is not paid, so it was not refunded.")
    return redirect(request.POST.get("next") or reverse("manage:orders"))

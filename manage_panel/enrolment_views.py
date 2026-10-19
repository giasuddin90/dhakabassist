"""Who may study what, changed by hand from /manage/.

Granting, revoking, recording a payment taken outside the gateway, adding
or editing an order and refunding all end in the same place: an
`Enrollment` row, the only thing `courses.access` reads. The gateway path
enrols through `Order.mark_paid` too, so both kinds of payment behave alike.
"""

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from courses.models import Course, Enrollment
from orders.emails import send_receipt
from orders.models import MANUAL_GATEWAY, Order
from pages.seo import noindex

from .forms import ManualPaymentForm, NewOrderForm, OrderForm
from .views import nav_counts, staff_required

User = get_user_model()


@staff_required
@require_POST
def student_grant(request, pk):
    """Grant a course without a payment — refunds, comps, support fixes."""
    student = get_object_or_404(User, pk=pk, is_staff=False)
    course = get_object_or_404(Course, slug=request.POST.get("course", ""))
    Enrollment.grant(student, course)
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
    Enrollment.revoke(student, [course])
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


def return_url(request):
    """Where an order form goes back to: the page it came from, if on this site."""
    url = request.POST.get("next") or request.GET.get("next", "")
    if url_has_allowed_host_and_scheme(url, allowed_hosts={request.get_host()}):
        return url
    return reverse("manage:orders")


def render_order_form(request, form, order=None):
    """The add-order page, or the edit page when `order` is given."""
    title = f"Edit order {order.reference}" if order else "Add an order"
    return render(
        request,
        "manage_panel/order_form.html",
        {
            "form": form,
            "order": order,
            "next_url": return_url(request),
            "section": "orders",
            "counts": nav_counts(),
            "seo": noindex(title),
        },
    )


@staff_required
def order_create(request):
    """Add an order by hand for any student, paid or awaiting payment."""
    initial = {"student": request.GET["student"]} if "student" in request.GET else None
    form = NewOrderForm(request.POST or None, initial=initial)
    if request.method == "POST" and form.is_valid():
        order = form.save()
        if order.status == Order.Status.PAID:
            send_receipt(order)
            messages.success(
                request,
                f"Order {order.reference} recorded. {order.student.get_full_name()} "
                f"now has access to “{order.course.title}”.",
            )
        else:
            messages.success(request, f"Order {order.reference} added as pending.")
        return redirect(return_url(request))
    return render_order_form(request, form)


@staff_required
def order_edit(request, reference):
    """Correct an order's amount, method, transaction ID or status."""
    order = get_object_or_404(
        Order.objects.select_related("student", "course"), reference=reference
    )
    was_paid = order.status == Order.Status.PAID
    form = OrderForm(request.POST or None, instance=order)
    if request.method == "POST" and form.is_valid():
        form.save()
        if order.status == Order.Status.PAID and not was_paid:
            send_receipt(order)
        messages.success(request, f"Order {order.reference} has been saved.")
        return redirect(return_url(request))
    return render_order_form(request, form, order)

import logging

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse, HttpResponseRedirect
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.translation import gettext as _
from django.utils.translation import gettext_noop
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods, require_POST

from courses.access import CourseAccess, course_queryset
from courses.models import Course
from pages import seo

from .emails import send_receipt
from .gateways import GatewayError, get_gateway
from .models import PAYMENT_METHOD_HINTS, Order, PaymentMethod

logger = logging.getLogger(__name__)


def payment_methods():
    return [
        {
            "value": value,
            "label": label,
            "hint": PAYMENT_METHOD_HINTS[value],
        }
        for value, label in PaymentMethod.choices
    ]


@login_required
@require_http_methods(["GET", "POST"])
def checkout(request, slug):
    """Order summary and payment method, then hand off to the gateway."""
    course = get_object_or_404(
        course_queryset().filter(status=Course.Status.PUBLISHED), slug=slug
    )
    access = CourseAccess(request.user, course)
    if access.is_enrolled:
        messages.info(request, _("You already have access to this course."))
        return redirect("courses:dashboard")

    prerequisite = course.requires
    if prerequisite and not CourseAccess(request.user, prerequisite).is_enrolled:
        messages.warning(
            request,
            _("%(course)s is required before this course.") % {"course": prerequisite.title},
        )
        return redirect(prerequisite.get_absolute_url())

    selected = request.POST.get("method") or PaymentMethod.BKASH

    if request.method == "POST":
        if selected not in PaymentMethod.values:
            messages.error(request, _("Choose a payment method to continue."))
        else:
            order = Order.objects.create(
                student=request.user,
                course=course,
                amount=course.price,
                method=selected,
                gateway=settings.PAYMENT_GATEWAY,
            )
            request.session["pending_order"] = order.reference
            try:
                return HttpResponseRedirect(get_gateway().start_url(order, request))
            except GatewayError as exc:
                order.mark_failed(str(exc))
                logger.warning("Checkout failed for %s: %s", order.reference, exc)
                messages.error(
                    request,
                    _("The payment gateway could not be reached. Please try again."),
                )

    return render(
        request,
        "orders/checkout.html",
        {
            "course": course,
            "methods": payment_methods(),
            "selected": selected,
            "seo": seo.noindex(
                _("Checkout"),
                canonical_path=reverse("orders:checkout", kwargs={"slug": slug}),
            ),
        },
    )


@login_required
def sandbox(request, reference):
    """Local stand-in for the gateway's hosted payment page.

    Only reachable while `PAYMENT_GATEWAY=sandbox`; it never handles real card
    details, it just offers the two outcomes the callback has to cope with.
    """
    if settings.PAYMENT_GATEWAY != "sandbox":
        return HttpResponse(status=404)
    order = get_object_or_404(
        Order, reference=reference, student=request.user, status=Order.Status.PENDING
    )
    return render(
        request,
        "orders/sandbox.html",
        {
            "order": order,
            "method_label": order.get_method_display(),
            "seo": seo.noindex(_("Payment")),
        },
    )


def _finish(request, order, data):
    gateway = get_gateway()
    is_paid, gateway_reference, reason = gateway.verify(order, data)
    if is_paid:
        if order.mark_paid(gateway_reference):
            send_receipt(order)
        request.session.pop("pending_order", None)
        return redirect(reverse("orders:receipt", kwargs={"reference": order.reference}))
    order.mark_failed(reason)
    messages.error(request, _(reason) if reason else _("The payment did not complete."))
    return redirect(reverse("orders:checkout", kwargs={"slug": order.course.slug}))


@login_required
@require_POST
def sandbox_complete(request, reference):
    if settings.PAYMENT_GATEWAY != "sandbox":
        return HttpResponse(status=404)
    order = get_object_or_404(Order, reference=reference, student=request.user)
    return _finish(
        request,
        order,
        {"token": order.callback_token, "result": request.POST.get("result")},
    )


@csrf_exempt
@require_http_methods(["GET", "POST"])
def callback(request, outcome):
    """Where the gateway returns the student after payment.

    CSRF-exempt because the POST comes from the gateway, not from a page of
    ours; authenticity rests on the gateway's own signature plus the
    per-order token, both checked in `Gateway.verify`.
    """
    data = request.POST.dict() or request.GET.dict()
    reference = data.get("tran_id") or request.session.get("pending_order", "")
    order = Order.objects.filter(reference=reference).select_related("course").first()
    if order is None:
        messages.error(request, _("That payment could not be matched to an order."))
        return redirect("pages:home")
    if outcome != "success":
        # Stored in English for staff; shown to the student in their language.
        reason = {
            "fail": gettext_noop("Payment failed."),
            "cancel": gettext_noop("Payment cancelled."),
        }
        order.mark_failed(reason.get(outcome, ""))
        messages.error(
            request,
            _(order.failure_reason) if order.failure_reason else _("The payment did not complete."),
        )
        return redirect(reverse("orders:checkout", kwargs={"slug": order.course.slug}))
    return _finish(request, order, data)


@csrf_exempt
@require_POST
def ipn(request):
    """Server-to-server payment notification.

    The authoritative signal: it arrives even if the student closes the
    browser before being redirected back.
    """
    data = request.POST.dict()
    order = Order.objects.filter(reference=data.get("tran_id", "")).first()
    if order is None:
        return HttpResponse(status=404)
    is_paid, gateway_reference, reason = get_gateway().verify(order, data)
    if is_paid:
        if order.mark_paid(gateway_reference):
            send_receipt(order)
    elif order.status == Order.Status.PENDING:
        order.mark_failed(reason)
    return HttpResponse("ok", content_type="text/plain")


@login_required
def receipt(request, reference):
    order = get_object_or_404(
        Order.objects.select_related("course"), reference=reference, student=request.user
    )
    first_module = next(
        (m for m in order.course.module_list if m.status == "published"), None
    )
    return render(
        request,
        "orders/receipt.html",
        {
            "order": order,
            "first_module": first_module,
            "seo": seo.noindex("You are enrolled"),
        },
    )

"""Course promotions in /manage/: time-limited discounts such as BDT 1000 off
for November. They are listed and added from the course settings page."""

from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from courses.models import Course, Promotion
from pages.seo import noindex

from .forms import PromotionForm
from .views import nav_counts, staff_required


@staff_required
def promotion_edit(request, slug=None, pk=None):
    """Add a promotion to the course `slug`, or edit the promotion `pk`."""
    if pk:
        promotion = get_object_or_404(Promotion.objects.select_related("course"), pk=pk)
    else:
        promotion = Promotion(course=get_object_or_404(Course, slug=slug))
    course = promotion.course
    form = PromotionForm(request.POST or None, instance=promotion)
    if request.method == "POST" and form.is_valid():
        promotion = form.save()
        messages.success(request, f"“{promotion.name}” has been saved.")
        return redirect("manage:course_edit", slug=course.slug)
    return render(
        request,
        "manage_panel/promotion_form.html",
        {
            "form": form,
            "course": course,
            "promotion": promotion if pk else None,
            "section": "courses",
            "counts": nav_counts(),
            "seo": noindex(promotion.name if pk else "New promotion"),
        },
    )


@staff_required
@require_POST
def promotion_delete(request, pk):
    """Delete a promotion nobody bought under.

    Orders protect the row so sales stay linked to the offer, so one that
    sold something is ended early by moving its last day instead.
    """
    promotion = get_object_or_404(Promotion.objects.select_related("course"), pk=pk)
    slug, name = promotion.course.slug, promotion.name
    if promotion.orders.exists():
        messages.error(
            request,
            f"“{name}” has orders, so it cannot be deleted. To stop it early, "
            "set its last day to yesterday.",
        )
    else:
        promotion.delete()
        messages.success(request, f"“{name}” has been deleted.")
    return redirect("manage:course_edit", slug=slug)

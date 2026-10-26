"""Downloads in /manage/: the worksheets, PDFs, audio and ZIPs on the
public downloads page, free or paid."""

from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from courses.i18n import columns
from downloads.models import Download
from orders.models import Order
from pages.seo import noindex

from .forms import DownloadForm
from .views import ManageBase, nav_counts, staff_required


# Seven of the eight ancestors are Django's own view classes.
class DownloadsView(ManageBase):  # pylint: disable=too-many-ancestors
    """Every download with its price, status and number sold."""

    template_name = "manage_panel/downloads.html"
    section = "downloads"
    heading = "Downloads"
    paginate_by = 25

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        rows = Download.objects.annotate(
            sales=Count("orders", filter=Q(orders__status=Order.Status.PAID))
        )
        page = Paginator(rows, self.paginate_by).get_page(self.request.GET.get("page"))
        context.update(
            page=page,
            page_range=page.paginator.get_elided_page_range(page.number, on_each_side=1),
        )
        return context


@staff_required
def download_edit(request, slug=None):
    """Create or edit a download: titles, files per language, price and status."""
    download = get_object_or_404(Download, slug=slug) if slug else None
    form = DownloadForm(request.POST or None, request.FILES or None, instance=download)
    if request.method == "POST" and form.is_valid():
        download = form.save()
        messages.success(request, f"“{download.title}” has been saved.")
        return redirect("manage:downloads")
    return render(
        request,
        "manage_panel/download_form.html",
        {
            "form": form,
            "download": download,
            "section": "downloads",
            "counts": nav_counts(),
            "seo": noindex(download.title if download else "New download"),
        },
    )


@staff_required
@require_POST
def download_delete(request, slug):
    """Delete a download nobody has ordered, with its files.

    Orders protect the row: a buyer keeps their purchase, so a download
    with orders is set to Draft instead.
    """
    download = get_object_or_404(Download, slug=slug)
    title = download.title
    if download.orders.exists():
        messages.error(
            request,
            f"“{title}” has orders, so it cannot be deleted. Set it to Draft to take "
            "it off the downloads page; buyers keep their copy.",
        )
    else:
        for column in columns("file"):
            getattr(download, column).delete(save=False)
        download.delete()
        messages.success(request, f"“{title}” has been deleted.")
    return redirect("manage:downloads")

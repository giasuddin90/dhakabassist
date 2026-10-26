"""The public downloads list, the files themselves, and a student's bought downloads."""

from urllib.parse import urlencode

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.utils.translation import gettext as _
from django.views.generic import ListView

from courses.views import _serve_media
from pages import seo

from .models import Download

PER_PAGE = 12


# One hook is the whole of the mixin.
class PagedListMixin:  # pylint: disable=too-few-public-methods
    """Twelve cards a page, with the page links `includes/pagination.html` needs."""

    paginate_by = PER_PAGE
    context_object_name = "downloads"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        page = context["page_obj"]
        context["page_range"] = page.paginator.get_elided_page_range(page.number, on_each_side=1)
        context["nav_active"] = "downloads"
        return context


# Django's ListView alone is seven ancestors deep, so any mixin passes pylint's limit.
class DownloadListView(PagedListMixin, ListView):  # pylint: disable=too-many-ancestors
    """Every published download, filterable by type."""

    template_name = "downloads/list.html"

    @property
    def kind(self):
        """The type filter from the query string, or "" for every type."""
        value = self.request.GET.get("type", "")
        return value if value in Download.Kind.values else ""

    def get_queryset(self):
        downloads = Download.objects.published()
        return downloads.filter(kind=self.kind) if self.kind else downloads

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        page = context["page_obj"]
        user = self.request.user
        owned = set()
        if user.is_authenticated:
            # One query for the whole page, not one per card.
            owned = set(
                Download.objects.bought_by(user)
                .filter(pk__in=[d.pk for d in page])
                .values_list("pk", flat=True)
            )
        params = {"type": self.kind, "page": page.number if page.number > 1 else ""}
        query = urlencode({k: v for k, v in params.items() if v})
        path = reverse("downloads:list") + (f"?{query}" if query else "")
        title = _("Downloads: worksheets, PDFs and audio")
        if page.number > 1:
            title = _("%(title)s, page %(number)s") % {"title": title, "number": page.number}
        context.update(
            owned=owned,
            kind=self.kind,
            filters=[("", _("All"))] + list(Download.Kind.choices),
            seo=seo.SEO(
                title=title,
                description=_(
                    "Music theory worksheets, PDFs, audio and ZIP bundles. Free ones "
                    "need only an account; paid ones are a one-time payment in BDT."
                ),
                canonical_path=path,
                breadcrumbs=[seo.Breadcrumb(_("Home"), "/"), seo.Breadcrumb(_("Downloads"))],
                schemas=[seo.downloads_schema(page, path)],
            ),
        )
        return context


class MyDownloadsView(  # pylint: disable=too-many-ancestors  # as DownloadListView
    LoginRequiredMixin, PagedListMixin, ListView
):
    """The downloads a student has bought, to fetch again at any time."""

    template_name = "downloads/mine.html"

    def get_queryset(self):
        return Download.objects.bought_by(self.request.user)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["seo"] = seo.noindex(_("My downloads"), canonical_path=reverse("downloads:mine"))
        return context


@login_required
def download_file(request, slug):
    """The file, for staff, anyone signed in when it is free, and its buyers."""
    download = get_object_or_404(Download, slug=slug)
    if not download.is_available_to(request.user):
        if download.status == Download.Status.PUBLISHED:
            messages.info(request, _("Buy this download to get the file."))
            return redirect(download.get_buy_url())
        raise Http404("No such download.")
    if not download.file:
        raise Http404("No file for this download.")
    return _serve_media(download.file.name, download_name=download.filename, as_attachment=True)

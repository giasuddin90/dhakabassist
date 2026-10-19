from django.conf import settings
from django.contrib import admin
from django.contrib.sitemaps.views import sitemap
from django.urls import include, path
from django.views.generic import RedirectView

from pages import views as page_views
from pages.sitemaps import SITEMAPS

admin.site.site_header = "DhakaBassist"
admin.site.site_title = "DhakaBassist"
admin.site.index_title = "Database administration"

urlpatterns = [
    path("", include("pages.urls")),
    path("", include("courses.urls")),
    path("", include("accounts.urls")),
    path("", include("orders.urls")),
    path("manage/", include("manage_panel.urls")),
    path("django-admin/", admin.site.urls),
    # Discovery
    path(
        "sitemap.xml",
        sitemap,
        {"sitemaps": SITEMAPS},
        name="django.contrib.sitemaps.views.sitemap",
    ),
    path("robots.txt", page_views.RobotsView.as_view(), name="robots"),
    path("llms.txt", page_views.LlmsTxtView.as_view(), name="llms"),
    path(
        "favicon.ico",
        RedirectView.as_view(url=settings.STATIC_URL + "img/logo-mark.svg", permanent=True),
    ),
    path("healthz", page_views.health, name="health"),
]

handler404 = "pages.views.not_found"
handler500 = "pages.views.server_error"

# MEDIA_ROOT is deliberately not served here, even in development: everything
# in it is course material, reachable only through the access-checked views.

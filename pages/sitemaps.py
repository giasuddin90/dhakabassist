"""Sitemaps for public pages only.

Signed-in pages (dashboard, lessons, quizzes, checkout) are deliberately
absent and are also marked `noindex` by their views.
"""

from django.contrib.sitemaps import Sitemap
from django.urls import reverse

from courses.models import Course

from .models import LegalPage


class StaticViewSitemap(Sitemap):
    protocol = "https"
    changefreq = "monthly"

    def items(self):
        return [
            ("pages:home", 1.0),
            ("courses:list", 0.8),
            ("pages:about", 0.6),
            ("pages:faq", 0.6),
        ]

    def location(self, item):
        return reverse(item[0])

    def priority(self, item):
        return item[1]


class CourseSitemap(Sitemap):
    protocol = "https"
    changefreq = "weekly"
    priority = 0.9

    def items(self):
        return Course.published.all()

    def lastmod(self, obj):
        return obj.updated_at


class LegalSitemap(Sitemap):
    protocol = "https"
    changefreq = "yearly"
    priority = 0.3

    def items(self):
        return LegalPage.objects.filter(is_published=True)

    def lastmod(self, obj):
        return obj.updated_at


SITEMAPS = {
    "pages": StaticViewSitemap,
    "courses": CourseSitemap,
    "legal": LegalSitemap,
}

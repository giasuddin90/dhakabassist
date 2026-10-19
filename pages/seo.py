"""Per-page metadata and JSON-LD.

Views build a small `SEO` object; `base.html` renders it. Keeping the shape
in one place means every page gets a canonical URL, an Open Graph image and a
sensible title without each view remembering to.
"""

import json
from dataclasses import dataclass, field

from django.conf import settings
from django.templatetags.static import static
from django.urls import reverse, translate_url
from django.utils import translation
from django.utils.html import escape
from django.utils.safestring import mark_safe
from django.utils.translation import get_language_from_path


def absolute(path):
    """A fully qualified URL for `path`, which may already be absolute."""
    if path.startswith(("http://", "https://")):
        return path
    base = settings.SITE["base_url"]
    return f"{base}{path if path.startswith('/') else '/' + path}"


def localized(path, language=None):
    """`path` in `language` (default: the active one), e.g. "/" -> "/en/".

    Views hand over paths like "/" that carry no language, so the canonical
    URL, hreflang links and breadcrumbs all go through here. The path is
    resolved in its own language (a bare path is Bangla), since `/` is not
    an English address.
    """
    target = language or translation.get_language()
    with translation.override(get_language_from_path(path) or settings.LANGUAGE_CODE):
        return translate_url(path, target)


@dataclass
class Breadcrumb:
    name: str
    url: str = ""

    def __post_init__(self):
        if self.url:
            self.url = localized(self.url)


@dataclass
class SEO:
    title: str
    description: str = ""
    canonical_path: str = ""
    image_path: str = ""
    kind: str = "website"
    robots: str = "index, follow"
    breadcrumbs: list = field(default_factory=list)
    schemas: list = field(default_factory=list)

    @property
    def full_title(self):
        name = settings.SITE["name"]
        return self.title if self.title.startswith(name) else f"{self.title} · {name}"

    @property
    def canonical(self):
        return absolute(localized(self.canonical_path or "/"))

    @property
    def alternates(self):
        """(hreflang, URL) pairs for every language, plus x-default.

        Private pages are not indexed, so they get none.
        """
        if self.robots.startswith("noindex"):
            return []
        path = self.canonical_path or "/"
        pairs = [(code, absolute(localized(path, code))) for code, _name in settings.LANGUAGES]
        pairs.append(("x-default", absolute(localized(path, settings.LANGUAGE_CODE))))
        return pairs

    @property
    def image(self):
        return absolute(self.image_path or static("img/instructor-640.jpg"))

    @property
    def json_ld(self):
        """All structured data for the page as one `@graph` script body."""
        graph = [organization()] + list(self.schemas)
        if self.breadcrumbs:
            graph.append(breadcrumb_list(self.breadcrumbs))
        payload = {"@context": "https://schema.org", "@graph": graph}
        return mark_safe(
            json.dumps(payload, ensure_ascii=False).replace("</", "<\\/")
        )


def noindex(title, description="", canonical_path=""):
    """Metadata for a signed-in page that must stay out of search results."""
    return SEO(
        title=title,
        description=description,
        canonical_path=canonical_path,
        robots="noindex, nofollow",
    )


# -- schema.org builders ----------------------------------------------------


def organization():
    site = settings.SITE
    return {
        "@type": "EducationalOrganization",
        "@id": absolute("/") + "#organization",
        "name": site["name"],
        "url": absolute("/"),
        "logo": absolute(static("img/logo-full.svg")),
        "email": site["email"],
        "description": site["tagline"],
        "address": {"@type": "PostalAddress", "addressLocality": "Dhaka", "addressCountry": "BD"},
        "founder": {"@type": "Person", "name": site["instructor"]},
    }


def person(name, description=""):
    return {
        "@type": "Person",
        "name": name,
        "description": description,
        "worksFor": {"@id": absolute("/") + "#organization"},
    }


def author_person(author, description=""):
    """An `Author` as a `Person`, with their photo when there is one."""
    data = person(author.name, description)
    if author.photo:
        data["image"] = absolute(author.photo_url)
    return data


def course_author(course):
    """The course's author as a `Person`, or the site's instructor when none is linked."""
    if course.author:
        return author_person(course.author)
    return person(course.author_name)


def course_schema(course):
    """`Course` plus a `CourseInstance`, which search engines expect together."""
    site = settings.SITE
    data = {
        "@type": "Course",
        "@id": absolute(course.get_absolute_url()) + "#course",
        "name": course.title,
        "url": absolute(course.get_absolute_url()),
        "description": course.summary,
        "inLanguage": translation.get_language(),
        "educationalLevel": course.level,
        "numberOfCredits": course.module_count,
        "teaches": [m.title for m in course.module_list],
        "provider": {"@id": absolute("/") + "#organization"},
        "instructor": course_author(course),
        "isAccessibleForFree": False,
        "offers": {
            "@type": "Offer",
            "price": f"{course.price:.0f}",
            "priceCurrency": site["currency"],
            "availability": "https://schema.org/InStock",
            "url": absolute(reverse("orders:checkout", kwargs={"slug": course.slug})),
            "category": "Paid",
        },
        "hasCourseInstance": {
            "@type": "CourseInstance",
            "courseMode": "online",
            "courseWorkload": course.iso_duration or "PT2H20M",
            "instructor": course_author(course),
        },
    }
    free = course.free_module
    if free:
        data["hasPart"] = {
            "@type": "Course",
            "name": free.title,
            "description": free.summary,
            "isAccessibleForFree": True,
            "provider": {"@id": absolute("/") + "#organization"},
        }
    return data


def faq_schema(faqs):
    return {
        "@type": "FAQPage",
        "mainEntity": [
            {
                "@type": "Question",
                "name": item.question,
                "acceptedAnswer": {"@type": "Answer", "text": item.answer},
            }
            for item in faqs
        ],
    }


def article_schema(title, description, path, updated=None):
    return {
        "@type": "Article",
        "headline": title,
        "description": description,
        "url": absolute(path),
        "datePublished": updated.isoformat() if updated else None,
        "dateModified": updated.isoformat() if updated else None,
        "author": person(settings.SITE["instructor"]),
        "publisher": {"@id": absolute("/") + "#organization"},
    }


def breadcrumb_list(crumbs):
    return {
        "@type": "BreadcrumbList",
        "itemListElement": [
            {
                "@type": "ListItem",
                "position": index,
                "name": escape(crumb.name),
                **({"item": absolute(crumb.url)} if crumb.url else {}),
            }
            for index, crumb in enumerate(crumbs, start=1)
        ],
    }

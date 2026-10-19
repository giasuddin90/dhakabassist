from django.conf import settings
from django.urls import translate_url
from django.utils import translation
from django.utils.functional import SimpleLazyObject
from django.utils.translation import gettext, gettext_noop

from courses.i18n import columns
from courses.models import Course

# The settings hold these in English (for JSON-LD and staff); pages show
# them in the visitor's language.
TRANSLATED_SITE_TEXT = {
    "tagline": gettext_noop("Music theory courses by Tanveer Haque."),
    "instructor": gettext_noop("Tanveer Haque"),
    "location": gettext_noop("Dhaka, Bangladesh"),
}


def _primary_course():
    """The course the header's Enroll button points at.

    Lazy, so pages that never render the button pay no query.
    """
    return (
        Course.published.only("slug", *columns("title"), "price")
        .order_by(*Course.HOME_ORDERING)
        .first()
    )


def _language_links(request):
    """The current page in every language, for the masthead switcher."""
    current = translation.get_language()
    return [
        {
            "code": code,
            "name": name,
            "url": translate_url(request.get_full_path(), code),
            "is_current": code == current,
        }
        for code, name in settings.LANGUAGES
    ]


def site(request):
    locales = settings.SITE["locales"]
    current = translation.get_language()
    return {
        "site": {
            **settings.SITE,
            **{key: gettext(settings.SITE[key]) for key in TRANSLATED_SITE_TEXT},
        },
        "og_locale": locales.get(current, locales[settings.LANGUAGE_CODE]),
        "og_locale_alternates": [v for k, v in locales.items() if k != current],
        "language_links": _language_links(request),
        "primary_course": SimpleLazyObject(_primary_course),
    }

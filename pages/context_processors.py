from django.conf import settings
from django.utils.functional import SimpleLazyObject

from courses.models import Course


def _primary_course():
    """The course the header's Enroll button points at.

    Lazy, so pages that never render the button pay no query.
    """
    return (
        Course.published.only("slug", "title", "price").order_by("position", "title").first()
    )


def site(request):
    return {
        "site": settings.SITE,
        "primary_course": SimpleLazyObject(_primary_course),
    }

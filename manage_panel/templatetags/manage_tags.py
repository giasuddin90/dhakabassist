"""Template helpers for the administration panel."""

from django import template

from courses.models import format_runtime

register = template.Library()


@register.simple_tag(takes_context=True)
def querystring(context, **changes):
    """The current query string with some values replaced or removed.

    A stand-in for Django 5.1's built-in tag of the same name, so a page or
    folder link keeps the search and filters already applied. Pass `None` to
    drop a key, e.g. `{% querystring folder=row.folder page=None %}`.
    """
    params = context["request"].GET.copy()
    for key, value in changes.items():
        if value is None or value == "":
            params.pop(key, None)
        else:
            params[key] = value
    encoded = params.urlencode()
    return f"?{encoded}" if encoded else context["request"].path


@register.filter
def runtime(seconds):
    """Seconds as "1 hr 5 min" or "12 min", for watch time."""
    return format_runtime(seconds or 0)

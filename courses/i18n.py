"""Content stored in both languages.

Each translatable field, text or media, is two real columns, `<name>_bn`
and `<name>_en`.
`translated("<name>")` puts a `<name>` property on the model that returns
the active language's value and falls back to the other language when that
one is blank, so a page never shows an empty title just because a
translation has not been written yet.
"""

from django.conf import settings
from django.db import models
from django.utils import translation

LANGUAGE_CODES = tuple(code for code, _name in settings.LANGUAGES)


def active_language():
    """The active language code, or the primary one outside any request."""
    active = translation.get_language()
    return active if active in LANGUAGE_CODES else settings.LANGUAGE_CODE


def language_order():
    """Language codes, the active one first, so lookups fall back in order."""
    active = active_language()
    return (active, *(code for code in LANGUAGE_CODES if code != active))


def pick(obj, name, key=None):
    """`<name>_<code>` for the first language, in `language_order()`, whose
    `<key>_<code>` is filled in (`key` defaults to `name`).

    `key` keeps a set of columns together: a video's duration and subtitles
    come from the same language as the video that is actually played.
    """
    order = language_order()
    for code in order:
        if getattr(obj, f"{key or name}_{code}"):
            return getattr(obj, f"{name}_{code}")
    return getattr(obj, f"{name}_{order[0]}")


def active_column(name):
    """The column `<name>` is written to in the active language, e.g. "title_en"."""
    return f"{name}_{active_language()}"


def translated(name, key=None):
    """A property for `<name>_bn` / `<name>_en` in the active language.

    Reading falls back to the other language (see `pick` for `key`);
    assigning writes the active language's column only. Django passes model
    keyword arguments that name a property to its setter, so
    `Course(title="…")` works too.
    """
    return property(
        lambda self: pick(self, name, key),
        lambda self, value: setattr(self, active_column(name), value),
        doc=f"`{name}` in the active language.",
    )


def missing_language(obj, names, code):
    """True when any of `names` has text in another language but not `code`.

    Lets the staff panel flag content still waiting for a translation.
    """
    return any(
        not getattr(obj, f"{name}_{code}")
        and any(getattr(obj, column) for column in columns(name))
        for name in names
    )


def columns(name):
    """Every column behind a translated field, e.g. ("title_bn", "title_en")."""
    return tuple(f"{name}_{code}" for code in LANGUAGE_CODES)


def in_some_language(model_name, name):
    """A check that at least one language of a required field is filled in."""
    condition = models.Q()
    for column in columns(name):
        condition |= ~models.Q(**{column: ""})
    return models.CheckConstraint(check=condition, name=f"{model_name}_{name}_in_some_language")

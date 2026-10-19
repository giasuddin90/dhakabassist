"""Render lesson notes from Markdown to sanitised HTML.

Notes are authored by administrators, not students, but they are still
sanitised: an account compromise should not turn into stored XSS for every
student reading the lesson.
"""

import re

import bleach
import markdown
from django.utils.safestring import mark_safe

# bleach's `strip=True` removes a disallowed tag but keeps its text, which for
# a <script> block would leave the code visible in the lesson. Dropping these
# two elements whole, before Markdown runs, keeps the notes readable.
DROP_WHOLE = re.compile(r"<(script|style|iframe|object|embed)\b.*?</\1\s*>", re.I | re.S)

ALLOWED_TAGS = [
    "p", "br", "hr", "strong", "em", "code", "pre", "blockquote",
    "h2", "h3", "h4", "ul", "ol", "li", "a", "img", "figure", "figcaption",
    "table", "thead", "tbody", "tr", "th", "td", "audio", "source", "sup", "sub",
]

ALLOWED_ATTRIBUTES = {
    "a": ["href", "title", "rel", "target"],
    "img": ["src", "alt", "width", "height", "loading", "decoding"],
    "audio": ["controls", "preload", "src"],
    "source": ["src", "type"],
    "th": ["scope", "colspan", "rowspan"],
    "td": ["colspan", "rowspan"],
}

ALLOWED_PROTOCOLS = ["http", "https", "mailto"]

# `![Scale in C](/library/…/scale.mp3)` is how an administrator embeds audio
# from the media library: one syntax for every file, so Markdown's image tag
# is swapped for a player when its source is an audio file.
AUDIO_IMAGE = re.compile(
    r'<img\b[^>]*?\bsrc="([^"]+\.(?:mp3|m4a|ogg|wav))"[^>]*>', re.IGNORECASE
)

_renderer = markdown.Markdown(
    extensions=["extra", "sane_lists", "smarty"], output_format="html"
)


def render_notes(text):
    """Markdown -> safe HTML, with lazy-loaded images and safe outbound links."""
    if not text:
        return ""
    _renderer.reset()
    html = _renderer.convert(DROP_WHOLE.sub("", text))
    cleaner = bleach.Cleaner(
        tags=ALLOWED_TAGS,
        attributes=ALLOWED_ATTRIBUTES,
        protocols=ALLOWED_PROTOCOLS,
        strip=True,
        filters=[],
    )
    html = cleaner.clean(html)
    html = AUDIO_IMAGE.sub(r'<audio src="\1"></audio>', html)
    # Defaults the editor should not have to repeat in every note.
    html = html.replace("<img ", '<img loading="lazy" decoding="async" ')
    html = html.replace("<audio ", '<audio controls preload="none" ')
    return mark_safe(html)  # noqa: S308 - sanitised by bleach immediately above

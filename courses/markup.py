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

# A text link to a media library file is a download (the server sends it as an
# attachment), so it gets a class that marks it as one for the student.
LIBRARY_LINK = re.compile(r'<a href="(/library/[^"]+)"')

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
    html = LIBRARY_LINK.sub(r'<a class="file-link" href="\1"', html)
    # Defaults the editor should not have to repeat in every note.
    html = html.replace("<img ", '<img loading="lazy" decoding="async" ')
    html = html.replace("<audio ", '<audio controls preload="none" ')
    return mark_safe(html)  # noqa: S308 - sanitised by bleach immediately above


# One paragraph and nothing else: what a quiz title or answer option renders to.
SINGLE_PARAGRAPH = re.compile(r"\A<p>((?:(?!</?p>).)*)</p>\Z", re.DOTALL)
AUDIO_PLAYER = re.compile(r"<audio\b[^>]*>.*?</audio>", re.DOTALL)


def render_inline(text):
    """Markdown for one-line fields, without the paragraph around it.

    Quiz titles and answer options sit inside a heading or a button, where a
    <p> is not allowed. Longer text keeps its paragraphs.
    """
    html = render_notes(text)
    match = SINGLE_PARAGRAPH.match(html)
    # Both branches are output of `render_notes`, already sanitised by bleach.
    return mark_safe(match.group(1)) if match else html


def split_audio(html):
    """Separate audio players from the rest of some rendered HTML.

    A player inside an answer button would submit the answer when pressed,
    so the quiz shows an option's audio beside its button instead.
    """
    players = "".join(AUDIO_PLAYER.findall(html))
    rest = AUDIO_PLAYER.sub("", html).strip()
    # Pieces of `render_notes` output, already sanitised by bleach.
    return mark_safe(rest), mark_safe(players)

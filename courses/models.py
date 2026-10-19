"""Course content, enrolment, progress and quizzes.

Shape: Course -> Module -> (video, markdown notes, MediaAsset*, Quiz).
A module is reachable when it is the free preview, or when the student is
enrolled and has passed every earlier module's quiz.
"""

import html
import re
import secrets
from pathlib import Path

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import FileExtensionValidator, MinValueValidator
from django.db import models, transaction
from django.db.models import F
from django.urls import reverse
from django.utils import timezone
from django.utils.functional import cached_property
from django.utils.html import strip_tags
from django.utils.text import slugify
from django.utils.translation import gettext_lazy as _

from .markup import render_inline, render_notes, split_audio
from .video import trailer_embed_url


def validate_trailer_url(value):
    """Accept only links `trailer_embed_url` can turn into an embed."""
    if not trailer_embed_url(value):
        raise ValidationError(
            _("Paste a YouTube or Cloudflare Stream link to the video."),
            code="invalid_trailer",
        )


def format_runtime(seconds):
    """Seconds as a human string, e.g. "2 hr 20 min" or "45 min"."""
    hours, minutes = divmod(round(seconds / 60), 60)
    return f"{hours} hr {minutes} min" if hours else f"{minutes} min"


# No SVG: the photo is served publicly, and an SVG can carry script.
AUTHOR_PHOTO_EXTENSIONS = ("jpg", "jpeg", "png", "webp")


def author_photo_upload_to(instance, filename):
    """Keep each author's photo in their own folder."""
    return f"authors/{instance.slug or slugify(instance.name)}/{filename}"


class TimeStampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True, editable=False)
    updated_at = models.DateTimeField(auto_now=True, editable=False)

    class Meta:
        abstract = True


class Author(TimeStampedModel):
    """The person who teaches a course. One author can teach many courses."""

    name = models.CharField(_("name"), max_length=120)
    slug = models.SlugField(
        _("slug"),
        max_length=140,
        unique=True,
        blank=True,
        help_text=_("Left blank, it is made from the name."),
    )
    photo = models.ImageField(
        _("photo"),
        upload_to=author_photo_upload_to,
        max_length=255,
        blank=True,
        validators=[FileExtensionValidator(AUTHOR_PHOTO_EXTENSIONS)],
        help_text=_("A square JPG, PNG or WEBP, at least 320 × 320 px, up to 5 MB."),
    )
    bio = models.TextField(
        _("bio"),
        blank=True,
        help_text=_("Markdown. Shown under “About the author” on the course page."),
    )

    class Meta:
        verbose_name = _("author")
        verbose_name_plural = _("authors")
        ordering = ("name", "id")

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = self._unique_slug()
        super().save(*args, **kwargs)

    def _unique_slug(self):
        """The name as a slug, numbered when another author already has it."""
        base = slugify(self.name)[:130] or "author"
        slug, number = base, 2
        while Author.objects.filter(slug=slug).exclude(pk=self.pk).exists():
            slug, number = f"{base}-{number}", number + 1
        return slug

    @property
    def photo_url(self):
        """The public URL of the photo, or "" when there is none."""
        if not self.photo:
            return ""
        # The version busts the browser cache when the photo is replaced.
        url = reverse("courses:author_photo", kwargs={"slug": self.slug})
        return f"{url}?v={int(self.updated_at.timestamp())}"

    @property
    def bio_html(self):
        """The Markdown bio as sanitised HTML."""
        return render_notes(self.bio)

    @property
    def bio_text(self):
        """The bio as one line of plain text, for meta descriptions."""
        return " ".join(html.unescape(strip_tags(self.bio_html)).split())


class PublishedCourseManager(models.Manager):
    def get_queryset(self):
        return super().get_queryset().filter(status=Course.Status.PUBLISHED)


class Course(TimeStampedModel):
    class Status(models.TextChoices):
        DRAFT = "draft", _("Draft")
        PUBLISHED = "published", _("Published")

    title = models.CharField(_("title"), max_length=160)
    slug = models.SlugField(_("slug"), max_length=180, unique=True)
    subtitle = models.CharField(_("subtitle"), max_length=200, blank=True)
    summary = models.TextField(
        _("summary"),
        help_text=_("One or two sentences. Used on cards and in search results."),
    )
    description = models.TextField(
        _("description"), help_text=_("Markdown. Shown on the course page.")
    )
    level = models.CharField(_("level"), max_length=60, default="Beginner")
    price = models.DecimalField(
        _("price (BDT)"), max_digits=10, decimal_places=2, default=3500
    )
    status = models.CharField(
        _("status"), max_length=12, choices=Status.choices, default=Status.DRAFT
    )
    trailer_url = models.URLField(
        _("trailer video link"),
        max_length=300,
        blank=True,
        validators=[validate_trailer_url],
        help_text=_(
            "A YouTube or Cloudflare Stream link. The trailer is public, so for "
            "Cloudflare turn off “require signed URLs” on this video."
        ),
    )
    trailer_label = models.CharField(
        _("trailer label"), max_length=60, blank=True, default="Watch the trailer"
    )
    trailer_duration = models.CharField(
        _("trailer duration"), max_length=16, blank=True
    )
    # A later part can require an earlier one, which covers the Part 1 -> Part 2
    # progression in the brief without a separate bundling model.
    requires = models.ForeignKey(
        "self",
        verbose_name=_("requires"),
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="unlocks",
        help_text=_("Students must own this course first."),
    )
    position = models.PositiveIntegerField(_("position"), default=0)
    # PROTECT: an author who still teaches a course cannot be deleted by
    # accident; reassign or clear the courses first.
    author = models.ForeignKey(
        Author,
        verbose_name=_("author"),
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="courses",
    )
    promote_on_home = models.BooleanField(
        _("promote on home page"),
        default=False,
        help_text=_(
            "Feature this course on the home page. Only one course can be "
            "featured, so ticking this clears it on the others."
        ),
    )

    meta_title = models.CharField(_("meta title"), max_length=70, blank=True)
    meta_description = models.CharField(
        _("meta description"), max_length=170, blank=True
    )

    objects = models.Manager()
    published = PublishedCourseManager()

    # The home page and the header's Enroll button show the promoted course,
    # falling back to the first published one when none is promoted.
    HOME_ORDERING = ("-promote_on_home", "position", "title")

    class Meta:
        verbose_name = _("course")
        verbose_name_plural = _("courses")
        ordering = ("position", "title")

    def __str__(self):
        return self.title

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.title)[:180]
        super().save(*args, **kwargs)
        if self.promote_on_home:
            Course.objects.exclude(pk=self.pk).filter(promote_on_home=True).update(
                promote_on_home=False
            )

    def get_absolute_url(self):
        return reverse("courses:detail", kwargs={"slug": self.slug})

    @cached_property
    def trailer_embed_url(self):
        return trailer_embed_url(self.trailer_url)

    @property
    def author_name(self):
        """The author's name, or the site's instructor when none is linked."""
        return self.author.name if self.author else settings.SITE["instructor"]

    @cached_property
    def module_list(self):
        return list(self.modules.all())

    @property
    def module_count(self):
        return len(self.module_list)

    @property
    def free_module(self):
        return next((m for m in self.module_list if m.is_free), None)

    @property
    def total_runtime(self):
        """Sum of module video durations as a human string, e.g. "2 hr 20 min"."""
        seconds = sum(m.video_duration_seconds for m in self.module_list)
        return format_runtime(seconds) if seconds else ""

    @property
    def iso_duration(self):
        """ISO 8601 duration for schema.org `timeRequired`."""
        seconds = sum(m.video_duration_seconds for m in self.module_list)
        if not seconds:
            return ""
        hours, minutes = divmod(round(seconds / 60), 60)
        return f"PT{hours}H{minutes}M" if hours else f"PT{minutes}M"


class Module(TimeStampedModel):
    class Access(models.TextChoices):
        PAID = "paid", _("Paid — enrolled students only")
        FREE = "free", _("Free preview — any registered account")

    class Status(models.TextChoices):
        DRAFT = "draft", _("Draft")
        PUBLISHED = "published", _("Published")

    course = models.ForeignKey(
        Course, verbose_name=_("course"), on_delete=models.CASCADE, related_name="modules"
    )
    number = models.CharField(
        _("number"), max_length=4, help_text=_('Shown in the curriculum, e.g. "04".')
    )
    position = models.PositiveIntegerField(_("position"), default=0, db_index=True)
    title = models.CharField(_("title"), max_length=160)
    slug = models.SlugField(_("slug"), max_length=180)
    title_bn = models.CharField(
        _("title (Bangla)"),
        max_length=160,
        blank=True,
        help_text=_("Optional. Shown alongside the English title."),
    )
    summary = models.TextField(_("summary"), blank=True)
    notes_markdown = models.TextField(
        _("lesson notes"),
        blank=True,
        help_text=_("Markdown. Headings, bold, lists, links, images and audio."),
    )
    access = models.CharField(
        _("access"), max_length=8, choices=Access.choices, default=Access.PAID
    )
    status = models.CharField(
        _("status"), max_length=12, choices=Status.choices, default=Status.DRAFT
    )

    video_provider = models.CharField(
        _("video provider"),
        max_length=20,
        blank=True,
        choices=[
            ("cloudflare", _("Cloudflare Stream")),
            ("protected_file", _("Uploaded file")),
        ],
    )
    video_uid = models.CharField(
        _("video id or path"),
        max_length=255,
        blank=True,
        help_text=_("Cloudflare Stream UID, or a path under the media folder."),
    )
    video_duration_seconds = models.PositiveIntegerField(
        _("video duration (seconds)"), default=0
    )
    video_has_subtitles = models.BooleanField(_("English subtitles"), default=False)
    # Handouts linked from the media library and listed under the module's
    # Downloads tab, free to anyone who may open the module.
    downloads = models.ManyToManyField(
        "LibraryFile",
        verbose_name=_("downloads"),
        blank=True,
        related_name="download_modules",
    )

    class Meta:
        verbose_name = _("module")
        verbose_name_plural = _("modules")
        ordering = ("position", "number")
        constraints = [
            models.UniqueConstraint(
                fields=("course", "slug"), name="module_slug_unique_per_course"
            ),
            models.UniqueConstraint(
                fields=("course", "number"), name="module_number_unique_per_course"
            ),
        ]

    def __str__(self):
        return f"{self.number} · {self.title}"

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.title)[:180]
        super().save(*args, **kwargs)

    def get_absolute_url(self):
        return reverse(
            "courses:lesson",
            kwargs={"slug": self.course.slug, "module_slug": self.slug},
        )

    @property
    def is_free(self):
        return self.access == self.Access.FREE

    @property
    def number_plain(self):
        """The module number without its padding zero, for use in a sentence.

        "04" reads correctly in the curriculum column but not in
        "Start Module 04 free".
        """
        return self.number.lstrip("0") or self.number

    @property
    def video_duration_display(self):
        if not self.video_duration_seconds:
            return ""
        minutes, seconds = divmod(self.video_duration_seconds, 60)
        return f"{minutes}:{seconds:02d}"

    @cached_property
    def quiz_question_count(self):
        quiz = getattr(self, "quiz", None)
        return quiz.questions.count() if quiz else 0

    @cached_property
    def audio_assets(self):
        return [a for a in self.assets.all() if a.kind == MediaAsset.Kind.AUDIO]

    @cached_property
    def download_assets(self):
        return [a for a in self.assets.all() if a.kind == MediaAsset.Kind.DOWNLOAD]

    @cached_property
    def download_files(self):
        """Everything under the Downloads tab: older per-module uploads, then
        the files picked from the media library. Prefetch `assets` and
        `downloads` first."""
        return self.download_assets + list(self.downloads.all())

    @cached_property
    def notation_assets(self):
        return [a for a in self.assets.all() if a.kind == MediaAsset.Kind.NOTATION]

    @cached_property
    def linkable_text(self):
        """The notes plus every word of the quiz: all the text that may link
        to media library files. Prefetch `quiz__questions__choices` first."""
        parts = [self.notes_markdown]
        quiz = getattr(self, "quiz", None)
        if quiz:
            parts.append(quiz.title)
            for question in quiz.questions.all():
                parts += [question.text, question.explanation]
                parts += [choice.text for choice in question.choices.all()]
        return "\n".join(parts)

    @property
    def meta_line(self):
        bits = []
        if self.video_duration_display:
            bits.append(f"Video {self.video_duration_display}")
        if self.notes_markdown:
            bits.append("Reading")
        if self.audio_assets:
            bits.append("Audio")
        if self.quiz_question_count:
            bits.append(f"Quiz, {self.quiz_question_count} questions")
        return " · ".join(bits)


class Lesson(TimeStampedModel):
    """A named step inside a module, listed under the curriculum entry."""

    module = models.ForeignKey(
        Module, verbose_name=_("module"), on_delete=models.CASCADE, related_name="lessons"
    )
    title = models.CharField(_("title"), max_length=160)
    position = models.PositiveIntegerField(_("position"), default=0)

    class Meta:
        verbose_name = _("lesson")
        verbose_name_plural = _("lessons")
        ordering = ("position", "id")

    def __str__(self):
        return self.title


def asset_upload_to(instance, filename):
    return f"courses/{instance.module.course.slug}/{instance.module.slug}/{filename}"


class MediaAsset(TimeStampedModel):
    """Audio, notation graphics and downloadable resources for a module.

    Files are written under `MEDIA_ROOT` and streamed by
    `courses.views.protected_asset`, which checks access first. Notation
    graphics are the exception: they are part of the readable notes, so
    they follow the same access rule as the module itself.
    """

    class Kind(models.TextChoices):
        AUDIO = "audio", _("Audio (MP3)")
        NOTATION = "notation", _("Notation or diagram (SVG)")
        DOWNLOAD = "download", _("Download (PDF)")

    module = models.ForeignKey(
        Module, verbose_name=_("module"), on_delete=models.CASCADE, related_name="assets"
    )
    kind = models.CharField(_("kind"), max_length=10, choices=Kind.choices)
    title = models.CharField(_("title"), max_length=200)
    file = models.FileField(
        _("file"),
        upload_to=asset_upload_to,
        max_length=255,
    )
    alt_text = models.CharField(
        _("alt text"),
        max_length=255,
        blank=True,
        help_text=_("Describes the image for screen readers. Required for notation."),
    )
    duration_seconds = models.PositiveIntegerField(_("duration (seconds)"), default=0)
    position = models.PositiveIntegerField(_("position"), default=0)

    class Meta:
        verbose_name = _("media asset")
        verbose_name_plural = _("media assets")
        ordering = ("kind", "position", "id")

    def __str__(self):
        return self.title

    def get_absolute_url(self):
        return reverse("courses:asset", kwargs={"pk": self.pk})

    @property
    def duration_display(self):
        if not self.duration_seconds:
            return ""
        minutes, seconds = divmod(self.duration_seconds, 60)
        return f"{minutes}:{seconds:02d}"

    @property
    def size_display(self):
        return file_size_display(self.file)

    @property
    def detail_line(self):
        bits = [b for b in (self.duration_display, self.size_display) if b]
        return " · ".join(bits)


def file_size_display(file):
    """A stored file's size as "1.2 MB", or "" when the file is missing."""
    try:
        size = file.size
    except (OSError, ValueError):
        return ""
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024
    return ""


# The path of `courses:library_file`, found inside a pasted URL or Markdown.
LIBRARY_LINK_PATH = re.compile(r"/library/(?P<key>[\w-]+)/(?P<name>[^\s/()\[\]]+)")


def library_upload_to(instance, filename):
    """Group stored files by folder, so the disk mirrors the library."""
    return f"library/{slugify(instance.folder) or 'unsorted'}/{filename}"


def new_library_key():
    """A random URL key; the default for `LibraryFile.key`."""
    return secrets.token_urlsafe(12)


class LibraryFile(TimeStampedModel):
    """A file in the shared media library, linked from lesson notes by URL.

    The administrator uploads audio, diagrams and handouts once, copies the
    link, and pastes it into any module's Markdown or picks it as one of a
    module's `downloads`. `courses.views.library_file` works out who may
    fetch it from which modules link to it or offer it, so the paywall
    still applies.
    """

    class Purpose(models.TextChoices):
        LESSON = "lesson", _("Lesson material")
        QUIZ = "quiz", _("Quiz material")
        DOWNLOAD = "download", _("Download material")

    AUDIO_EXTENSIONS = ("mp3", "m4a", "ogg", "wav")
    IMAGE_EXTENSIONS = ("svg", "png", "jpg", "jpeg", "webp", "gif")
    DOCUMENT_EXTENSIONS = (
        "pdf", "doc", "docx", "odt", "rtf", "txt",
        "ppt", "pptx", "odp", "xls", "xlsx", "ods", "csv",
    )
    # Sheet music and bass tab: MIDI, MusicXML, Guitar Pro and MuseScore.
    SCORE_EXTENSIONS = ("mid", "midi", "musicxml", "mxl", "gp", "gp5", "gpx", "mscz")
    ARCHIVE_EXTENSIONS = ("zip",)
    EXTENSIONS = (
        AUDIO_EXTENSIONS
        + IMAGE_EXTENSIONS
        + DOCUMENT_EXTENSIONS
        + SCORE_EXTENSIONS
        + ARCHIVE_EXTENSIONS
    )

    purpose = models.CharField(
        _("material"),
        max_length=10,
        choices=Purpose.choices,
        default=Purpose.LESSON,
        db_index=True,
        help_text=_("What the file is for. Download material is always offered as a download."),
    )
    folder = models.CharField(
        _("folder"),
        max_length=80,
        default="General",
        db_index=True,
        help_text=_("Group related files, e.g. “Module 3” or “Scales”."),
    )
    title = models.CharField(_("title"), max_length=200)
    file = models.FileField(
        _("file"),
        upload_to=library_upload_to,
        max_length=255,
        validators=[FileExtensionValidator(EXTENSIONS)],
    )
    # Random, so the URLs pasted into notes cannot be guessed by counting.
    key = models.CharField(
        _("key"), max_length=24, unique=True, default=new_library_key, editable=False
    )

    class Meta:
        verbose_name = _("library file")
        verbose_name_plural = _("library files")
        ordering = ("folder", "title", "id")

    def __str__(self):
        return self.title

    @classmethod
    def from_link(cls, text):
        """The library file a pasted link points at, or None.

        Takes the "Link only" URL (with or without the site address) or the
        Markdown the library offers to copy, so either paste works.
        """
        match = LIBRARY_LINK_PATH.search(text)
        if not match:
            return None
        item = cls.objects.filter(key=match["key"]).first()
        return item if item and item.filename == match["name"] else None

    @property
    def filename(self):
        """The stored file's name, without its folder."""
        return Path(self.file.name).name

    @property
    def extension(self):
        """Lower-case extension without the dot, e.g. "mp3"."""
        return Path(self.file.name).suffix.lstrip(".").lower()

    @property
    def is_audio(self):
        """True for files that play in an audio player."""
        return self.extension in self.AUDIO_EXTENSIONS

    @property
    def is_image(self):
        """True for files that show as a figure."""
        return self.extension in self.IMAGE_EXTENSIONS

    @property
    def is_download(self):
        """True when students should save the file rather than view it."""
        return self.purpose == self.Purpose.DOWNLOAD or not (self.is_audio or self.is_image)

    @property
    def detail_line(self):
        """File type and size for the Downloads tab, e.g. "PDF · 1.2 MB"."""
        bits = [b for b in (self.extension.upper(), file_size_display(self.file)) if b]
        return " · ".join(bits)

    @property
    def link_prefix(self):
        """The part of the URL that identifies this file inside notes."""
        return self.get_absolute_url().rsplit("/", 1)[0] + "/"

    def get_absolute_url(self):
        """The link the administrator pastes into notes."""
        return reverse("courses:library_file", kwargs={"key": self.key, "name": self.filename})

    @property
    def markdown(self):
        """What the administrator pastes into the notes.

        Audio uses image syntax too: `render_notes` turns an "image" that
        points at an audio file into a player, so there is one thing to learn.
        Download material is a plain link, even for audio, so a backing track
        meant to be saved is not embedded as a player.
        """
        url = self.get_absolute_url()
        if self.is_download:
            return f"[{self.title}]({url})"
        return f"![{self.title}]({url})"


class Quiz(TimeStampedModel):
    module = models.OneToOneField(
        Module, verbose_name=_("module"), on_delete=models.CASCADE, related_name="quiz"
    )
    title = models.CharField(_("title"), max_length=160, blank=True)
    require_perfect_score = models.BooleanField(
        _("require 100% to unlock the next module"), default=True
    )
    allow_unlimited_retries = models.BooleanField(
        _("allow unlimited retries"), default=True
    )

    class Meta:
        verbose_name = _("quiz")
        verbose_name_plural = _("quizzes")

    def __str__(self):
        return self.title or f"{self.module.title} quiz"

    @property
    def display_title(self):
        return self.title or f"Module {self.module.number.lstrip('0') or '0'} quiz"

    @cached_property
    def title_html(self):
        """The title with any Markdown (and library media) rendered."""
        return render_inline(self.display_title)

    @property
    def plain_title(self):
        """The title as text, for the browser tab where markup cannot show."""
        return strip_tags(self.title_html).strip() or self.display_title


class Question(TimeStampedModel):
    quiz = models.ForeignKey(
        Quiz, verbose_name=_("quiz"), on_delete=models.CASCADE, related_name="questions"
    )
    text = models.TextField(_("question"))
    position = models.PositiveIntegerField(_("position"), default=0)
    explanation = models.TextField(
        _("explanation"),
        blank=True,
        help_text=_("Shown once the correct answer is selected."),
    )
    notation = models.ForeignKey(
        MediaAsset,
        verbose_name=_("notation image"),
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="notation_questions",
        limit_choices_to={"kind": MediaAsset.Kind.NOTATION},
    )
    audio = models.ForeignKey(
        MediaAsset,
        verbose_name=_("audio clip"),
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="audio_questions",
        limit_choices_to={"kind": MediaAsset.Kind.AUDIO},
    )

    class Meta:
        verbose_name = _("question")
        verbose_name_plural = _("questions")
        ordering = ("position", "id")

    def __str__(self):
        return self.text[:70]

    @cached_property
    def correct_choice(self):
        return next((c for c in self.choices.all() if c.is_correct), None)

    @cached_property
    def text_html(self):
        """The question as Markdown, so library audio and diagrams show inline."""
        return render_notes(self.text)

    @cached_property
    def explanation_html(self):
        """The explanation as Markdown, shown once the right answer is picked."""
        return render_notes(self.explanation)


class Choice(models.Model):
    question = models.ForeignKey(
        Question,
        verbose_name=_("question"),
        on_delete=models.CASCADE,
        related_name="choices",
    )
    text = models.CharField(_("answer"), max_length=255)
    is_correct = models.BooleanField(_("correct answer"), default=False)
    position = models.PositiveIntegerField(_("position"), default=0)

    class Meta:
        verbose_name = _("answer option")
        verbose_name_plural = _("answer options")
        ordering = ("position", "id")

    def __str__(self):
        return self.text

    @property
    def letter(self):
        return "ABCDEFGH"[self.position] if self.position < 8 else "?"

    @cached_property
    def _rendered(self):
        return split_audio(render_inline(self.text))

    @property
    def text_html(self):
        """The option's text and images, which fit inside the answer button."""
        return self._rendered[0]

    @property
    def audio_html(self):
        """The option's audio players, shown beside the button, not in it."""
        return self._rendered[1]


class Enrollment(TimeStampedModel):
    """A student's right to study a course.

    Created automatically when an order is paid, or by an administrator
    granting access. Registering gives no enrolment: the free module is
    reachable to any signed-in account without one.
    """

    student = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=_("student"),
        on_delete=models.CASCADE,
        related_name="enrollments",
    )
    course = models.ForeignKey(
        Course,
        verbose_name=_("course"),
        on_delete=models.CASCADE,
        related_name="enrollments",
    )
    is_active = models.BooleanField(_("active"), default=True)
    granted_manually = models.BooleanField(_("granted by an administrator"), default=False)

    class Meta:
        verbose_name = _("enrollment")
        verbose_name_plural = _("enrollments")
        ordering = ("-created_at",)
        constraints = [
            models.UniqueConstraint(
                fields=("student", "course"), name="one_enrollment_per_student_course"
            )
        ]

    def __str__(self):
        return f"{self.student} → {self.course}"

    @classmethod
    def grant(cls, student, course):
        """Open a course without a payment — refunds, comps, support fixes."""
        cls.objects.update_or_create(
            student=student,
            course=course,
            defaults={"is_active": True, "granted_manually": True},
        )

    @classmethod
    def revoke(cls, student, courses):
        """Withdraw the given courses. Orders stay as they are."""
        cls.objects.filter(student=student, course__in=courses).update(is_active=False)


class ModuleProgress(TimeStampedModel):
    """How far one student has got with one module: video, quiz, completion."""

    MAX_WATCHED_PER_REPORT = 60

    student = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=_("student"),
        on_delete=models.CASCADE,
        related_name="module_progress",
    )
    module = models.ForeignKey(
        Module, verbose_name=_("module"), on_delete=models.CASCADE, related_name="progress"
    )
    video_position_seconds = models.PositiveIntegerField(
        _("video position (seconds)"), default=0, validators=[MinValueValidator(0)]
    )
    # Time spent playing the video, rewatches included. Unlike the position
    # it only grows, so staff can see how long a student has studied.
    watched_seconds = models.PositiveIntegerField(_("watched (seconds)"), default=0)
    quiz_passed_at = models.DateTimeField(_("quiz passed at"), null=True, blank=True)
    completed_at = models.DateTimeField(_("completed at"), null=True, blank=True)
    last_seen_at = models.DateTimeField(_("last seen at"), default=timezone.now)

    class Meta:
        verbose_name = _("module progress")
        verbose_name_plural = _("module progress")
        ordering = ("module__position",)
        constraints = [
            models.UniqueConstraint(
                fields=("student", "module"), name="one_progress_per_student_module"
            )
        ]

    def __str__(self):
        return f"{self.student} · {self.module}"

    @property
    def is_complete(self):
        return self.completed_at is not None

    @classmethod
    def record_playback(cls, student, module, position, watched):
        """Save the resume point and add the seconds played since the last report.

        `watched` comes from the browser, so it is capped: the player
        reports at least every 15 seconds while playing, and a larger
        claim would only inflate the figure staff read.
        """
        watched = min(max(0, watched), cls.MAX_WATCHED_PER_REPORT)
        with transaction.atomic():
            progress, _ = cls.objects.get_or_create(student=student, module=module)
            now = timezone.now()
            # F() so two overlapping reports (a pause and a beacon) both count.
            cls.objects.filter(pk=progress.pk).update(
                video_position_seconds=max(0, position),
                watched_seconds=F("watched_seconds") + watched,
                last_seen_at=now,
                updated_at=now,
            )

    def mark_complete(self):
        now = timezone.now()
        self.quiz_passed_at = self.quiz_passed_at or now
        self.completed_at = self.completed_at or now
        self.last_seen_at = now
        self.save(
            update_fields=[
                "quiz_passed_at",
                "completed_at",
                "last_seen_at",
                "updated_at",
            ]
        )


class QuizAttempt(TimeStampedModel):
    """One pass through a quiz.

    Students may retry a question until they pick the right answer, so an
    attempt records how many wrong picks happened on the way. `score` is the
    share of questions answered correctly on the first try.
    """

    student = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=_("student"),
        on_delete=models.CASCADE,
        related_name="quiz_attempts",
    )
    quiz = models.ForeignKey(
        Quiz, verbose_name=_("quiz"), on_delete=models.CASCADE, related_name="attempts"
    )
    answers = models.JSONField(_("answers"), default=dict, blank=True)
    wrong_picks = models.PositiveIntegerField(_("wrong picks"), default=0)
    score_percent = models.PositiveIntegerField(_("score (%)"), default=0)
    completed_at = models.DateTimeField(_("completed at"), null=True, blank=True)

    class Meta:
        verbose_name = _("quiz attempt")
        verbose_name_plural = _("quiz attempts")
        ordering = ("-created_at",)

    def __str__(self):
        return f"{self.student} · {self.quiz} · {self.score_percent}%"

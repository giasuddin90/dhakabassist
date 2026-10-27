"""Course content, enrolment, progress and quizzes.

Shape: Course -> Module -> (video, markdown notes, MediaAsset*, Quiz).
A module is reachable when it is the free preview, or when the student is
enrolled and has completed every earlier module: by passing its quiz, or, for
a module without one, by marking it complete.
"""

import html
import re
import secrets
from datetime import datetime, time, timedelta
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import (
    FileExtensionValidator,
    MinValueValidator,
    RegexValidator,
)
from django.db import models, transaction
from django.db.models import F
from django.templatetags.static import static
from django.urls import reverse
from django.utils import timezone
from django.utils.functional import cached_property
from django.utils.html import strip_tags
from django.utils.text import slugify
from django.utils.translation import gettext, ngettext
from django.utils.translation import gettext_lazy as _

from .i18n import (
    active_language,
    columns,
    in_some_language,
    missing_language,
    translated,
)
from .markup import render_inline, render_notes, split_audio
from .video import CLOUDFLARE_UID, trailer_embed_url


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
    if hours:
        return gettext("%(hours)s hr %(minutes)s min") % {"hours": hours, "minutes": minutes}
    return gettext("%(minutes)s min") % {"minutes": minutes}


# No SVG: author photos and course banners are served publicly, and an SVG
# can carry script.
PUBLIC_IMAGE_EXTENSIONS = ("jpg", "jpeg", "png", "webp")


def author_photo_upload_to(instance, filename):
    """Keep each author's photo in their own folder."""
    return f"authors/{instance.slug or slugify(instance.name)}/{filename}"


def course_banner_upload_to(instance, filename):
    """Keep each course's banner beside its modules' files."""
    return f"courses/{instance.slug or slugify(instance.title)}/banner/{filename}"


class TimeStampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True, editable=False)
    updated_at = models.DateTimeField(auto_now=True, editable=False)

    class Meta:
        abstract = True


class Author(TimeStampedModel):
    """The person who teaches a course. One author can teach many courses."""

    name_bn = models.CharField(_("name (Bangla)"), max_length=120, blank=True)
    name_en = models.CharField(_("name (English)"), max_length=120, blank=True)
    slug = models.SlugField(
        _("slug"),
        max_length=140,
        unique=True,
        blank=True,
        help_text=_("Left blank, it is made from the English name."),
    )
    photo = models.ImageField(
        _("photo"),
        upload_to=author_photo_upload_to,
        max_length=255,
        blank=True,
        validators=[FileExtensionValidator(PUBLIC_IMAGE_EXTENSIONS)],
        help_text=_("A square JPG, PNG or WEBP, at least 320 × 320 px, up to 5 MB."),
    )
    bio_bn = models.TextField(
        _("bio (Bangla)"),
        blank=True,
        help_text=_("Markdown. Shown under “About the author” on the course page."),
    )
    bio_en = models.TextField(
        _("bio (English)"),
        blank=True,
        help_text=_("Markdown. Shown under “About the author” on the course page."),
    )

    name = translated("name")
    bio = translated("bio")

    class Meta:
        verbose_name = _("author")
        verbose_name_plural = _("authors")
        ordering = ("name_bn", "name_en", "id")
        constraints = [in_some_language("author", "name")]

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = self._unique_slug()
        super().save(*args, **kwargs)

    def _unique_slug(self):
        """The name as a slug, numbered when another author already has it."""
        # slugify drops Bangla letters, so the English name makes the slug.
        base = slugify(self.name_en or self.name_bn)[:130] or "author"
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

    title_bn = models.CharField(_("title (Bangla)"), max_length=160, blank=True)
    title_en = models.CharField(_("title (English)"), max_length=160, blank=True)
    slug = models.SlugField(_("slug"), max_length=180, unique=True)
    subtitle_bn = models.CharField(_("subtitle (Bangla)"), max_length=200, blank=True)
    subtitle_en = models.CharField(_("subtitle (English)"), max_length=200, blank=True)
    summary_bn = models.TextField(
        _("summary (Bangla)"),
        blank=True,
        help_text=_("One or two sentences. Used on cards and in search results."),
    )
    summary_en = models.TextField(
        _("summary (English)"),
        blank=True,
        help_text=_("One or two sentences. Used on cards and in search results."),
    )
    description_bn = models.TextField(
        _("description (Bangla)"), blank=True, help_text=_("Markdown. Shown on the course page.")
    )
    description_en = models.TextField(
        _("description (English)"), blank=True, help_text=_("Markdown. Shown on the course page.")
    )
    level_bn = models.CharField(_("level (Bangla)"), max_length=60, blank=True)
    level_en = models.CharField(_("level (English)"), max_length=60, blank=True, default="Beginner")
    price = models.DecimalField(
        _("price (BDT)"), max_digits=10, decimal_places=2, default=3500
    )
    status = models.CharField(
        _("status"), max_length=12, choices=Status.choices, default=Status.DRAFT
    )
    banner = models.ImageField(
        _("banner"),
        upload_to=course_banner_upload_to,
        max_length=255,
        blank=True,
        validators=[FileExtensionValidator(PUBLIC_IMAGE_EXTENSIONS)],
        help_text=_("A 16:9 JPG, PNG or WEBP, at least 1280 × 720 px, up to 5 MB."),
    )
    trailer_url_bn = models.URLField(
        _("trailer video link (Bangla)"),
        max_length=300,
        blank=True,
        validators=[validate_trailer_url],
        help_text=_(
            "A YouTube or Cloudflare Stream link. The trailer is public, so for "
            "Cloudflare turn off “require signed URLs” on this video."
        ),
    )
    trailer_url_en = models.URLField(
        _("trailer video link (English)"),
        max_length=300,
        blank=True,
        validators=[validate_trailer_url],
        help_text=_(
            "A YouTube or Cloudflare Stream link. The trailer is public, so for "
            "Cloudflare turn off “require signed URLs” on this video."
        ),
    )
    trailer_label_bn = models.CharField(
        _("trailer label (Bangla)"), max_length=60, blank=True, default="ট্রেইলার দেখুন"
    )
    trailer_label_en = models.CharField(
        _("trailer label (English)"), max_length=60, blank=True, default="Watch the trailer"
    )
    trailer_duration_bn = models.CharField(
        _("trailer duration (Bangla)"), max_length=16, blank=True
    )
    trailer_duration_en = models.CharField(
        _("trailer duration (English)"), max_length=16, blank=True
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

    meta_title_bn = models.CharField(_("meta title (Bangla)"), max_length=70, blank=True)
    meta_title_en = models.CharField(_("meta title (English)"), max_length=70, blank=True)
    meta_description_bn = models.CharField(
        _("meta description (Bangla)"), max_length=170, blank=True
    )
    meta_description_en = models.CharField(
        _("meta description (English)"), max_length=170, blank=True
    )

    title = translated("title")
    subtitle = translated("subtitle")
    summary = translated("summary")
    description = translated("description")
    level = translated("level")
    trailer_label = translated("trailer_label")
    trailer_url = translated("trailer_url")
    trailer_duration = translated("trailer_duration", key="trailer_url")
    meta_title = translated("meta_title")
    meta_description = translated("meta_description")

    objects = models.Manager()
    published = PublishedCourseManager()

    # The home page and the header's Enroll button show the promoted course,
    # falling back to the first published one when none is promoted.
    HOME_ORDERING = ("-promote_on_home", "position", *columns("title"))

    class Meta:
        verbose_name = _("course")
        verbose_name_plural = _("courses")
        ordering = ("position", "title_bn", "title_en")
        constraints = [
            in_some_language("course", "title"),
            in_some_language("course", "summary"),
            in_some_language("course", "description"),
        ]

    def __str__(self):
        return self.title

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.title_en or self.title_bn)[:180]
        super().save(*args, **kwargs)
        if self.promote_on_home:
            Course.objects.exclude(pk=self.pk).filter(promote_on_home=True).update(
                promote_on_home=False
            )

    def get_absolute_url(self):
        return reverse("courses:detail", kwargs={"slug": self.slug})

    @property
    def linkable_text(self):
        """Both languages of the description: the course text that may link to
        media library files, which then become public."""
        return "\n".join(getattr(self, column) for column in columns("description"))

    @cached_property
    def trailer_embed_url(self):
        return trailer_embed_url(self.trailer_url)

    @property
    def banner_url(self):
        """The public URL of the banner, or "" when there is none."""
        if not self.banner:
            return ""
        # The version busts the browser cache when the banner is replaced.
        url = reverse("courses:banner", kwargs={"slug": self.slug})
        return f"{url}?v={int(self.updated_at.timestamp())}"

    @property
    def banner_src(self):
        """The banner, or the site's placeholder when none is uploaded."""
        return self.banner_url or static(settings.SITE["course_banner_placeholder"])

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
    def free_modules(self):
        """Every module marked as a free preview, in course order."""
        return [m for m in self.module_list if m.is_free]

    @property
    def free_module(self):
        """The first free module: where "Try it free" links send people."""
        return next(iter(self.free_modules), None)

    @property
    def free_numbers(self):
        """Every free module's number for a sentence: "1", "1 & 2", "1, 2 & 3"."""
        numbers = [m.number_plain for m in self.free_modules]
        if len(numbers) < 2:
            return "".join(numbers)
        return f"{', '.join(numbers[:-1])} & {numbers[-1]}"

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

    @cached_property
    def current_promotion(self):
        """The promotion running today, or None.

        Reads `running_promotions` when `course_queryset()` prefetched it. A
        promotion that would make the course free is skipped, so a later cut
        to the course price can never send the gateway a zero amount. Should
        two overlap, the lower price wins.
        """
        running = getattr(self, "running_promotions", None)
        if running is None:
            running = Promotion.objects.running().filter(course=self)
        valid = [p for p in running if p.apply(self.price) > 0]
        return min(valid, key=lambda p: p.apply(self.price), default=None)

    @property
    def current_price(self):
        """What the course costs today, after any running promotion."""
        promotion = self.current_promotion
        return promotion.apply(self.price) if promotion else self.price


class PromotionQuerySet(models.QuerySet):
    """Promotions by date."""

    def running(self, today=None):
        """Promotions whose dates include `today` (in Dhaka by default)."""
        today = today or timezone.localdate()
        return self.filter(starts_on__lte=today, ends_on__gte=today)


class Promotion(TimeStampedModel):
    """A time-limited discount on one course, e.g. BDT 1000 off for November."""

    class Kind(models.TextChoices):
        AMOUNT = "amount", _("BDT off")
        PERCENT = "percent", _("% off")

    course = models.ForeignKey(
        Course, verbose_name=_("course"), on_delete=models.CASCADE, related_name="promotions"
    )
    name = models.CharField(
        _("name"), max_length=80, help_text=_("For staff only, e.g. “November offer”.")
    )
    kind = models.CharField(_("discount"), max_length=10, choices=Kind.choices, default=Kind.AMOUNT)
    value = models.DecimalField(
        _("value"),
        max_digits=10,
        decimal_places=2,
        help_text=_("Taka off the price, or the percentage off."),
    )
    # Dates, not times: an offer runs whole days in Dhaka time, both ends included.
    starts_on = models.DateField(_("first day"))
    ends_on = models.DateField(_("last day"))
    offer_text_bn = models.CharField(
        _("offer text (Bangla)"),
        max_length=160,
        blank=True,
        help_text=_("Optional. Shown under the price on the course page."),
    )
    offer_text_en = models.CharField(
        _("offer text (English)"),
        max_length=160,
        blank=True,
        help_text=_("Optional. Shown under the price on the course page."),
    )

    offer_text = translated("offer_text")

    objects = PromotionQuerySet.as_manager()

    class Meta:
        verbose_name = _("promotion")
        verbose_name_plural = _("promotions")
        ordering = ("-starts_on",)
        indexes = [models.Index(fields=("course", "ends_on"))]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(value__gt=0), name="promotion_value_positive"
            ),
            models.CheckConstraint(
                condition=~models.Q(kind="percent") | models.Q(value__lte=100),
                name="promotion_percent_max_100",
            ),
            models.CheckConstraint(
                condition=models.Q(ends_on__gte=F("starts_on")), name="promotion_ends_after_start"
            ),
        ]

    def __str__(self):
        return f"{self.name} · {self.course}"

    def apply(self, price):
        """`price` after this discount, in whole taka: pages show no paisa,
        and the gateway must charge exactly what the page shows."""
        if self.kind == self.Kind.PERCENT:
            discounted = price * (100 - self.value) / 100
        else:
            discounted = price - self.value
        return discounted.quantize(Decimal(1), rounding=ROUND_HALF_UP)

    def is_running(self, today=None):
        """Whether `today` (in Dhaka by default) is one of the offer's days."""
        today = today or timezone.localdate()
        return self.starts_on <= today <= self.ends_on

    @property
    def ends_at(self):
        """The moment the offer stops: midnight after its last day, in Dhaka."""
        next_day = self.ends_on + timedelta(days=1)
        return timezone.make_aware(datetime.combine(next_day, time.min))

    @property
    def seconds_left(self):
        """Whole seconds until `ends_at`, for the countdown; 0 once it ended.

        Counted on the server so a visitor's wrong clock cannot skew it."""
        return max(0, int((self.ends_at - timezone.now()).total_seconds()))

    @property
    def countdown_text(self):
        """The time left as the countdown first shows it, e.g. "Ends in 3d 04h 12m 05s"."""
        days, rest = divmod(self.seconds_left, 86400)
        hours, rest = divmod(rest, 3600)
        minutes, seconds = divmod(rest, 60)
        return gettext("Ends in {d}d {h}h {m}m {s}s").format(
            d=days, h=f"{hours:02d}", m=f"{minutes:02d}", s=f"{seconds:02d}"
        )

    @property
    def sale_price(self):
        """The course's price under this promotion."""
        return self.apply(self.course.price)

    @property
    def discount_label(self):
        """The discount for staff screens: "৳1,000 off" or "20% off"."""
        if self.kind == self.Kind.PERCENT:
            return f"{self.value.normalize():f}% off"
        return f"{settings.SITE['currency_symbol']}{self.value:,.0f} off"


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
    # The number is also the module's place in the course: modules are listed,
    # and unlocked, in number order. Stored zero-padded so text order matches.
    number = models.CharField(
        _("number"),
        max_length=4,
        validators=[RegexValidator(r"^\d{1,2}$", _("Enter one or two digits, e.g. 4 or 04."))],
        help_text=_('Sets the module\'s place in the course, e.g. "04".'),
    )
    title_bn = models.CharField(_("title (Bangla)"), max_length=160, blank=True)
    title_en = models.CharField(_("title (English)"), max_length=160, blank=True)
    slug = models.SlugField(_("slug"), max_length=180)
    summary_bn = models.TextField(_("summary (Bangla)"), blank=True)
    summary_en = models.TextField(_("summary (English)"), blank=True)
    notes_markdown_bn = models.TextField(
        _("lesson notes (Bangla)"),
        blank=True,
        help_text=_("Markdown. Headings, bold, lists, links, images and audio."),
    )
    notes_markdown_en = models.TextField(
        _("lesson notes (English)"),
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
    # One video per language; a module with only one plays it in both.
    video_uid_bn = models.CharField(
        _("Bangla video id or path"),
        max_length=255,
        blank=True,
        help_text=_("Cloudflare Stream UID, or a path under the media folder."),
    )
    video_uid_en = models.CharField(
        _("English video id or path"),
        max_length=255,
        blank=True,
        help_text=_("Cloudflare Stream UID, or a path under the media folder."),
    )
    video_duration_seconds_bn = models.PositiveIntegerField(
        _("Bangla video duration (seconds)"), default=0
    )
    video_duration_seconds_en = models.PositiveIntegerField(
        _("English video duration (seconds)"), default=0
    )
    video_has_subtitles_bn = models.BooleanField(
        _("Bangla video has English subtitles"), default=False
    )
    video_has_subtitles_en = models.BooleanField(
        _("English video has English subtitles"), default=False
    )
    # Handouts linked from the media library and listed under the module's
    # Downloads tab, free to anyone who may open the module.
    downloads = models.ManyToManyField(
        "LibraryFile",
        verbose_name=_("downloads"),
        blank=True,
        related_name="download_modules",
    )

    title = translated("title")
    summary = translated("summary")
    notes_markdown = translated("notes_markdown")
    video_uid = translated("video_uid")
    video_duration_seconds = translated("video_duration_seconds", key="video_uid")
    video_has_subtitles = translated("video_has_subtitles", key="video_uid")

    class Meta:
        verbose_name = _("module")
        verbose_name_plural = _("modules")
        ordering = ("number",)
        constraints = [
            in_some_language("module", "title"),
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
            self.slug = slugify(self.title_en or self.title_bn)[:180]
        self.number = self.pad_number(self.number)
        super().save(*args, **kwargs)

    @staticmethod
    def pad_number(value):
        """Zero-pad a module number ("4" becomes "04") so text order is number order."""
        value = str(value).strip()
        return f"{int(value):02d}" if value.isdigit() else value

    @classmethod
    def renumber(cls, course, order):
        """Number the course's modules 01, 02, … in the order of the pks in `order`.

        Modules left out of `order` (added in another tab, say) follow the
        listed ones in their current order. Returns how many were renumbered.
        """
        with transaction.atomic():
            remaining = {str(m.pk): m for m in course.modules.select_for_update()}
            listed = [remaining.pop(str(pk)) for pk in order if str(pk) in remaining]
            changed = []
            for index, module in enumerate(listed + list(remaining.values()), start=1):
                number = cls.pad_number(index)
                if module.number != number:
                    module.number = number
                    changed.append(module)
            # Park the moved modules on placeholders first: the database checks
            # the unique number per row, so swapping 01 and 02 in one pass fails.
            final = [module.number for module in changed]
            for index, module in enumerate(changed):
                module.number = f"~{index}"
            cls.objects.bulk_update(changed, ["number"])
            for module, number in zip(changed, final):
                module.number = number
            cls.objects.bulk_update(changed, ["number"])
        return len(changed)

    def clean(self):
        super().clean()
        if self.video_provider != "cloudflare":
            return
        errors = {}
        for column in columns("video_uid"):
            # The UID is signed into the playback token as-is, so a typo or a
            # pasted URL would only show up as a broken player for students.
            uid = getattr(self, column).strip().lower()
            setattr(self, column, uid)
            if uid and not CLOUDFLARE_UID.match(uid):
                errors[column] = _(
                    "Enter the 32-character video ID from the Cloudflare "
                    "Stream dashboard, not a link."
                )
        if errors:
            raise ValidationError(errors)

    def get_absolute_url(self):
        return reverse(
            "courses:lesson",
            kwargs={"slug": self.course.slug, "module_slug": self.slug},
        )

    @property
    def is_free(self):
        return self.access == self.Access.FREE

    @property
    def needs_bangla(self):
        """True when the title, summary or notes exist only in English."""
        return missing_language(self, ("title", "summary", "notes_markdown"), "bn")

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

    @property
    def completes_by_quiz(self):
        """True when passing the quiz is the only way to complete the module.

        A module without quiz questions has nothing to pass, so the student
        marks it complete instead; otherwise every module after it would stay
        locked for good.
        """
        return bool(self.quiz_question_count)

    @cached_property
    def audio_assets(self):
        return [a for a in self.assets.all() if a.kind == MediaAsset.Kind.AUDIO]

    @cached_property
    def download_assets(self):
        return [a for a in self.assets.all() if a.kind == MediaAsset.Kind.DOWNLOAD]

    @cached_property
    def download_files(self):
        """Everything under the Downloads tab: older per-module uploads, then
        the files picked from the media library for this language. Prefetch
        `assets` and `downloads` first."""
        offered = (LibraryFile.Language.BOTH, active_language())
        return self.download_assets + [f for f in self.downloads.all() if f.language in offered]

    @cached_property
    def notation_assets(self):
        return [a for a in self.assets.all() if a.kind == MediaAsset.Kind.NOTATION]

    @cached_property
    def linkable_text(self):
        """The notes plus every word of the quiz, in both languages: all the
        text that may link to media library files. Prefetch
        `quiz__questions__choices` first."""
        parts = [getattr(self, column) for column in columns("notes_markdown")]
        quiz = getattr(self, "quiz", None)
        if quiz:
            parts += [getattr(quiz, column) for column in columns("title")]
            for question in quiz.questions.all():
                for name in ("text", "explanation"):
                    parts += [getattr(question, column) for column in columns(name)]
                for choice in question.choices.all():
                    parts += [getattr(choice, column) for column in columns("text")]
        return "\n".join(parts)

    @property
    def meta_line(self):
        bits = []
        if self.video_duration_display:
            bits.append(gettext("Video %(duration)s") % {"duration": self.video_duration_display})
        if self.notes_markdown:
            bits.append(gettext("Reading"))
        if self.audio_assets:
            bits.append(gettext("Audio"))
        if self.quiz_question_count:
            count = self.quiz_question_count
            bits.append(
                ngettext("Quiz, %(count)d question", "Quiz, %(count)d questions", count)
                % {"count": count}
            )
        return " · ".join(bits)


class Lesson(TimeStampedModel):
    """A named step inside a module, listed under the curriculum entry."""

    module = models.ForeignKey(
        Module, verbose_name=_("module"), on_delete=models.CASCADE, related_name="lessons"
    )
    title_bn = models.CharField(_("title (Bangla)"), max_length=160, blank=True)
    title_en = models.CharField(_("title (English)"), max_length=160, blank=True)
    position = models.PositiveIntegerField(_("position"), default=0)

    title = translated("title")

    class Meta:
        verbose_name = _("lesson")
        verbose_name_plural = _("lessons")
        ordering = ("position", "id")
        constraints = [in_some_language("lesson", "title")]

    def __str__(self):
        return self.title


def asset_upload_to(instance, filename):
    """Where assets went before they had a file per language. Kept for the
    migrations that name it."""
    return f"courses/{instance.module.course.slug}/{instance.module.slug}/{filename}"


def asset_upload_to_bn(instance, filename):
    return f"courses/{instance.module.course.slug}/{instance.module.slug}/bn/{filename}"


def asset_upload_to_en(instance, filename):
    return f"courses/{instance.module.course.slug}/{instance.module.slug}/en/{filename}"


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
    title_bn = models.CharField(_("title (Bangla)"), max_length=200, blank=True)
    title_en = models.CharField(_("title (English)"), max_length=200, blank=True)
    # One file per language; with only one, both languages get it.
    file_bn = models.FileField(
        _("Bangla file"), upload_to=asset_upload_to_bn, max_length=255, blank=True
    )
    file_en = models.FileField(
        _("English file"), upload_to=asset_upload_to_en, max_length=255, blank=True
    )
    alt_text_bn = models.CharField(
        _("alt text (Bangla)"),
        max_length=255,
        blank=True,
        help_text=_("Describes the image for screen readers. Required for notation."),
    )
    alt_text_en = models.CharField(
        _("alt text (English)"),
        max_length=255,
        blank=True,
        help_text=_("Describes the image for screen readers. Required for notation."),
    )
    duration_seconds_bn = models.PositiveIntegerField(
        _("Bangla file duration (seconds)"), default=0
    )
    duration_seconds_en = models.PositiveIntegerField(
        _("English file duration (seconds)"), default=0
    )
    position = models.PositiveIntegerField(_("position"), default=0)

    title = translated("title")
    alt_text = translated("alt_text")
    file = translated("file")
    duration_seconds = translated("duration_seconds", key="file")

    class Meta:
        verbose_name = _("media asset")
        verbose_name_plural = _("media assets")
        ordering = ("kind", "position", "id")
        constraints = [
            in_some_language("mediaasset", "title"),
            in_some_language("mediaasset", "file"),
        ]

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


# The path of `library:file`, found inside a pasted URL or Markdown.
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

    class Language(models.TextChoices):
        BOTH = "both", _("Both languages")
        BANGLA = "bn", _("Bangla only")
        ENGLISH = "en", _("English only")

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
    # Notes in each language link their own files, so a tag is enough: it
    # only decides which downloads a module lists on each language's page.
    language = models.CharField(
        _("language"),
        max_length=4,
        choices=Language.choices,
        default=Language.BOTH,
        help_text=_("Which language's pages offer it as a module download."),
    )
    folder = models.CharField(
        _("folder"),
        max_length=80,
        default="General",
        db_index=True,
        help_text=_("Group related files, e.g. “Module 3” or “Scales”."),
    )
    title_bn = models.CharField(_("title (Bangla)"), max_length=200, blank=True)
    title_en = models.CharField(_("title (English)"), max_length=200, blank=True)
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

    title = translated("title")

    class Meta:
        verbose_name = _("library file")
        verbose_name_plural = _("library files")
        ordering = ("folder", "title_bn", "title_en", "id")
        constraints = [in_some_language("libraryfile", "title")]

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
        return reverse("library:file", kwargs={"key": self.key, "name": self.filename})

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
    title_bn = models.CharField(_("title (Bangla)"), max_length=160, blank=True)
    title_en = models.CharField(_("title (English)"), max_length=160, blank=True)
    require_perfect_score = models.BooleanField(
        _("require 100% to unlock the next module"), default=True
    )
    allow_unlimited_retries = models.BooleanField(
        _("allow unlimited retries"), default=True
    )

    title = translated("title")

    class Meta:
        verbose_name = _("quiz")
        verbose_name_plural = _("quizzes")

    def __str__(self):
        return self.title or f"{self.module.title} quiz"

    @property
    def display_title(self):
        number = self.module.number.lstrip("0") or "0"
        return self.title or gettext("Module %(number)s quiz") % {"number": number}

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
    text_bn = models.TextField(_("question (Bangla)"), blank=True)
    text_en = models.TextField(_("question (English)"), blank=True)
    position = models.PositiveIntegerField(_("position"), default=0)
    explanation_bn = models.TextField(
        _("explanation (Bangla)"),
        blank=True,
        help_text=_("Shown once the correct answer is selected."),
    )
    explanation_en = models.TextField(
        _("explanation (English)"),
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

    text = translated("text")
    explanation = translated("explanation")

    class Meta:
        verbose_name = _("question")
        verbose_name_plural = _("questions")
        ordering = ("position", "id")
        constraints = [in_some_language("question", "text")]

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
    text_bn = models.CharField(_("answer (Bangla)"), max_length=255, blank=True)
    text_en = models.CharField(_("answer (English)"), max_length=255, blank=True)
    is_correct = models.BooleanField(_("correct answer"), default=False)
    position = models.PositiveIntegerField(_("position"), default=0)

    text = translated("text")

    class Meta:
        verbose_name = _("answer option")
        verbose_name_plural = _("answer options")
        ordering = ("position", "id")
        constraints = [in_some_language("choice", "text")]

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
        ordering = ("module__number",)
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

    def mark_complete(self, quiz_passed=True):
        """Finish the module. `quiz_passed` is False when the student marked a
        module without a quiz complete, so staff can tell the two apart."""
        now = timezone.now()
        if quiz_passed:
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

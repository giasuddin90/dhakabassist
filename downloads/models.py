"""Downloads sold or given away on their own: worksheets, PDFs, audio and ZIPs.

Separate from the course and its media library. A free download opens to any
signed-in account; a paid one to a student with a paid `orders.Order` for it.
Access is read from the orders, so a refund closes it again by itself.
"""

from pathlib import Path

from django.apps import apps
from django.core.validators import FileExtensionValidator, MinValueValidator
from django.db import models
from django.urls import reverse
from django.utils.text import slugify
from django.utils.translation import gettext_lazy as _

from courses.i18n import in_some_language, translated
from courses.models import TimeStampedModel, file_size_display

EXTENSIONS = ("pdf", "zip", "mp3", "m4a", "wav", "doc", "docx")


def download_upload_to_bn(instance, filename):
    """Keep each download's files in its own folder, one per language."""
    return f"downloads/{instance.slug}/bn/{filename}"


def download_upload_to_en(instance, filename):
    """Keep each download's files in its own folder, one per language."""
    return f"downloads/{instance.slug}/en/{filename}"


class DownloadQuerySet(models.QuerySet):
    """Lookups the list pages and access checks share."""

    def published(self):
        """The downloads shown on the public list."""
        return self.filter(status=Download.Status.PUBLISHED)

    def bought_by(self, user):
        """The downloads `user` has a paid order for."""
        # Looked up by name: `orders.Order` imports this module for its FK.
        Order = apps.get_model("orders", "Order")  # pylint: disable=invalid-name  # a class
        return self.filter(
            orders__student=user, orders__status=Order.Status.PAID
        ).distinct()


class Download(TimeStampedModel):
    """One file to download, free or for sale, with a file per language."""

    class Kind(models.TextChoices):
        WORKSHEET = "worksheet", _("Worksheet")
        PDF = "pdf", _("PDF")
        AUDIO = "audio", _("Audio")
        ZIP = "zip", _("ZIP bundle")

    class Status(models.TextChoices):
        DRAFT = "draft", _("Draft")
        PUBLISHED = "published", _("Published")

    title_bn = models.CharField(_("title (Bangla)"), max_length=200, blank=True)
    title_en = models.CharField(_("title (English)"), max_length=200, blank=True)
    slug = models.SlugField(
        _("slug"),
        max_length=200,
        unique=True,
        blank=True,
        help_text=_("Left blank, it is made from the English title."),
    )
    description_bn = models.TextField(
        _("description (Bangla)"),
        blank=True,
        help_text=_("One or two sentences on what is inside."),
    )
    description_en = models.TextField(
        _("description (English)"),
        blank=True,
        help_text=_("One or two sentences on what is inside."),
    )
    kind = models.CharField(
        _("type"), max_length=10, choices=Kind.choices, default=Kind.WORKSHEET, db_index=True
    )
    # One file per language; with only one, both languages get it.
    file_bn = models.FileField(
        _("Bangla file"),
        upload_to=download_upload_to_bn,
        max_length=255,
        blank=True,
        validators=[FileExtensionValidator(EXTENSIONS)],
    )
    file_en = models.FileField(
        _("English file"),
        upload_to=download_upload_to_en,
        max_length=255,
        blank=True,
        validators=[FileExtensionValidator(EXTENSIONS)],
    )
    price = models.DecimalField(
        _("price (BDT)"),
        max_digits=10,
        decimal_places=2,
        default=0,
        validators=[MinValueValidator(0)],
        help_text=_("0 makes it free for any signed-in account."),
    )
    status = models.CharField(
        _("status"), max_length=12, choices=Status.choices, default=Status.DRAFT
    )
    position = models.PositiveIntegerField(
        _("position"), default=0, help_text=_("Lower numbers are listed first.")
    )

    title = translated("title")
    description = translated("description")
    file = translated("file")

    objects = DownloadQuerySet.as_manager()

    class Meta:
        verbose_name = _("download")
        verbose_name_plural = _("downloads")
        ordering = ("position", "-created_at")
        indexes = [models.Index(fields=("status", "position"))]
        constraints = [
            in_some_language("download", "title"),
            in_some_language("download", "file"),
            models.CheckConstraint(
                condition=models.Q(price__gte=0), name="download_price_not_negative"
            ),
        ]

    def __str__(self):
        return self.title

    def save(self, *args, **kwargs):
        # Before saving, since the upload folder is named after the slug.
        if not self.slug:
            self.slug = self._unique_slug()
        super().save(*args, **kwargs)

    def _unique_slug(self):
        # slugify drops Bangla letters, so the English title makes the slug.
        base = slugify(self.title_en or self.title_bn)[:190] or "download"
        slug, number = base, 2
        while Download.objects.filter(slug=slug).exclude(pk=self.pk).exists():
            slug, number = f"{base}-{number}", number + 1
        return slug

    def get_file_url(self):
        """Where the file itself is fetched; `downloads.views.download_file` checks access."""
        return reverse("downloads:file", kwargs={"slug": self.slug})

    def get_buy_url(self):
        """The checkout page for a paid download."""
        return reverse("orders:download_checkout", kwargs={"slug": self.slug})

    @property
    def is_free(self):
        """True when any signed-in account may download it."""
        return self.price == 0

    @property
    def filename(self):
        """The stored file's name, without its folder."""
        return Path(self.file.name).name

    @property
    def extension(self):
        """Lower-case extension without the dot, e.g. "pdf"."""
        return Path(self.file.name).suffix.lstrip(".").lower()

    @property
    def detail_line(self):
        """File type and size, e.g. "PDF · 1.2 MB"."""
        bits = [b for b in (self.extension.upper(), file_size_display(self.file)) if b]
        return " · ".join(bits)

    def is_bought_by(self, user):
        """True when `user` has a paid order for this download."""
        return Download.objects.bought_by(user).filter(pk=self.pk).exists()

    def is_available_to(self, user):
        """True when `user` may fetch the file.

        A buyer keeps it even after staff unpublish it: they paid for it.
        """
        if not user.is_authenticated:
            return False
        if user.is_staff:
            return True
        if self.status == self.Status.PUBLISHED and self.is_free:
            return True
        return self.is_bought_by(user)

"""Editable site content that is not course material."""

from django.db import models
from django.urls import reverse
from django.utils.translation import gettext_lazy as _

from courses.models import TimeStampedModel


class FaqManager(models.Manager):
    def published(self):
        return self.filter(is_published=True)


class Faq(TimeStampedModel):
    question = models.CharField(_("question"), max_length=200)
    answer = models.TextField(_("answer"))
    position = models.PositiveIntegerField(_("position"), default=0)
    is_published = models.BooleanField(_("published"), default=True)

    objects = FaqManager()

    class Meta:
        verbose_name = _("FAQ")
        verbose_name_plural = _("FAQs")
        ordering = ("position", "id")

    def __str__(self):
        return self.question


class LegalPage(TimeStampedModel):
    """Terms, Privacy and Refund policy, kept editable without a deploy."""

    class Slug(models.TextChoices):
        TERMS = "terms", _("Terms & Conditions")
        PRIVACY = "privacy", _("Privacy Policy")
        REFUNDS = "refunds", _("Refund Policy")

    slug = models.SlugField(_("page"), max_length=40, unique=True, choices=Slug.choices)
    title = models.CharField(_("title"), max_length=120)
    body_markdown = models.TextField(_("body"), help_text=_("Markdown."))
    meta_description = models.CharField(
        _("meta description"), max_length=170, blank=True
    )
    is_published = models.BooleanField(_("published"), default=True)

    class Meta:
        verbose_name = _("legal page")
        verbose_name_plural = _("legal pages")
        ordering = ("slug",)

    def __str__(self):
        return self.title

    def get_absolute_url(self):
        return reverse("pages:legal", kwargs={"slug": self.slug})


class ContactMessage(TimeStampedModel):
    name = models.CharField(_("name"), max_length=120)
    email = models.EmailField(_("email"))
    message = models.TextField(_("message"))
    is_handled = models.BooleanField(_("handled"), default=False)

    class Meta:
        verbose_name = _("contact message")
        verbose_name_plural = _("contact messages")
        ordering = ("-created_at",)

    def __str__(self):
        return f"{self.name} <{self.email}>"

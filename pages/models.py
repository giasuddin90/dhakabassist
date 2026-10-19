"""Editable site content that is not course material."""

from django.db import models
from django.urls import reverse
from django.utils.translation import gettext_lazy as _

from courses.i18n import in_some_language, translated
from courses.models import TimeStampedModel


class FaqManager(models.Manager):
    def published(self):
        return self.filter(is_published=True)


class Faq(TimeStampedModel):
    question_bn = models.CharField(_("question (Bangla)"), max_length=200, blank=True)
    question_en = models.CharField(_("question (English)"), max_length=200, blank=True)
    answer_bn = models.TextField(_("answer (Bangla)"), blank=True)
    answer_en = models.TextField(_("answer (English)"), blank=True)
    position = models.PositiveIntegerField(_("position"), default=0)
    is_published = models.BooleanField(_("published"), default=True)

    question = translated("question")
    answer = translated("answer")

    objects = FaqManager()

    class Meta:
        verbose_name = _("FAQ")
        verbose_name_plural = _("FAQs")
        ordering = ("position", "id")
        constraints = [
            in_some_language("faq", "question"),
            in_some_language("faq", "answer"),
        ]

    def __str__(self):
        return self.question


class LegalPage(TimeStampedModel):
    """Terms, Privacy and Refund policy, kept editable without a deploy."""

    class Slug(models.TextChoices):
        TERMS = "terms", _("Terms & Conditions")
        PRIVACY = "privacy", _("Privacy Policy")
        REFUNDS = "refunds", _("Refund Policy")

    slug = models.SlugField(_("page"), max_length=40, unique=True, choices=Slug.choices)
    title_bn = models.CharField(_("title (Bangla)"), max_length=120, blank=True)
    title_en = models.CharField(_("title (English)"), max_length=120, blank=True)
    body_markdown_bn = models.TextField(_("body (Bangla)"), blank=True, help_text=_("Markdown."))
    body_markdown_en = models.TextField(_("body (English)"), blank=True, help_text=_("Markdown."))
    meta_description_bn = models.CharField(
        _("meta description (Bangla)"), max_length=170, blank=True
    )
    meta_description_en = models.CharField(
        _("meta description (English)"), max_length=170, blank=True
    )
    is_published = models.BooleanField(_("published"), default=True)

    title = translated("title")
    body_markdown = translated("body_markdown")
    meta_description = translated("meta_description")

    class Meta:
        verbose_name = _("legal page")
        verbose_name_plural = _("legal pages")
        ordering = ("slug",)
        constraints = [
            in_some_language("legalpage", "title"),
            in_some_language("legalpage", "body_markdown"),
        ]

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

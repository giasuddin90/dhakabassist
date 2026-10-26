from datetime import timedelta

from django.conf import settings
from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _


class UserManager(BaseUserManager):
    """Manager for a user model keyed on email instead of username."""

    use_in_migrations = True

    def _create_user(self, email, password, **extra):
        if not email:
            raise ValueError("An email address is required.")
        user = self.model(email=self.normalize_email(email), **extra)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_user(self, email, password=None, **extra):
        extra.setdefault("is_staff", False)
        extra.setdefault("is_superuser", False)
        return self._create_user(email, password, **extra)

    def create_superuser(self, email, password=None, **extra):
        extra.setdefault("is_staff", True)
        extra.setdefault("is_superuser", True)
        # Made from the command line by someone who owns the address, so
        # there is nobody to send a confirmation link to.
        extra.setdefault("email_confirmed_at", timezone.now())
        if not extra["is_staff"] or not extra["is_superuser"]:
            raise ValueError("A superuser must have is_staff and is_superuser set.")
        return self._create_user(email, password, **extra)


class Language(models.TextChoices):
    """The site's languages, as in `settings.LANGUAGES`. Bangla is primary."""

    BANGLA = "bn", "বাংলা"
    ENGLISH = "en", "English"


class User(AbstractUser):
    """A student or administrator. Email is the login identifier."""

    username = None
    email = models.EmailField(_("email address"), unique=True)
    full_name = models.CharField(_("full name"), max_length=150, blank=True)
    # Lets an administrator suspend access without deleting the account or
    # the purchase history behind it.
    access_enabled = models.BooleanField(
        _("course access enabled"),
        default=True,
        help_text=_("Turn off to suspend access to paid course material."),
    )
    marketing_opt_in = models.BooleanField(_("course news by email"), default=False)
    # Empty until the student follows the link in the confirmation email (or a
    # password-reset link, which proves the same thing). Sign-in is refused
    # while it is empty. Kept apart from `is_active`, which staff use to block
    # an account on purpose.
    email_confirmed_at = models.DateTimeField(_("email confirmed"), null=True, blank=True)
    # When the last confirmation and password-reset emails went out, so a
    # student (or someone typing their address) cannot fill the inbox. Empty
    # until the first one.
    confirmation_sent_at = models.DateTimeField(
        _("confirmation email sent"), null=True, blank=True
    )
    password_reset_sent_at = models.DateTimeField(
        _("password reset email sent"), null=True, blank=True
    )
    # The language the student signed up in. Emails no longer use it (they
    # are always English); kept until it is decided whether to drop it.
    language = models.CharField(
        _("email language"),
        max_length=5,
        choices=Language.choices,
        default=Language.BANGLA,
    )
    # Optional profile details the student fills in or updates from settings.
    profession = models.CharField(_("profession"), max_length=100, blank=True)
    education = models.CharField(_("education"), max_length=150, blank=True)
    location = models.CharField(_("location"), max_length=100, blank=True)

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []

    objects = UserManager()

    class Meta:
        verbose_name = _("user")
        verbose_name_plural = _("users")
        ordering = ("-date_joined",)

    def __str__(self):
        return self.full_name or self.email

    def get_full_name(self):
        return self.full_name or self.email

    def get_short_name(self):
        return (self.full_name or self.email).split(" ")[0].split("@")[0]

    @property
    def email_confirmed(self):
        return self.email_confirmed_at is not None

    def confirm_email(self):
        """Record that the student has shown they can read mail at `email`."""
        if self.email_confirmed_at is None:
            self.email_confirmed_at = timezone.now()
            self.save(update_fields=["email_confirmed_at"])

    def claim_confirmation_send(self):
        """Record a confirmation email about to go out, if one is allowed yet."""
        return self._claim_email_send("confirmation_sent_at")

    def claim_password_reset_send(self):
        """Record a password-reset email about to go out, if one is allowed yet."""
        return self._claim_email_send("password_reset_sent_at")

    def _claim_email_send(self, field):
        """Stamp `field` with the time now, unless it is too recent.

        False while the last send is younger than `EMAIL_RESEND_SECONDS`.
        One conditional UPDATE, so two requests at the same moment cannot
        both pass the check.
        """
        now = timezone.now()
        wait_until = now - timedelta(seconds=settings.EMAIL_RESEND_SECONDS)
        claimed = (
            User.objects.filter(pk=self.pk)
            .filter(
                models.Q(**{f"{field}__isnull": True})
                | models.Q(**{f"{field}__lte": wait_until})
            )
            .update(**{field: now})
        )
        if claimed:
            setattr(self, field, now)
        return bool(claimed)

    @property
    def initials(self):
        parts = [p for p in (self.full_name or "").split() if p]
        if parts:
            return (parts[0][0] + (parts[-1][0] if len(parts) > 1 else "")).upper()
        return self.email[:2].upper()

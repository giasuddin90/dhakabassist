from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.db import models
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
    # Emails are sent outside a request (receipts from a payment callback,
    # welcomes from the staff panel), so the language has to be stored.
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
    def initials(self):
        parts = [p for p in (self.full_name or "").split() if p]
        if parts:
            return (parts[0][0] + (parts[-1][0] if len(parts) > 1 else "")).upper()
        return self.email[:2].upper()

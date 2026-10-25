from django import forms
from django.conf import settings
from django.contrib.auth import get_user_model, password_validation
from django.contrib.auth.forms import (
    AuthenticationForm,
    PasswordResetForm,
    UserCreationForm,
)
from django.utils import translation
from django.utils.translation import gettext_lazy as _

User = get_user_model()

# Our wording for Django's password validators, by error code. Django ships no
# Bangla for these.
PASSWORD_RULE_MESSAGES = {
    "password_too_short": _("Use at least %(min_length)d characters."),
    "password_entirely_numeric": _("Use at least one letter or symbol, not only numbers."),
    "password_too_common": _("This password is too common. Choose one that is harder to guess."),
    "password_too_similar": _("This password is too close to your name or email."),
}

# The checklist under "Password" on the sign-up page, in order, by the same
# codes. site.js ticks the ones it can check in the browser as the student types.
PASSWORD_RULES = (
    ("password_too_short", _("At least %(min_length)d characters")),
    ("password_entirely_numeric", _("Not only numbers")),
    ("password_too_similar", _("Not too similar to your name or email")),
    ("password_too_common", _("Not a common password")),
)


class LoginForm(AuthenticationForm):
    """Email and password, with an opt-out of the long-lived session."""

    username = forms.EmailField(
        label=_("Email"),
        widget=forms.EmailInput(attrs={"autocomplete": "email", "autofocus": True}),
    )
    remember_me = forms.BooleanField(label=_("Keep me logged in"), required=False, initial=True)

    error_messages = {
        **AuthenticationForm.error_messages,
        "invalid_login": _("That email and password do not match an account."),
        "unconfirmed": _(
            "Confirm your email address before logging in. "
            "We sent you a link when you created your account."
        ),
    }

    # Set when the password was right but the email is unconfirmed, so the
    # page can offer to send the link again.
    unconfirmed = False

    def confirm_login_allowed(self, user):
        super().confirm_login_allowed(user)
        if not user.email_confirmed:
            self.unconfirmed = True
            raise forms.ValidationError(
                self.error_messages["unconfirmed"], code="unconfirmed"
            )


class RegisterForm(UserCreationForm):
    full_name = forms.CharField(
        label=_("Full name"),
        max_length=150,
        widget=forms.TextInput(attrs={"autocomplete": "name", "autofocus": True}),
    )
    email = forms.EmailField(
        label=_("Email"), widget=forms.EmailInput(attrs={"autocomplete": "email"})
    )

    class Meta:
        model = User
        fields = ("full_name", "email")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["password1"].widget.attrs["autocomplete"] = "new-password"
        self.fields["password2"].widget.attrs["autocomplete"] = "new-password"
        self.fields["password1"].label = _("Password")
        self.fields["password2"].label = _("Confirm password")
        # The page lists the rules itself (`password_rules`), in place of the
        # validators' help text. `minlength` lets the browser hint too.
        self.fields["password1"].help_text = ""
        # Django's "Enter the same password as before" has no Bangla, and the
        # label already says it; the page shows a live match line instead.
        self.fields["password2"].help_text = ""
        for name in ("password1", "password2"):
            self.fields[name].widget.attrs["minlength"] = settings.PASSWORD_MIN_LENGTH
        self.error_messages = {
            **self.error_messages,
            "password_mismatch": _("The two passwords do not match."),
        }

    @property
    def password_rules(self):
        """The checklist under "Password", each marked failed if the post broke it."""
        return [
            {
                "code": code,
                "text": text % {"min_length": settings.PASSWORD_MIN_LENGTH},
                "failed": self.is_bound and self.has_error("password1", code),
            }
            for code, text in PASSWORD_RULES
        ]

    def validate_password_for_user(self, user, password_field_name="password1"):
        # Django files rule errors under the confirm field; they are about the
        # password itself, so they go under it, leaving "do not match" below.
        password = self.cleaned_data.get(password_field_name)
        if not password:
            return
        try:
            password_validation.validate_password(password, user)
        except forms.ValidationError as error:
            self.add_error(
                password_field_name,
                [
                    forms.ValidationError(
                        PASSWORD_RULE_MESSAGES.get(item.code, item.message),
                        code=item.code,
                        params=item.params,
                    )
                    for item in error.error_list
                ],
            )

    def clean_email(self):
        email = self.cleaned_data["email"].strip()
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError(_("An account with this email already exists."))
        return email

    def save(self, commit=True):
        # Emails follow the language the student signed up in.
        self.instance.language = translation.get_language()
        return super().save(commit)


class ResendConfirmationForm(forms.Form):
    email = forms.EmailField(
        label=_("Email"),
        widget=forms.EmailInput(attrs={"autocomplete": "email", "autofocus": True}),
    )

    def get_user(self):
        """The unconfirmed account at this address, or None.

        The caller answers the same way either way, so the form never tells
        a visitor whether an address has an account.
        """
        return User.objects.filter(
            email__iexact=self.cleaned_data["email"].strip(),
            email_confirmed_at__isnull=True,
            is_active=True,
        ).first()


class StudentPasswordResetForm(PasswordResetForm):
    """Django's reset form, with the email in the student's own language.

    The link is built from `SITE_BASE_URL` rather than the request's Host
    header, so a forged header cannot point the link at another site.
    """

    def send_mail(self, subject_template_name, email_template_name, context, *args, **kwargs):
        context["base_url"] = settings.SITE["base_url"]
        with translation.override(context["user"].language):
            super().send_mail(
                subject_template_name, email_template_name, context, *args, **kwargs
            )


class AccountSettingsForm(forms.ModelForm):
    class Meta:
        model = User
        fields = (
            "full_name", "email", "profession", "education", "location", "language",
            "marketing_opt_in",
        )
        labels = {
            "profession": _("Profession (optional)"),
            "education": _("Education (optional)"),
            "location": _("Location (optional)"),
            "marketing_opt_in": _("Email me when new modules are published"),
            "language": _("Language for emails"),
        }
        help_texts = {
            "education": _(
                "Highest qualification or where you study, e.g. BSc, University of Dhaka."
            ),
            "location": _("City and country, e.g. Dhaka, Bangladesh."),
        }
        widgets = {
            "full_name": forms.TextInput(attrs={"autocomplete": "name"}),
            "email": forms.EmailInput(attrs={"autocomplete": "email"}),
            "profession": forms.TextInput(attrs={"autocomplete": "organization-title"}),
            "location": forms.TextInput(attrs={"autocomplete": "address-level2"}),
        }

    def clean_email(self):
        email = self.cleaned_data["email"].strip()
        if User.objects.filter(email__iexact=email).exclude(pk=self.instance.pk).exists():
            raise forms.ValidationError(_("Another account already uses this email."))
        return email

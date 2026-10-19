from django import forms
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import (
    AuthenticationForm,
    PasswordResetForm,
    UserCreationForm,
)
from django.utils import translation
from django.utils.translation import gettext_lazy as _

User = get_user_model()


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

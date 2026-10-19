from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm
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
    }


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

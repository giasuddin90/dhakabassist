from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm

User = get_user_model()


class LoginForm(AuthenticationForm):
    """Email and password, with an opt-out of the long-lived session."""

    username = forms.EmailField(
        label="Email",
        widget=forms.EmailInput(attrs={"autocomplete": "email", "autofocus": True}),
    )
    remember_me = forms.BooleanField(label="Keep me logged in", required=False, initial=True)

    error_messages = {
        **AuthenticationForm.error_messages,
        "invalid_login": "That email and password do not match an account.",
    }


class RegisterForm(UserCreationForm):
    full_name = forms.CharField(
        label="Full name",
        max_length=150,
        widget=forms.TextInput(attrs={"autocomplete": "name", "autofocus": True}),
    )
    email = forms.EmailField(
        label="Email", widget=forms.EmailInput(attrs={"autocomplete": "email"})
    )

    class Meta:
        model = User
        fields = ("full_name", "email")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["password1"].widget.attrs["autocomplete"] = "new-password"
        self.fields["password2"].widget.attrs["autocomplete"] = "new-password"
        self.fields["password1"].label = "Password"
        self.fields["password2"].label = "Confirm password"

    def clean_email(self):
        email = self.cleaned_data["email"].strip()
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError("An account with this email already exists.")
        return email


class AccountSettingsForm(forms.ModelForm):
    class Meta:
        model = User
        fields = (
            "full_name", "email", "profession", "education", "location", "marketing_opt_in",
        )
        labels = {
            "profession": "Profession (optional)",
            "education": "Education (optional)",
            "location": "Location (optional)",
            "marketing_opt_in": "Email me when new modules are published",
        }
        help_texts = {
            "education": "Highest qualification or where you study, e.g. BSc, University of Dhaka.",
            "location": "City and country, e.g. Dhaka, Bangladesh.",
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
            raise forms.ValidationError("Another account already uses this email.")
        return email

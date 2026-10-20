from django import forms
from django.utils.translation import gettext_lazy as _

from .captcha import MathCaptchaMixin
from .models import ContactMessage


class ContactForm(MathCaptchaMixin, forms.ModelForm):
    """Contact form with a simple sum to answer and a hidden honeypot."""

    # Bots fill every field; people never see this one.
    website = forms.CharField(required=False, widget=forms.HiddenInput)

    class Meta:
        model = ContactMessage
        fields = ("name", "email", "message")
        widgets = {
            "name": forms.TextInput(attrs={"autocomplete": "name", "maxlength": 120}),
            "email": forms.EmailInput(attrs={"autocomplete": "email"}),
            "message": forms.Textarea(attrs={"rows": 5}),
        }

    def clean(self):
        data = super().clean()
        if data.get("website"):
            raise forms.ValidationError(_("This message could not be sent."))
        return data

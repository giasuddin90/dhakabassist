"""A small "What is 3 + 4?" check for public forms.

Stateless, so anonymous visitors and crawlers never get a session row. The
form carries a signed, timestamped nonce; the two numbers are derived from it
with the secret key, so the page never contains the answer in any form a bot
could decode.
"""

import secrets

from django import forms
from django.core import signing
from django.utils.crypto import salted_hmac
from django.utils.translation import gettext
from django.utils.translation import gettext_lazy as _

TOKEN_SALT = "pages.captcha.token"
OPERANDS_SALT = "pages.captcha.operands"
# Long enough to write a message, short enough that a solved question is not
# worth keeping for replay.
MAX_AGE = 60 * 60

WRONG_ANSWER = _("That answer is not right. Try the new question.")
EXPIRED = _("This question has expired. Answer the new one.")


def operands(nonce):
    """The two numbers (1–9) a nonce stands for."""
    digest = salted_hmac(OPERANDS_SALT, nonce).digest()
    return digest[0] % 9 + 1, digest[1] % 9 + 1


class FixedHiddenInput(forms.HiddenInput):
    """A hidden input that renders its own value, never the submitted one.

    After a failed submission the page must show the new question's token,
    not the one that was just used.
    """

    def __init__(self, value, attrs=None):
        super().__init__(attrs)
        self.fixed_value = value

    def format_value(self, value):
        return self.fixed_value


class BlankTextInput(forms.TextInput):
    """A text input that never echoes the old answer: the question changes.

    Text with a numeric keyboard rather than `type="number"`, whose spinner
    arrows crowd a box this small.
    """

    def format_value(self, value):
        return None


# A form mixin: its public surface is the form it is mixed into.
class MathCaptchaMixin:  # pylint: disable=too-few-public-methods
    """Add a simple sum to a form.

    Render it with `{% include "includes/captcha_field.html" %}`.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        nonce = secrets.token_urlsafe(8)
        self.captcha_operands = operands(nonce)
        first, second = self.captcha_operands
        # Shown on the page; the label reads the same sum out as a question.
        self.captcha_sum = f"{first} + {second}"
        token = signing.TimestampSigner(salt=TOKEN_SALT).sign(nonce)
        # The token goes first so `clean_captcha` can read it.
        self.fields["captcha_token"] = forms.CharField(
            required=False, initial=token, widget=FixedHiddenInput(token)
        )
        self.fields["captcha"] = forms.IntegerField(
            label=gettext("What is %(first)s + %(second)s?") % {"first": first, "second": second},
            help_text=_("Add the two numbers. This keeps spam robots out."),
            widget=BlankTextInput(
                attrs={
                    "class": "captcha__input",
                    "inputmode": "numeric",
                    "pattern": "[0-9]*",
                    "maxlength": 2,
                    "autocomplete": "off",
                }
            ),
        )
        describe = self["captcha"].auto_id
        self.fields["captcha"].widget.attrs["aria-describedby"] = (
            f"{describe}_help {describe}_error"
        )

    def full_clean(self):
        """Mark a wrong answer for screen readers as well as visually."""
        super().full_clean()
        if "captcha" in self.errors:
            self.fields["captcha"].widget.attrs["aria-invalid"] = "true"

    def clean_captcha(self):
        """Check the answer against the question the submitted token stands for."""
        answer = self.cleaned_data["captcha"]
        try:
            nonce = signing.TimestampSigner(salt=TOKEN_SALT).unsign(
                self.cleaned_data.get("captcha_token", ""), max_age=MAX_AGE
            )
        except signing.BadSignature as error:  # SignatureExpired is a subclass
            raise forms.ValidationError(EXPIRED, code="expired") from error
        if answer != sum(operands(nonce)):
            raise forms.ValidationError(WRONG_ANSWER, code="wrong")
        return answer

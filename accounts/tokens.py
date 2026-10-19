"""Signed, expiring tokens for links sent by email."""

from django.contrib.auth.tokens import PasswordResetTokenGenerator


class EmailConfirmationTokenGenerator(PasswordResetTokenGenerator):
    """Tokens for the "confirm your email" link.

    Its own salt keeps these from working as password-reset links and the
    other way round. The hash covers the confirmation time and the address,
    so a link stops working once it has been used or the email has changed.
    It expires after `PASSWORD_RESET_TIMEOUT`, like a reset link.
    """

    key_salt = "accounts.tokens.EmailConfirmationTokenGenerator"

    def _make_hash_value(self, user, timestamp):
        return f"{user.pk}{user.email}{user.email_confirmed_at}{timestamp}"


email_confirmation_token = EmailConfirmationTokenGenerator()

"""An email backend that sends through Resend's HTTP API.

Uses the standard library only. HTTPS on 443 also works on hosts that block
outbound SMTP ports, which is why this is preferred over smtp.resend.com.
API reference: https://resend.com/docs/api-reference/emails/send-email
"""

import json
import logging
import urllib.error
import urllib.request

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.core.mail.backends.base import BaseEmailBackend

logger = logging.getLogger(__name__)

API_URL = "https://api.resend.com/emails"
# Resend refuses requests without a User-Agent with a 403.
USER_AGENT = "DhakaBassist/1.0 (+django)"


class ResendError(OSError):
    """Resend refused an email. The message holds its status and reply.

    An `OSError`, like `smtplib.SMTPException`, so code that copes with a
    failed send does not need to know which backend is configured.
    """


class ResendEmailBackend(BaseEmailBackend):
    def __init__(self, api_key=None, timeout=None, fail_silently=False, **kwargs):
        super().__init__(fail_silently=fail_silently, **kwargs)
        self.api_key = api_key or settings.RESEND_API_KEY
        self.timeout = timeout or settings.EMAIL_TIMEOUT
        if not self.api_key:
            raise ImproperlyConfigured("RESEND_API_KEY is not set.")

    def send_messages(self, email_messages):
        sent = 0
        for message in email_messages:
            try:
                self._send(message)
            except OSError:
                if not self.fail_silently:
                    raise
                logger.exception("Resend did not accept the email to %s", message.to)
            else:
                sent += 1
        return sent

    def _send(self, message):
        request = urllib.request.Request(
            API_URL,
            data=json.dumps(self._payload(message)).encode(),
            method="POST",
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                "User-Agent": USER_AGENT,
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                logger.info("Resend accepted email %s", json.load(response).get("id"))
        except urllib.error.HTTPError as error:
            # The body says why, e.g. an unverified `from` domain.
            detail = error.read().decode(errors="replace")[:500]
            raise ResendError(f"{error.code}: {detail}") from error

    @staticmethod
    def _payload(message):
        if message.attachments:
            raise ResendError("Attachments are not supported by ResendEmailBackend.")
        payload = {
            "from": message.from_email,
            "to": message.to,
            "subject": message.subject,
        }
        for field, value in (("cc", message.cc), ("bcc", message.bcc),
                             ("reply_to", message.reply_to)):
            if value:
                payload[field] = value
        if message.content_subtype == "html":
            payload["html"] = message.body
        else:
            payload["text"] = message.body
        for content, mimetype in getattr(message, "alternatives", []):
            if mimetype == "text/html":
                payload["html"] = content
        if message.extra_headers:
            payload["headers"] = message.extra_headers
        return payload

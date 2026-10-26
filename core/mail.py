"""Sending email: one helper, a threaded backend and Resend's HTTP API.

`send_email` is how the apps send mail; every email is in English.

`ThreadedEmailBackend` is `EMAIL_BACKEND`, so every `send()` in the project
(Django's password reset too) returns at once and the real backend,
`EMAIL_DELIVERY_BACKEND`, does the network call in a background thread.

`ResendEmailBackend` uses the standard library only. HTTPS on 443 also works
on hosts that block outbound SMTP ports, which is why this is preferred over
smtp.resend.com.
API reference: https://resend.com/docs/api-reference/emails/send-email
"""

import json
import logging
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.core.mail import EmailMessage, get_connection
from django.core.mail.backends.base import BaseEmailBackend
from django.db import transaction
from django.template.loader import render_to_string
from django.utils import translation

logger = logging.getLogger(__name__)

def send_email(subject, template_name, context, to, fail_silently=False, **kwargs):
    """Render `template_name` and send it as a plain-text email, in English.

    English is switched on while rendering because the body's links
    (`{% url %}`), course titles, payment methods and dates otherwise follow
    whichever page or callback happened to trigger the email. `kwargs` go to
    `EmailMessage`, e.g. `reply_to`.
    """
    with translation.override("en"):
        body = render_to_string(template_name, context)
    message = EmailMessage(subject=subject, body=body, to=to, **kwargs)
    return message.send(fail_silently=fail_silently)


# One small pool per process rather than a thread per email, so a burst of
# signups cannot start hundreds of threads. Python joins these threads at
# exit, so a graceful gunicorn restart still delivers what is queued.
EXECUTOR = ThreadPoolExecutor(max_workers=2, thread_name_prefix="mail")


class ThreadedEmailBackend(BaseEmailBackend):
    """Hands messages to a background thread so no request waits on mail.

    Messages arrive fully built: templates are rendered and subjects
    translated in the request thread, which is the only one that knows the
    student's language. The thread only does network I/O and must not touch
    the database.
    """

    def send_messages(self, email_messages):
        messages = list(email_messages)
        if messages:
            # After commit, so a rolled-back order never sends a receipt.
            # Outside a transaction this runs straight away.
            transaction.on_commit(lambda: EXECUTOR.submit(deliver, messages))
        return len(messages)


def deliver(messages):
    """Send through the real backend. Runs in a pool thread."""
    try:
        get_connection(settings.EMAIL_DELIVERY_BACKEND).send_messages(messages)
    # Any error at all: a pool thread has no caller to raise to, so whatever
    # is not logged here is lost.
    except Exception:  # pylint: disable=broad-exception-caught
        logger.exception("Could not send the email to %s", [m.to for m in messages])

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

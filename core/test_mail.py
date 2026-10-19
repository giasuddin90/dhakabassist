"""The Resend backend, with the HTTP call replaced by a fake."""

import io
import json
import urllib.error
from unittest import mock

from django.core.mail import EmailMessage, EmailMultiAlternatives
from django.test import SimpleTestCase, override_settings

from core.mail import ResendEmailBackend, ResendError


def accepted(*_args, **_kwargs):
    return io.BytesIO(b'{"id": "49a3999c"}')


@override_settings(RESEND_API_KEY="re_test", EMAIL_TIMEOUT=5)
class ResendBackendTests(SimpleTestCase):
    def send(self, message, urlopen=accepted, **backend_options):
        with mock.patch("core.mail.urllib.request.urlopen", side_effect=urlopen) as fake:
            sent = ResendEmailBackend(**backend_options).send_messages([message])
        return sent, fake

    def test_a_plain_email_is_posted_as_text(self):
        message = EmailMessage(
            "Hello", "Body", "DhakaBassist <hello@example.com>", ["a@example.com"],
            reply_to=["help@example.com"],
        )
        sent, fake = self.send(message)
        self.assertEqual(sent, 1)
        request = fake.call_args.args[0]
        self.assertEqual(request.full_url, "https://api.resend.com/emails")
        self.assertEqual(request.get_header("Authorization"), "Bearer re_test")
        self.assertTrue(request.get_header("User-agent"))
        self.assertEqual(fake.call_args.kwargs["timeout"], 5)
        self.assertEqual(
            json.loads(request.data),
            {
                "from": "DhakaBassist <hello@example.com>",
                "to": ["a@example.com"],
                "subject": "Hello",
                "text": "Body",
                "reply_to": ["help@example.com"],
            },
        )

    def test_an_html_alternative_is_sent_alongside_the_text(self):
        message = EmailMultiAlternatives("Hi", "Text", "x@example.com", ["a@example.com"])
        message.attach_alternative("<p>Text</p>", "text/html")
        _, fake = self.send(message)
        payload = json.loads(fake.call_args.args[0].data)
        self.assertEqual((payload["text"], payload["html"]), ("Text", "<p>Text</p>"))

    def test_a_refusal_raises_with_resend_s_reason(self):
        def refused(*_args, **_kwargs):
            raise urllib.error.HTTPError(
                "https://api.resend.com/emails", 403, "Forbidden", {},
                io.BytesIO(b'{"message": "The domain is not verified."}'),
            )

        message = EmailMessage("Hi", "Body", "x@example.com", ["a@example.com"])
        with self.assertRaisesMessage(ResendError, "not verified"):
            self.send(message, urlopen=refused)
        with self.assertLogs("core.mail", "ERROR"):
            sent, _ = self.send(message, urlopen=refused, fail_silently=True)
        self.assertEqual(sent, 0)

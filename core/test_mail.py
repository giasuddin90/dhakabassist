"""The mail backends: Resend with a fake HTTP call, and the threaded front."""

import io
import json
import threading
import urllib.error
from unittest import mock

from django.core import mail
from django.core.mail import EmailMessage, EmailMultiAlternatives
from django.test import SimpleTestCase, TestCase, override_settings

from core import mail as mail_module
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


# Runs submitted work at once, so a test can read the outbox after it.
INLINE_EXECUTOR = mock.Mock(submit=lambda fn, *args: fn(*args))


@override_settings(
    EMAIL_BACKEND="core.mail.ThreadedEmailBackend",
    EMAIL_DELIVERY_BACKEND="django.core.mail.backends.locmem.EmailBackend",
)
class ThreadedBackendTests(TestCase):
    """The front backend, delivering through Django's in-memory one."""

    @staticmethod
    def message():
        """A minimal email to send."""
        return EmailMessage("Hi", "Body", "x@example.com", ["a@example.com"])

    def test_mail_waits_for_the_transaction_to_commit(self):
        with mock.patch("core.mail.EXECUTOR", INLINE_EXECUTOR):
            with self.captureOnCommitCallbacks(execute=False) as callbacks:
                self.assertEqual(self.message().send(), 1)
            self.assertEqual(mail.outbox, [])
            callbacks[0]()
        self.assertEqual(mail.outbox[0].subject, "Hi")

    def test_a_failed_delivery_is_logged_not_raised(self):
        with (
            mock.patch("core.mail.EXECUTOR", INLINE_EXECUTOR),
            mock.patch(
                "django.core.mail.backends.locmem.EmailBackend.send_messages",
                side_effect=OSError("refused"),
            ),
            self.assertLogs("core.mail", "ERROR"),
            self.captureOnCommitCallbacks(execute=True),
        ):
            self.message().send()
        self.assertEqual(mail.outbox, [])

    def test_delivery_happens_off_the_request_thread(self):
        threads, futures = [], []
        submit = mail_module.EXECUTOR.submit

        def record(_backend, messages):
            threads.append(threading.current_thread().name)
            return len(messages)

        def keep_future(fn, *args):
            futures.append(submit(fn, *args))
            return futures[-1]

        with (
            mock.patch("django.core.mail.backends.locmem.EmailBackend.send_messages", record),
            mock.patch.object(mail_module.EXECUTOR, "submit", keep_future),
        ):
            with self.captureOnCommitCallbacks(execute=True):
                self.message().send()
            futures[0].result(timeout=5)
        self.assertTrue(threads[0].startswith("mail"))

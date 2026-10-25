"""Registration, login, password reset and account settings."""

import re
from unittest import mock

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core import mail
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone, translation

from accounts.forms import RegisterForm
from core.testing import EnglishPagesMixin

User = get_user_model()
PASSWORD = "quite-a-long-test-password"
SIGNUP = {
    "full_name": "Rafiq Ahmed",
    "email": "rafiq@example.com",
    "password1": PASSWORD,
    "password2": PASSWORD,
}


def link_in(message):
    """The path of the first link to this site in an email body."""
    return re.search(r"https?://[^/\s]+(/\S+)", message.body).group(1)


class RegistrationTests(EnglishPagesMixin, TestCase):
    def test_registering_creates_an_account_and_emails_a_confirmation_link(self):
        response = self.client.post(reverse("accounts:register"), SIGNUP)
        self.assertRedirects(response, reverse("accounts:confirm_sent"))
        user = User.objects.get(email="rafiq@example.com")
        self.assertEqual(user.full_name, "Rafiq Ahmed")
        self.assertTrue(user.access_enabled)
        self.assertFalse(user.email_confirmed)
        self.assertNotIn("_auth_user_id", self.client.session)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ["rafiq@example.com"])
        self.assertIn("Confirm your DhakaBassist email", mail.outbox[0].subject)
        self.assertIn("/account/confirm/", mail.outbox[0].body)

    def test_a_failed_send_still_creates_the_account_and_is_logged(self):
        with (
            mock.patch("accounts.emails.EmailMessage.send", side_effect=OSError("refused")),
            self.assertLogs("accounts.emails", "ERROR"),
        ):
            response = self.client.post(reverse("accounts:register"), SIGNUP)
        self.assertRedirects(response, reverse("accounts:confirm_sent"))
        self.assertTrue(User.objects.filter(email="rafiq@example.com").exists())

    def test_the_sent_page_names_the_address(self):
        response = self.client.post(reverse("accounts:register"), SIGNUP, follow=True)
        self.assertContains(response, "rafiq@example.com")
        self.assertContains(response, "noindex")

    def test_the_confirmation_email_follows_the_signup_language(self):
        with translation.override("bn"):
            self.client.post(reverse("accounts:register"), SIGNUP)
        self.assertEqual(User.objects.get().language, "bn")
        self.assertIn("ইমেইল", mail.outbox[0].subject)

    def test_a_duplicate_email_is_refused(self):
        User.objects.create_user(email="rafiq@example.com", password=PASSWORD)
        response = self.client.post(
            reverse("accounts:register"),
            {
                "full_name": "Someone Else",
                "email": "RAFIQ@example.com",
                "password1": PASSWORD,
                "password2": PASSWORD,
            },
        )
        self.assertContains(response, "already exists")
        self.assertEqual(User.objects.count(), 1)

    def test_a_weak_password_is_refused(self):
        response = self.client.post(
            reverse("accounts:register"),
            {
                "full_name": "Rafiq Ahmed",
                "email": "rafiq@example.com",
                "password1": "12345678",
                "password2": "12345678",
            },
        )
        self.assertEqual(User.objects.count(), 0)
        self.assertContains(response, "not only numbers")

    def test_a_five_character_password_is_refused(self):
        response = self.client.post(
            reverse("accounts:register"), {**SIGNUP, "password1": "q7#Lm", "password2": "q7#Lm"}
        )
        self.assertEqual(User.objects.count(), 0)
        self.assertContains(response, "at least 6 characters")

    def test_a_six_character_password_is_accepted(self):
        response = self.client.post(
            reverse("accounts:register"), {**SIGNUP, "password1": "q7#Lm2", "password2": "q7#Lm2"}
        )
        self.assertRedirects(response, reverse("accounts:confirm_sent"))
        self.assertTrue(User.objects.get().check_password("q7#Lm2"))

    def test_the_form_hints_the_minimum_length(self):
        response = self.client.get(reverse("accounts:register"))
        self.assertContains(response, "At least 6 characters")
        self.assertContains(response, 'minlength="6"', count=2)
        self.assertContains(response, "data-password-match-status hidden")

    def test_the_password_rules_are_listed_before_anyone_types(self):
        response = self.client.get(reverse("accounts:register"))
        self.assertContains(response, "data-rule=", count=4)
        for rule in (
            "At least 6 characters",
            "Not only numbers",
            "Not too similar to your name or email",
            "Not a common password",
        ):
            self.assertContains(response, rule)
        self.assertNotContains(response, "is-failed")

    def test_a_broken_rule_is_marked_in_the_list(self):
        response = self.client.post(
            reverse("accounts:register"),
            {**SIGNUP, "password1": "password", "password2": "password"},
        )
        rules = {rule["code"]: rule["failed"] for rule in response.context["form"].password_rules}
        self.assertEqual(
            rules,
            {
                "password_too_short": False,
                "password_entirely_numeric": False,
                "password_too_similar": False,
                "password_too_common": True,
            },
        )
        self.assertContains(response, "pw-checklist__item is-failed", count=1)

    def test_the_password_rules_are_in_bangla_on_the_bangla_page(self):
        with translation.override("bn"):
            rules = [rule["text"] for rule in RegisterForm().password_rules]
        self.assertEqual(rules[0], "কমপক্ষে 6টি অক্ষর")
        self.assertEqual(rules[1], "শুধু সংখ্যা নয়")

    def register_errors(self, **data):
        response = self.client.post(reverse("accounts:register"), {**SIGNUP, **data})
        self.assertEqual(User.objects.count(), 0)
        return response.context["form"].errors

    def test_password_rules_are_shown_under_the_password_not_the_confirmation(self):
        errors = self.register_errors(password1="12345", password2="12345")
        self.assertEqual(len(errors["password1"]), 3)
        self.assertNotIn("password2", errors)

    def test_a_mismatch_is_shown_under_the_confirmation(self):
        errors = self.register_errors(password1="q7#Lm2zz", password2="q7#Lm2zy")
        self.assertEqual(errors["password2"], ["The two passwords do not match."])

    def test_a_common_password_is_refused(self):
        errors = self.register_errors(password1="password", password2="password")
        self.assertIn("too common", errors["password1"][0])

    def test_a_password_like_the_name_is_refused(self):
        errors = self.register_errors(password1="ahmedrafiq", password2="ahmedrafiq")
        self.assertEqual(
            errors["password1"], ["This password is too close to your name or email."]
        )

    def test_password_errors_are_in_bangla_on_the_bangla_form(self):
        with translation.override("bn"):
            form = RegisterForm({**SIGNUP, "password1": "123456", "password2": "123456"})
            self.assertFalse(form.is_valid())
            self.assertIn("শুধু সংখ্যা নয়", " ".join(form.errors["password1"]))

    def test_the_home_page_email_box_opens_the_form_filled_in(self):
        response = self.client.post(
            reverse("accounts:register"), {"prefill": "1", "email": "rafiq@example.com"}
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.context["form"].is_bound)
        self.assertEqual(response.context["form"].initial["email"], "rafiq@example.com")
        self.assertEqual(User.objects.count(), 0)

    def test_registering_grants_no_enrolment(self):
        self.client.post(
            reverse("accounts:register"),
            {
                "full_name": "Rafiq Ahmed",
                "email": "rafiq@example.com",
                "password1": PASSWORD,
                "password2": PASSWORD,
            },
        )
        user = User.objects.get(email="rafiq@example.com")
        self.assertEqual(user.enrollments.count(), 0)


class EmailConfirmationTests(EnglishPagesMixin, TestCase):
    def setUp(self):
        self.client.post(reverse("accounts:register"), SIGNUP)
        self.user = User.objects.get(email="rafiq@example.com")
        self.link = link_in(mail.outbox[0])

    def test_an_unconfirmed_account_cannot_log_in(self):
        response = self.client.post(
            reverse("accounts:login"), {"username": "rafiq@example.com", "password": PASSWORD}
        )
        self.assertContains(response, "Confirm your email address before logging in")
        self.assertContains(response, reverse("accounts:confirm_resend"))
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_a_wrong_password_does_not_reveal_the_account_is_unconfirmed(self):
        response = self.client.post(
            reverse("accounts:login"), {"username": "rafiq@example.com", "password": "nope-nope"}
        )
        self.assertContains(response, "do not match an account")
        self.assertNotContains(response, "Confirm your email address")

    def test_opening_the_link_changes_nothing_until_the_button_is_pressed(self):
        response = self.client.get(self.link)
        self.assertContains(response, "Confirm my email")
        self.assertContains(response, "noindex")
        self.user.refresh_from_db()
        self.assertFalse(self.user.email_confirmed)

    def test_confirming_signs_the_student_in(self):
        response = self.client.post(self.link)
        self.assertRedirects(response, reverse("courses:dashboard"))
        self.user.refresh_from_db()
        self.assertTrue(self.user.email_confirmed)
        self.assertEqual(int(self.client.session["_auth_user_id"]), self.user.pk)

    def test_a_confirmed_account_can_log_in(self):
        self.client.post(self.link)
        self.client.logout()
        response = self.client.post(
            reverse("accounts:login"), {"username": "rafiq@example.com", "password": PASSWORD}
        )
        self.assertRedirects(response, reverse("courses:dashboard"))

    def test_the_link_works_once(self):
        self.client.post(self.link)
        self.client.logout()
        response = self.client.post(self.link)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "already confirmed")
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_a_tampered_link_is_refused(self):
        response = self.client.post(self.link.rstrip("/") + "x/")
        self.assertContains(response, "This link has expired")
        self.user.refresh_from_db()
        self.assertFalse(self.user.email_confirmed)

    def test_the_link_stops_working_if_the_email_changes(self):
        User.objects.filter(pk=self.user.pk).update(email="other@example.com")
        response = self.client.post(self.link)
        self.assertContains(response, "This link has expired")

    def test_confirming_does_not_unblock_an_account_staff_turned_off(self):
        User.objects.filter(pk=self.user.pk).update(is_active=False)
        self.client.post(self.link)
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_a_new_link_can_be_requested(self):
        response = self.client.post(
            reverse("accounts:confirm_resend"), {"email": "RAFIQ@example.com"}
        )
        self.assertRedirects(response, reverse("accounts:confirm_sent"))
        self.assertEqual(len(mail.outbox), 2)
        self.client.post(link_in(mail.outbox[1]))
        self.user.refresh_from_db()
        self.assertTrue(self.user.email_confirmed)

    def test_asking_for_a_link_reveals_nothing_about_an_address(self):
        self.client.post(self.link)
        for email in ("nobody@example.com", "rafiq@example.com"):
            with self.subTest(email=email):
                response = self.client.post(reverse("accounts:confirm_resend"), {"email": email})
                self.assertRedirects(response, reverse("accounts:confirm_sent"))
        self.assertEqual(len(mail.outbox), 1)

    def test_a_password_reset_link_also_confirms_the_email(self):
        self.client.post(reverse("accounts:password_reset"), {"email": "rafiq@example.com"})
        confirm = self.client.get(link_in(mail.outbox[1]), follow=True)
        new_password = "another-long-test-password"
        self.client.post(
            confirm.redirect_chain[-1][0],
            {"new_password1": new_password, "new_password2": new_password},
        )
        self.user.refresh_from_db()
        self.assertTrue(self.user.email_confirmed)



# Its own class: robots.txt and the sitemap sit outside the language prefix,
# so requesting them switches the active language back to Bangla.
class ConfirmationSearchTests(TestCase):
    def test_the_confirmation_pages_are_kept_out_of_search(self):
        robots = self.client.get("/robots.txt").content.decode()
        self.assertIn("Disallow: /account/", robots)
        self.assertIn("Disallow: /en/account/", robots)
        sitemap = self.client.get("/sitemap.xml").content.decode()
        self.assertNotIn("/account/confirm", sitemap)


class LoginTests(EnglishPagesMixin, TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email="rafiq@example.com",
            password=PASSWORD,
            full_name="Rafiq Ahmed",
            email_confirmed_at=timezone.now(),
        )

    def test_login_works_and_is_case_insensitive_on_the_email(self):
        response = self.client.post(
            reverse("accounts:login"),
            {"username": "RAFIQ@EXAMPLE.COM", "password": PASSWORD, "remember_me": "on"},
        )
        self.assertRedirects(response, reverse("courses:dashboard"))

    def test_a_wrong_password_is_refused(self):
        response = self.client.post(
            reverse("accounts:login"),
            {"username": "rafiq@example.com", "password": "wrong-password"},
        )
        self.assertContains(response, "do not match an account")

    def test_an_inactive_account_cannot_sign_in(self):
        self.user.is_active = False
        self.user.save(update_fields=["is_active"])
        response = self.client.post(
            reverse("accounts:login"),
            {"username": "rafiq@example.com", "password": PASSWORD},
        )
        self.assertContains(response, "do not match an account")

    def test_not_asking_to_be_remembered_ends_the_session_at_browser_close(self):
        self.client.post(
            reverse("accounts:login"),
            {"username": "rafiq@example.com", "password": PASSWORD},
        )
        self.assertTrue(self.client.session.get_expire_at_browser_close())

    def test_logging_out_ends_the_session(self):
        self.client.force_login(self.user)
        response = self.client.post(reverse("accounts:logout"))
        self.assertRedirects(response, reverse("pages:home"))
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_the_login_page_is_not_indexed(self):
        response = self.client.get(reverse("accounts:login"))
        self.assertContains(response, "noindex")


class PasswordResetTests(EnglishPagesMixin, TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email="rafiq@example.com", password=PASSWORD, language="en"
        )

    def test_a_reset_email_is_sent_for_a_known_address(self):
        self.client.post(reverse("accounts:password_reset"), {"email": "rafiq@example.com"})
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("Reset your DhakaBassist password", mail.outbox[0].subject)
        self.assertIn("/password/reset/", mail.outbox[0].body)

    def test_the_link_uses_the_site_address_not_the_request_host(self):
        with self.settings(ALLOWED_HOSTS=["evil.example"]):
            self.client.post(
                reverse("accounts:password_reset"),
                {"email": "rafiq@example.com"},
                HTTP_HOST="evil.example",
            )
        self.assertNotIn("evil.example", mail.outbox[0].body)
        self.assertIn(settings.SITE["base_url"] + "/", mail.outbox[0].body)

    def test_the_email_follows_the_student_s_language(self):
        User.objects.filter(pk=self.user.pk).update(language="bn")
        self.client.post(reverse("accounts:password_reset"), {"email": "rafiq@example.com"})
        self.assertIn("পাসওয়ার্ড", mail.outbox[0].subject)

    def test_a_new_password_works_and_the_link_works_once(self):
        self.client.post(reverse("accounts:password_reset"), {"email": "rafiq@example.com"})
        link = link_in(mail.outbox[0])
        form_page = self.client.get(link, follow=True)
        set_url = form_page.redirect_chain[-1][0]
        new_password = "another-long-test-password"
        response = self.client.post(
            set_url, {"new_password1": new_password, "new_password2": new_password}
        )
        self.assertRedirects(response, reverse("accounts:password_reset_complete"))
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(new_password))
        self.assertContains(self.client.get(link, follow=True), "This link has expired")

    def test_an_unknown_address_reveals_nothing(self):
        response = self.client.post(
            reverse("accounts:password_reset"), {"email": "nobody@example.com"}
        )
        self.assertRedirects(response, reverse("accounts:password_reset_done"))
        self.assertEqual(len(mail.outbox), 0)


class AccountSettingsTests(EnglishPagesMixin, TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email="rafiq@example.com", password=PASSWORD, full_name="Rafiq Ahmed"
        )
        self.client.force_login(self.user)

    def test_details_can_be_changed(self):
        response = self.client.post(
            reverse("accounts:settings"),
            {
                "full_name": "Rafiq A. Ahmed",
                "email": "rafiq@example.com",
                "language": "en",
                "marketing_opt_in": "on",
            },
            follow=True,
        )
        self.user.refresh_from_db()
        self.assertEqual(self.user.full_name, "Rafiq A. Ahmed")
        self.assertTrue(self.user.marketing_opt_in)
        self.assertContains(response, "have been saved")

    def test_profile_details_are_optional_and_can_be_updated(self):
        url = reverse("accounts:settings")
        details = {
            "full_name": "Rafiq Ahmed",
            "email": "rafiq@example.com",
            "profession": "Software engineer",
            "education": "BSc, University of Dhaka",
            "location": "Dhaka, Bangladesh",
            "language": "bn",
        }
        self.client.post(url, details)
        self.user.refresh_from_db()
        self.assertEqual(self.user.profession, "Software engineer")
        self.assertEqual(self.user.education, "BSc, University of Dhaka")
        self.assertEqual(self.user.location, "Dhaka, Bangladesh")

        # Clearing them later is allowed: every profile detail is optional.
        cleared = {**details, "profession": "", "education": "", "location": ""}
        response = self.client.post(url, cleared, follow=True)
        self.assertContains(response, "have been saved")
        self.user.refresh_from_db()
        self.assertEqual(
            (self.user.profession, self.user.education, self.user.location), ("", "", "")
        )

    def test_taking_another_account_s_email_is_refused(self):
        User.objects.create_user(email="taken@example.com", password=PASSWORD)
        response = self.client.post(
            reverse("accounts:settings"),
            {"full_name": "Rafiq Ahmed", "email": "taken@example.com"},
        )
        self.assertContains(response, "already uses this email")

    def test_settings_require_a_signed_in_user(self):
        self.client.logout()
        response = self.client.get(reverse("accounts:settings"))
        self.assertIn(reverse("accounts:login"), response["Location"])


class UserModelTests(TestCase):
    def test_initials_come_from_the_name_then_the_email(self):
        named = User(full_name="Rafiq Ahmed", email="rafiq@example.com")
        self.assertEqual(named.initials, "RA")
        unnamed = User(email="nusrat@example.com")
        self.assertEqual(unnamed.initials, "NU")

    def test_creating_a_user_without_an_email_fails(self):
        with self.assertRaises(ValueError):
            User.objects.create_user(email="", password=PASSWORD)

    def test_a_superuser_is_staff(self):
        admin = User.objects.create_superuser(email="t@example.com", password=PASSWORD)
        self.assertTrue(admin.is_staff)
        self.assertTrue(admin.is_superuser)

    def test_a_superuser_is_confirmed_and_a_new_user_is_not(self):
        admin = User.objects.create_superuser(email="t@example.com", password=PASSWORD)
        self.assertTrue(admin.email_confirmed)
        self.assertFalse(User.objects.create_user(email="s@example.com").email_confirmed)

"""Registration, login, password reset and account settings."""

from django.contrib.auth import get_user_model
from django.core import mail
from django.test import TestCase
from django.urls import reverse

User = get_user_model()
PASSWORD = "quite-a-long-test-password"


class RegistrationTests(TestCase):
    def test_registering_creates_an_account_and_signs_in(self):
        response = self.client.post(
            reverse("accounts:register"),
            {
                "full_name": "Rafiq Ahmed",
                "email": "rafiq@example.com",
                "password1": PASSWORD,
                "password2": PASSWORD,
            },
        )
        self.assertRedirects(response, reverse("courses:dashboard"))
        user = User.objects.get(email="rafiq@example.com")
        self.assertEqual(user.full_name, "Rafiq Ahmed")
        self.assertTrue(user.access_enabled)

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
        self.assertContains(response, "entirely numeric")

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


class LoginTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email="rafiq@example.com", password=PASSWORD, full_name="Rafiq Ahmed"
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


class PasswordResetTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(email="rafiq@example.com", password=PASSWORD)

    def test_a_reset_email_is_sent_for_a_known_address(self):
        self.client.post(reverse("accounts:password_reset"), {"email": "rafiq@example.com"})
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("Reset your DhakaBassist password", mail.outbox[0].subject)
        self.assertIn("/password/reset/", mail.outbox[0].body)

    def test_an_unknown_address_reveals_nothing(self):
        response = self.client.post(
            reverse("accounts:password_reset"), {"email": "nobody@example.com"}
        )
        self.assertRedirects(response, reverse("accounts:password_reset_done"))
        self.assertEqual(len(mail.outbox), 0)


class AccountSettingsTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email="rafiq@example.com", password=PASSWORD, full_name="Rafiq Ahmed"
        )
        self.client.force_login(self.user)

    def test_details_can_be_changed(self):
        response = self.client.post(
            reverse("accounts:settings"),
            {"full_name": "Rafiq A. Ahmed", "email": "rafiq@example.com", "marketing_opt_in": "on"},
            follow=True,
        )
        self.user.refresh_from_db()
        self.assertEqual(self.user.full_name, "Rafiq A. Ahmed")
        self.assertTrue(self.user.marketing_opt_in)
        self.assertContains(response, "have been saved")

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

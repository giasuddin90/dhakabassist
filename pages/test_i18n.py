"""The site in two languages: Bangla at /, English under /en/."""

import json
import re

from django.contrib.auth import get_user_model
from django.core import mail
from django.test import TestCase
from django.urls import reverse
from django.utils import translation

from courses.models import Course, Module
from orders.emails import send_receipt
from orders.models import Order, PaymentMethod

User = get_user_model()
BASE = "http://127.0.0.1:8000"


def make_course():
    course = Course.objects.create(
        title_bn="সংগীতের ভিত্তি",
        title_en="Foundations of Music",
        slug="foundations-of-music",
        summary_bn="বাংলা সারাংশ।",
        summary_en="English summary.",
        description_en="Description.",
        price=3500,
        status=Course.Status.PUBLISHED,
    )
    Module.objects.create(
        course=course,
        number="01",
        slug="sound",
        title_bn="শব্দ",
        title_en="Sound",
        access=Module.Access.FREE,
        status=Module.Status.PUBLISHED,
    )
    return course


def json_ld(response):
    match = re.search(
        r'<script type="application/ld\+json">(.*?)</script>', response.content.decode(), re.DOTALL
    )
    return json.loads(match.group(1))["@graph"]


class LanguageUrlTests(TestCase):
    def setUp(self):
        self.course = make_course()

    def tearDown(self):
        translation.activate("bn")

    def test_unprefixed_pages_are_bangla(self):
        response = self.client.get("/")
        self.assertContains(response, '<html lang="bn">')
        self.assertContains(response, f'<link rel="canonical" href="{BASE}/">')
        self.assertContains(response, "সংগীতের ভিত্তি")
        self.assertContains(response, "এখনই ভর্তি হোন")  # "Enroll now"
        self.assertContains(response, '<meta property="og:locale" content="bn_BD">')

    def test_en_prefixed_pages_are_english(self):
        response = self.client.get("/en/")
        self.assertContains(response, '<html lang="en">')
        self.assertContains(response, f'<link rel="canonical" href="{BASE}/en/">')
        self.assertContains(response, "Foundations of Music")
        self.assertContains(response, "Enroll now")
        self.assertNotContains(response, "সংগীতের ভিত্তি")

    def test_every_public_page_links_its_other_language(self):
        for path in ("/", "/courses/foundations-of-music/", "/faq/"):
            with self.subTest(path=path):
                response = self.client.get(path)
                alternate = '<link rel="alternate" hreflang="{}" href="{}">'
                self.assertContains(response, alternate.format("bn", f"{BASE}{path}"))
                self.assertContains(response, alternate.format("en", f"{BASE}/en{path}"))
                self.assertContains(
                    response, f'<link rel="alternate" hreflang="x-default" href="{BASE}{path}">'
                )
                # The visible switcher points at the same page in English.
                self.assertContains(response, f'href="/en{path}" hreflang="en" lang="en"')

    def test_json_ld_states_the_page_language(self):
        bangla = next(n for n in json_ld(self.client.get("/")) if n["@type"] == "Course")
        english = next(n for n in json_ld(self.client.get("/en/")) if n["@type"] == "Course")
        self.assertEqual(bangla["inLanguage"], "bn")
        self.assertEqual(bangla["name"], "সংগীতের ভিত্তি")
        self.assertEqual(english["inLanguage"], "en")
        self.assertEqual(english["name"], "Foundations of Music")

    def test_bangla_falls_back_to_english_until_translated(self):
        Course.objects.filter(pk=self.course.pk).update(summary_bn="")
        response = self.client.get("/courses/foundations-of-music/")
        self.assertContains(response, "English summary.")

    def test_breadcrumbs_link_within_the_language(self):
        response = self.client.get("/en/faq/")
        self.assertContains(response, '<a href="/en/">Home</a>')

    def test_private_pages_carry_no_hreflang(self):
        user = User.objects.create_user(email="rafiq@example.com", password="long-pass-123!")
        self.client.force_login(user)
        response = self.client.get(reverse("courses:dashboard"))
        self.assertContains(response, 'content="noindex, nofollow"')
        self.assertNotContains(response, 'hreflang="x-default"')


class DiscoveryFileTests(TestCase):
    def setUp(self):
        make_course()

    def test_the_sitemap_lists_both_languages_with_alternates(self):
        body = self.client.get("/sitemap.xml").content.decode()
        self.assertIn("<loc>https://testserver/courses/foundations-of-music/</loc>", body)
        self.assertIn("<loc>https://testserver/en/courses/foundations-of-music/</loc>", body)
        self.assertIn('hreflang="x-default"', body)
        for private in ("/learn/", "/my-courses/", "/enroll/", "/manage/"):
            self.assertNotIn(private, body)

    def test_robots_blocks_private_paths_in_both_languages(self):
        body = self.client.get("/robots.txt").content.decode()
        for path in ("/learn/", "/en/learn/", "/my-courses/", "/en/my-courses/", "/manage/"):
            self.assertIn(f"Disallow: {path}\n", body)

    def test_llms_txt_is_english_whatever_the_crawler_asks_for(self):
        body = self.client.get("/llms.txt", HTTP_ACCEPT_LANGUAGE="bn").content.decode()
        self.assertIn("## Foundations of Music", body)
        self.assertIn("Bangla and English", body)
        self.assertIn(f"{BASE}/en/courses/foundations-of-music/", body)


class StaffPanelLanguageTests(TestCase):
    def test_the_staff_panel_stays_english_for_a_bangla_browser(self):
        staff = User.objects.create_user(
            email="staff@example.com", password="long-pass-123!", is_staff=True
        )
        self.client.force_login(staff)
        response = self.client.get(reverse("manage:overview"), HTTP_ACCEPT_LANGUAGE="bn")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'lang="en"')


class EmailLanguageTests(TestCase):
    def setUp(self):
        self.course = make_course()

    def receipt_for(self, language):
        student = User.objects.create_user(
            email=f"{language}@example.com", password="long-pass-123!", language=language
        )
        order = Order.objects.create(
            student=student, course=self.course, amount=3500, method=PaymentMethod.BKASH
        )
        order.mark_paid("TRX1")
        mail.outbox.clear()
        send_receipt(order)
        return mail.outbox[0]

    def test_every_receipt_is_in_english(self):
        for language in ("bn", "en"):
            # Sent from a Bangla page either way, as a payment callback may be.
            with self.subTest(student=language), translation.override("bn"):
                message = self.receipt_for(language)
                self.assertIn("receipt", message.subject)
                self.assertIn("Foundations of Music", message.body)
                self.assertIn("/en/my-courses/", message.body)
                self.assertNotIn("সংগীতের ভিত্তি", message.body)

    def test_registration_remembers_the_language_signed_up_in(self):
        self.client.post(
            "/en/register/",
            {
                "full_name": "Nusrat Jahan",
                "email": "nusrat@example.com",
                "password1": "a-long-passphrase-42",
                "password2": "a-long-passphrase-42",
            },
        )
        self.assertEqual(User.objects.get(email="nusrat@example.com").language, "en")

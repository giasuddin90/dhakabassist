"""Downloads: who may fetch which file, buying one, and the public list."""

import json
import re
import shutil
import tempfile
from pathlib import Path

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core import mail
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError
from django.test import TestCase, override_settings
from django.urls import reverse

from core.testing import EnglishPagesMixin
from courses.models import Course
from orders.models import Order, PaymentMethod

from .models import Download

User = get_user_model()
PASSWORD = "quite-a-long-test-password"
MEDIA = Path(tempfile.mkdtemp())


def make_download(title="Major scales worksheet", price=0, access=None, **extra):
    """Free when no price is given, premium otherwise, unless `access` says."""
    defaults = {
        "title_en": title,
        "description_en": "Fill in every major scale.",
        "file_en": SimpleUploadedFile("scales.pdf", b"%PDF-1.4 test"),
        "price": price,
        "access": access or (Download.Access.PREMIUM if price else Download.Access.FREE),
        "status": Download.Status.PUBLISHED,
    }
    defaults.update(extra)
    return Download.objects.create(**defaults)


def pay_for(student, download, status=Order.Status.PAID):
    return Order.objects.create(
        student=student,
        download=download,
        amount=download.price,
        method=PaymentMethod.BKASH,
        status=status,
    )


def json_ld_types(response):
    script = re.search(
        r'<script type="application/ld\+json">(.*?)</script>', response.content.decode(), re.DOTALL
    )
    return {node["@type"] for node in json.loads(script.group(1))["@graph"]}


@override_settings(MEDIA_ROOT=MEDIA)
class MediaTestCase(TestCase):
    """Writes uploads to a throwaway folder."""

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(MEDIA, ignore_errors=True)
        super().tearDownClass()

    def setUp(self):
        self.student = User.objects.create_user(
            email="rafiq@example.com", password=PASSWORD, full_name="Rafiq Ahmed"
        )


class AccessRuleTests(MediaTestCase):
    def test_a_free_download_is_open_to_any_signed_in_account(self):
        download = make_download()
        self.assertTrue(download.is_available_to(self.student))

    def test_a_free_download_with_a_price_needs_no_order(self):
        download = make_download(price=300, access=Download.Access.FREE)
        self.assertTrue(download.is_available_to(self.student))

    def test_a_premium_download_needs_a_price(self):
        with self.assertRaises(IntegrityError):
            make_download(price=0, access=Download.Access.PREMIUM)

    def test_a_paid_download_needs_a_paid_order(self):
        download = make_download(price=250)
        self.assertFalse(download.is_available_to(self.student))
        pay_for(self.student, download, status=Order.Status.PENDING)
        self.assertFalse(download.is_available_to(self.student))
        pay_for(self.student, download)
        self.assertTrue(download.is_available_to(self.student))

    def test_a_refund_closes_the_download_again(self):
        download = make_download(price=250)
        order = pay_for(self.student, download)
        order.mark_refunded()
        self.assertFalse(download.is_available_to(self.student))

    def test_a_buyer_keeps_a_download_staff_unpublished(self):
        download = make_download(price=250)
        pay_for(self.student, download)
        download.status = Download.Status.DRAFT
        download.save()
        self.assertTrue(download.is_available_to(self.student))

    def test_a_free_draft_is_closed_to_students(self):
        download = make_download(status=Download.Status.DRAFT)
        self.assertFalse(download.is_available_to(self.student))

    def test_marking_a_download_order_paid_enrols_nobody(self):
        order = pay_for(self.student, make_download(price=250), status=Order.Status.PENDING)
        order.mark_paid()
        self.assertFalse(self.student.enrollments.exists())

    def test_an_order_buys_exactly_one_item(self):
        course = Course.objects.create(
            title="Course", slug="course", summary="S.", description="D."
        )
        with self.assertRaises(IntegrityError):
            Order.objects.create(
                student=self.student,
                course=course,
                download=make_download(price=250),
                amount=250,
                method=PaymentMethod.BKASH,
            )


class FileViewTests(MediaTestCase):
    def test_anonymous_visitors_are_sent_to_log_in(self):
        download = make_download()
        response = self.client.get(download.get_file_url())
        self.assertIn(reverse("accounts:login"), response["Location"])

    def test_a_free_file_downloads_as_an_attachment(self):
        download = make_download()
        self.client.force_login(self.student)
        response = self.client.get(download.get_file_url())
        self.assertEqual(response.status_code, 200)
        self.assertIn("attachment", response["Content-Disposition"])
        self.assertEqual(response["X-Robots-Tag"], "noindex, nofollow")
        self.assertEqual(b"".join(response.streaming_content), b"%PDF-1.4 test")

    def test_an_unpaid_file_sends_the_student_to_checkout(self):
        download = make_download(price=250)
        self.client.force_login(self.student)
        response = self.client.get(download.get_file_url())
        self.assertRedirects(response, download.get_buy_url(), fetch_redirect_response=False)

    def test_a_bought_file_downloads(self):
        download = make_download(price=250)
        pay_for(self.student, download)
        self.client.force_login(self.student)
        self.assertEqual(self.client.get(download.get_file_url()).status_code, 200)

    def test_a_draft_is_not_found_for_students_but_open_to_staff(self):
        download = make_download(price=250, status=Download.Status.DRAFT)
        self.client.force_login(self.student)
        self.assertEqual(self.client.get(download.get_file_url()).status_code, 404)
        staff = User.objects.create_user(
            email="staff@example.com", password=PASSWORD, is_staff=True
        )
        self.client.force_login(staff)
        self.assertEqual(self.client.get(download.get_file_url()).status_code, 200)


@override_settings(PAYMENT_GATEWAY="sandbox")
class BuyingTests(EnglishPagesMixin, MediaTestCase):
    def setUp(self):
        super().setUp()
        self.download = make_download("Bass groove pack", price=450)
        self.client.force_login(self.student)

    def test_checkout_shows_the_download_and_its_price(self):
        response = self.client.get(self.download.get_buy_url())
        self.assertContains(response, "Bass groove pack")
        self.assertContains(response, "Pay ৳450")
        self.assertContains(response, 'content="noindex, nofollow"')

    def test_paying_unlocks_the_download_and_emails_a_receipt(self):
        response = self.client.post(self.download.get_buy_url(), {"method": PaymentMethod.NAGAD})
        order = Order.objects.get()
        self.assertEqual((order.download, order.course, order.amount), (self.download, None, 450))
        self.assertRedirects(
            response, reverse("orders:sandbox", kwargs={"reference": order.reference})
        )

        response = self.client.post(
            reverse("orders:sandbox_complete", kwargs={"reference": order.reference}),
            {"result": "success"},
            follow=True,
        )
        self.assertContains(response, "Your download is ready")
        self.assertContains(response, self.download.get_file_url())
        self.assertTrue(self.download.is_available_to(self.student))
        self.assertIn("Bass groove pack", mail.outbox[0].body)
        self.assertIn(reverse("downloads:mine"), mail.outbox[0].body)

    def test_a_failed_payment_returns_to_the_download_checkout(self):
        self.client.post(self.download.get_buy_url(), {"method": PaymentMethod.NAGAD})
        order = Order.objects.get()
        response = self.client.post(
            reverse("orders:sandbox_complete", kwargs={"reference": order.reference}),
            {"result": "failure"},
        )
        self.assertRedirects(response, self.download.get_buy_url(), fetch_redirect_response=False)
        self.assertFalse(self.download.is_available_to(self.student))

    def test_an_owned_download_is_not_sold_twice(self):
        pay_for(self.student, self.download)
        response = self.client.get(self.download.get_buy_url())
        self.assertRedirects(response, reverse("downloads:mine"), fetch_redirect_response=False)

    def test_a_free_download_has_no_checkout(self):
        free = make_download("Free sheet", price=300, access=Download.Access.FREE)
        response = self.client.post(free.get_buy_url(), {"method": PaymentMethod.NAGAD})
        self.assertRedirects(response, reverse("downloads:list"), fetch_redirect_response=False)
        self.assertFalse(Order.objects.exists())

    def test_my_downloads_lists_only_what_was_bought(self):
        pay_for(self.student, self.download)
        make_download("Not bought", price=100)
        response = self.client.get(reverse("downloads:mine"))
        self.assertContains(response, "Bass groove pack")
        self.assertNotContains(response, "Not bought")
        self.assertContains(response, 'content="noindex, nofollow"')

    def test_order_history_links_a_paid_download(self):
        pay_for(self.student, self.download)
        response = self.client.get(reverse("accounts:orders"))
        self.assertContains(response, f'href="{self.download.get_file_url()}"')


class ListPageTests(EnglishPagesMixin, MediaTestCase):
    def test_the_list_is_indexable_with_its_own_metadata(self):
        make_download()
        response = self.client.get(reverse("downloads:list"))
        self.assertContains(response, "<title>Downloads: worksheets, PDFs and audio")
        self.assertContains(
            response, f'<link rel="canonical" href="{settings.SITE["base_url"]}/en/downloads/">'
        )
        self.assertContains(response, 'content="index, follow"')
        self.assertTrue({"ItemList", "BreadcrumbList"} <= json_ld_types(response))

    def test_buttons_follow_price_and_ownership(self):
        free = make_download("Free sheet")
        paid = make_download("Paid pack", price=300)
        response = self.client.get(reverse("downloads:list"))
        self.assertContains(response, "Log in to download")
        self.assertContains(response, paid.get_buy_url())

        pay_for(self.student, paid)
        self.client.force_login(self.student)
        response = self.client.get(reverse("downloads:list"))
        self.assertContains(response, "Download free")
        self.assertContains(response, free.get_file_url())
        self.assertContains(response, paid.get_file_url())
        self.assertNotContains(response, paid.get_buy_url())

    def test_a_free_download_shows_its_usual_price_struck_through(self):
        free = make_download("Worth having", price=300, access=Download.Access.FREE)
        self.client.force_login(self.student)
        response = self.client.get(reverse("downloads:list"))
        self.assertContains(response, "Usual price")
        self.assertContains(response, "৳300</s>")
        self.assertContains(response, "Download free")
        self.assertNotContains(response, free.get_buy_url())
        self.assertIn('"price": "0"', response.content.decode())

    def test_the_list_is_paginated_and_each_page_has_its_own_canonical(self):
        for number in range(13):
            make_download(f"Sheet {number:02d}", position=number)
        page_one = self.client.get(reverse("downloads:list"))
        self.assertEqual(len(page_one.context["downloads"]), 12)
        self.assertContains(page_one, 'rel="next"')

        page_two = self.client.get(reverse("downloads:list"), {"page": 2})
        self.assertContains(page_two, "Sheet 12")
        self.assertContains(page_two, "/en/downloads/?page=2")
        self.assertContains(page_two, "page 2")

    def test_the_type_filter_narrows_the_list(self):
        make_download("A worksheet")
        make_download(
            "A backing track",
            kind=Download.Kind.AUDIO,
            file_en=SimpleUploadedFile("track.mp3", b"ID3"),
        )
        response = self.client.get(reverse("downloads:list"), {"type": "audio"})
        self.assertContains(response, "A backing track")
        self.assertNotContains(response, "A worksheet")

    def test_drafts_stay_off_the_list(self):
        make_download("Hidden draft", status=Download.Status.DRAFT)
        self.assertNotContains(self.client.get(reverse("downloads:list")), "Hidden draft")

    def test_the_menu_links_the_downloads_after_the_course(self):
        nav = self.client.get(reverse("pages:home")).content.decode()
        nav = nav.split('id="primary-nav"', 1)[1].split("</nav>", 1)[0]
        self.assertLess(nav.index("Course"), nav.index(reverse("downloads:list")))


class DiscoveryFileTests(MediaTestCase):
    """Apart from the English page tests: these unprefixed paths leave the
    thread in Bangla for whatever runs next in the class."""

    def test_discovery_files_list_the_page_and_hide_the_files(self):
        self.assertIn("/downloads/", self.client.get("/sitemap.xml").content.decode())
        self.assertNotIn("/my-downloads/", self.client.get("/sitemap.xml").content.decode())
        robots = self.client.get("/robots.txt").content.decode()
        self.assertIn("Disallow: /my-downloads/", robots)
        self.assertIn("Disallow: /downloads/*/", robots)
        self.assertIn("/en/downloads/", self.client.get("/llms.txt").content.decode())


class ManagePanelTests(MediaTestCase):
    def setUp(self):
        super().setUp()
        self.staff = User.objects.create_user(
            email="staff@example.com", password=PASSWORD, is_staff=True
        )
        self.client.force_login(self.staff)

    def test_staff_add_a_download_with_its_file(self):
        response = self.client.post(
            reverse("manage:download_new"),
            {
                "title_en": "Chord chart",
                "kind": Download.Kind.PDF,
                "file_bn": SimpleUploadedFile("chart.pdf", b"%PDF-1.4"),
                "access": Download.Access.PREMIUM,
                "price": "150",
                "status": Download.Status.PUBLISHED,
                "position": "0",
            },
        )
        self.assertRedirects(response, reverse("manage:downloads"))
        download = Download.objects.get()
        self.assertEqual(download.slug, "chord-chart")
        self.assertTrue(download.file_bn.name.startswith("downloads/chord-chart/bn/"))

    def test_a_download_needs_a_file(self):
        response = self.client.post(
            reverse("manage:download_new"),
            {
                "title_en": "No file",
                "kind": "pdf",
                "access": Download.Access.FREE,
                "price": "0",
                "status": "draft",
                "position": "0",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Download.objects.exists())

    def test_a_premium_download_without_a_price_is_refused(self):
        response = self.client.post(
            reverse("manage:download_new"),
            {
                "title_en": "Priceless",
                "kind": "pdf",
                "file_en": SimpleUploadedFile("p.pdf", b"%PDF-1.4"),
                "access": Download.Access.PREMIUM,
                "price": "0",
                "status": "draft",
                "position": "0",
            },
        )
        self.assertContains(response, "A premium download needs a price above 0.")
        self.assertFalse(Download.objects.exists())

    def test_a_sold_download_cannot_be_deleted(self):
        download = make_download(price=250)
        pay_for(self.student, download)
        self.client.post(reverse("manage:download_delete", kwargs={"slug": download.slug}))
        self.assertTrue(Download.objects.filter(pk=download.pk).exists())

    def test_deleting_an_unsold_download_removes_its_file(self):
        download = make_download()
        stored = Path(settings.MEDIA_ROOT) / download.file_en.name
        self.client.post(reverse("manage:download_delete", kwargs={"slug": download.slug}))
        self.assertFalse(Download.objects.exists())
        self.assertFalse(stored.exists())

    def test_refunding_a_download_order_from_the_panel_closes_it(self):
        download = make_download(price=250)
        order = pay_for(self.student, download)
        url = reverse("manage:order_edit", kwargs={"reference": order.reference})
        self.assertNotContains(self.client.get(url), "Course access")
        self.client.post(
            url,
            {
                "status": Order.Status.REFUNDED,
                "amount": "250",
                "method": PaymentMethod.BKASH,
                "gateway_reference": "",
            },
        )
        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.REFUNDED)
        self.assertFalse(download.is_available_to(self.student))

    def test_students_cannot_open_the_panel(self):
        self.client.force_login(self.student)
        self.assertEqual(self.client.get(reverse("manage:downloads")).status_code, 403)

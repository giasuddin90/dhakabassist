"""Course promotions: the discounted price, where it shows, and who pays it."""

from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone, translation

from courses.access import course_queryset
from courses.models import Promotion
from orders.models import Order, PaymentMethod
from orders.tests import PASSWORD, make_course
from pages.test_i18n import json_ld

User = get_user_model()


def make_promotion(course, starts=-1, ends=5, **extra):
    """A promotion running from `starts` to `ends` days from today."""
    today = timezone.localdate()
    defaults = {
        "name": "November offer",
        "kind": Promotion.Kind.AMOUNT,
        "value": 1000,
        "starts_on": today + timedelta(days=starts),
        "ends_on": today + timedelta(days=ends),
    }
    defaults.update(extra)
    return Promotion.objects.create(course=course, **defaults)


def english(name, **kwargs):
    with translation.override("en"):
        return reverse(name, kwargs=kwargs)


class PromotionPriceTests(TestCase):
    def setUp(self):
        self.course = make_course()

    def test_amount_and_percent_off_round_to_whole_taka(self):
        amount = Promotion(kind=Promotion.Kind.AMOUNT, value=Decimal(1000))
        percent = Promotion(kind=Promotion.Kind.PERCENT, value=Decimal(15))
        self.assertEqual(amount.apply(Decimal(3500)), Decimal(2500))
        # 3333 × 0.85 = 2833.05
        self.assertEqual(percent.apply(Decimal(3333)), Decimal(2833))
        self.assertEqual(percent.apply(Decimal(3330)), Decimal(2831))  # 2830.5 rounds up

    def test_both_days_are_included(self):
        today = timezone.localdate()
        promotion = make_promotion(self.course, starts=0, ends=2)
        self.assertTrue(promotion.is_running(today))
        self.assertTrue(promotion.is_running(today + timedelta(days=2)))
        self.assertFalse(promotion.is_running(today - timedelta(days=1)))
        self.assertFalse(promotion.is_running(today + timedelta(days=3)))
        self.assertEqual(list(Promotion.objects.running(today + timedelta(days=3))), [])

    def test_no_promotion_means_the_course_price(self):
        make_promotion(self.course, starts=-10, ends=-1)
        self.assertIsNone(self.course.current_promotion)
        self.assertEqual(self.course.current_price, self.course.price)

    def test_a_running_promotion_lowers_the_price(self):
        promotion = make_promotion(self.course)
        self.assertEqual(self.course.current_promotion, promotion)
        self.assertEqual(self.course.current_price, Decimal(2500))

    def test_a_promotion_that_would_make_the_course_free_is_ignored(self):
        make_promotion(self.course, value=3500)
        self.assertEqual(self.course.current_price, self.course.price)

    def test_overlapping_promotions_give_the_lowest_price(self):
        make_promotion(self.course, value=500)
        best = make_promotion(self.course, name="Big", kind=Promotion.Kind.PERCENT, value=40)
        self.assertEqual(self.course.current_promotion, best)
        self.assertEqual(self.course.current_price, Decimal(2100))

    def test_course_queryset_prefetches_the_running_promotion(self):
        make_promotion(self.course)
        course = course_queryset().get(pk=self.course.pk)
        with self.assertNumQueries(0):
            self.assertEqual(course.current_price, Decimal(2500))

    def test_the_database_refuses_bad_values(self):
        today = timezone.localdate()
        bad = (
            {"value": 0},
            {"kind": Promotion.Kind.PERCENT, "value": 101},
            {"starts_on": today, "ends_on": today - timedelta(days=1)},
        )
        for extra in bad:
            with (
                self.subTest(**{k: str(v) for k, v in extra.items()}),
                self.assertRaises(IntegrityError),
                transaction.atomic(),
            ):
                make_promotion(self.course, **extra)


class PromotionPageTests(TestCase):
    def setUp(self):
        self.course = make_course()

    def test_course_pages_strike_the_usual_price(self):
        make_promotion(self.course)
        for url in (
            english("courses:list"),
            english("courses:detail", slug=self.course.slug),
        ):
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertContains(response, '<del class="price__was">')
                self.assertContains(response, "৳3,500</del>")
                self.assertContains(response, "৳2,500")
                self.assertContains(response, "Ends in ")
                self.assertNotContains(response, "one-time")

    def test_the_course_page_shows_the_offer_text_in_each_language(self):
        make_promotion(
            self.course, offer_text_bn="ঈদ স্পেশাল: ৳1,000 সাশ্রয়", offer_text_en="Eid special"
        )
        with translation.override("bn"):
            bangla = reverse("courses:detail", kwargs={"slug": self.course.slug})
        self.assertContains(self.client.get(bangla), "ঈদ স্পেশাল: ৳1,000 সাশ্রয়")
        english_page = self.client.get(english("courses:detail", slug=self.course.slug))
        self.assertContains(english_page, '<p class="price__offer">Eid special</p>', html=True)
        # The list keeps to the price and the end date.
        self.assertNotContains(self.client.get(english("courses:list")), "Eid special")

    def test_offer_text_falls_back_to_the_other_language(self):
        make_promotion(self.course, offer_text_bn="ঈদ স্পেশাল")
        response = self.client.get(english("courses:detail", slug=self.course.slug))
        self.assertContains(response, "ঈদ স্পেশাল")

    def test_the_countdown_runs_to_midnight_after_the_last_day(self):
        promotion = make_promotion(self.course, starts=0, ends=0)
        tomorrow = timezone.localdate() + timedelta(days=1)
        self.assertEqual(timezone.localtime(promotion.ends_at).date(), tomorrow)
        self.assertEqual(timezone.localtime(promotion.ends_at).hour, 0)
        self.assertTrue(0 < promotion.seconds_left <= 86400)
        response = self.client.get(english("courses:detail", slug=self.course.slug))
        self.assertContains(response, 'data-offer-countdown="')
        self.assertContains(response, 'data-format="Ends in {d}d {h}h {m}m {s}s"')
        # Rendered on the server too, so it reads right without JavaScript.
        self.assertContains(response, promotion.countdown_text[:12])

    def test_countdown_text_pads_hours_minutes_and_seconds(self):
        promotion = make_promotion(self.course)
        with (
            patch.object(Promotion, "seconds_left", 3 * 86400 + 4 * 3600 + 5 * 60 + 6),
            translation.override("en"),
        ):
            self.assertEqual(promotion.countdown_text, "Ends in 3d 04h 05m 06s")

    def test_no_offer_text_means_no_empty_paragraph(self):
        make_promotion(self.course)
        response = self.client.get(english("courses:detail", slug=self.course.slug))
        self.assertNotContains(response, "price__offer")

    def test_bangla_pages_name_the_offer_in_bangla(self):
        make_promotion(self.course)
        with translation.override("bn"):
            url = reverse("courses:detail", kwargs={"slug": self.course.slug})
        response = self.client.get(url)
        self.assertContains(response, '<html lang="bn">')
        self.assertContains(response, "শেষ হতে বাকি")

    def test_json_ld_carries_the_offer_price_and_its_last_day(self):
        promotion = make_promotion(self.course)
        response = self.client.get(english("courses:detail", slug=self.course.slug))
        course = next(node for node in json_ld(response) if node["@type"] == "Course")
        self.assertEqual(course["offers"]["price"], "2500")
        self.assertEqual(course["offers"]["priceValidUntil"], promotion.ends_on.isoformat())

    def test_without_a_promotion_nothing_changes(self):
        make_promotion(self.course, starts=3, ends=10)
        response = self.client.get(english("courses:detail", slug=self.course.slug))
        self.assertNotContains(response, "price__was")
        self.assertNotContains(response, "price__countdown")
        course = next(node for node in json_ld(response) if node["@type"] == "Course")
        self.assertEqual(course["offers"]["price"], "3500")
        self.assertNotIn("priceValidUntil", course["offers"])


@override_settings(PAYMENT_GATEWAY="sandbox")
class PromotionCheckoutTests(TestCase):
    def setUp(self):
        self.course = make_course()
        self.student = User.objects.create_user(email="rafiq@example.com", password=PASSWORD)
        self.client.force_login(self.student)
        self.url = english("orders:checkout", slug=self.course.slug)

    def test_the_summary_shows_the_discount(self):
        make_promotion(self.course)
        response = self.client.get(self.url)
        self.assertContains(response, "৳3,500.00")
        self.assertContains(response, "−৳1,000.00")
        self.assertContains(response, "৳2,500.00")

    def test_the_order_is_for_the_promotion_price(self):
        promotion = make_promotion(self.course)
        self.client.post(self.url, {"method": PaymentMethod.BKASH})
        order = Order.objects.get()
        self.assertEqual(order.amount, Decimal(2500))
        self.assertEqual(order.promotion, promotion)

    def test_outside_a_promotion_the_full_price_is_charged(self):
        make_promotion(self.course, starts=-10, ends=-1)
        self.client.post(self.url, {"method": PaymentMethod.BKASH})
        order = Order.objects.get()
        self.assertEqual(order.amount, self.course.price)
        self.assertIsNone(order.promotion)


class PromotionPanelTests(TestCase):
    def setUp(self):
        self.course = make_course()
        self.staff = User.objects.create_user(
            email="tanveer@example.com", password=PASSWORD, is_staff=True
        )
        self.client.force_login(self.staff)
        self.new_url = reverse("manage:promotion_new", kwargs={"slug": self.course.slug})

    def post(self, url=None, **extra):
        today = timezone.localdate()
        data = {
            "name": "November offer",
            "kind": Promotion.Kind.AMOUNT,
            "value": "1000",
            "starts_on": today.isoformat(),
            "ends_on": (today + timedelta(days=29)).isoformat(),
        }
        data.update(extra)
        return self.client.post(url or self.new_url, data)

    def test_staff_add_a_promotion_from_the_course(self):
        response = self.post()
        self.assertRedirects(
            response, reverse("manage:course_edit", kwargs={"slug": self.course.slug})
        )
        promotion = Promotion.objects.get()
        self.assertEqual(promotion.course, self.course)
        page = self.client.get(reverse("manage:course_edit", kwargs={"slug": self.course.slug}))
        self.assertContains(page, "November offer")
        self.assertContains(page, "Running")

    def test_staff_write_the_offer_text_in_both_languages(self):
        self.post(offer_text_bn="ঈদ স্পেশাল", offer_text_en="Eid special")
        promotion = Promotion.objects.get()
        self.assertEqual(promotion.offer_text_bn, "ঈদ স্পেশাল")
        self.assertEqual(promotion.offer_text_en, "Eid special")

    def test_staff_edit_a_promotion(self):
        promotion = make_promotion(self.course)
        self.post(reverse("manage:promotion_edit", kwargs={"pk": promotion.pk}), value="500")
        promotion.refresh_from_db()
        self.assertEqual(promotion.value, 500)

    def test_bad_promotions_are_refused(self):
        make_promotion(self.course, name="Eid offer", starts=10, ends=12)
        cases = (
            ("overlap", {}, "starts_on", "overlap"),
            ("percent", {"kind": Promotion.Kind.PERCENT, "value": "120"}, "value", "at most 100"),
            ("free", {"value": "3500"}, "value", "make the course free"),
        )
        for label, extra, field, message in cases:
            with self.subTest(label):
                response = self.post(**extra)
                self.assertEqual(response.status_code, 200)
                errors = response.context["form"].errors[field]
                self.assertTrue(any(message in error for error in errors), errors)
        self.assertEqual(Promotion.objects.count(), 1)

    def test_a_promotion_with_orders_cannot_be_deleted(self):
        promotion = make_promotion(self.course)
        student = User.objects.create_user(email="rafiq@example.com", password=PASSWORD)
        Order.objects.create(
            student=student,
            course=self.course,
            amount=2500,
            method=PaymentMethod.BKASH,
            promotion=promotion,
        )
        self.client.post(reverse("manage:promotion_delete", kwargs={"pk": promotion.pk}))
        self.assertTrue(Promotion.objects.filter(pk=promotion.pk).exists())

    def test_an_unused_promotion_can_be_deleted(self):
        promotion = make_promotion(self.course)
        self.client.post(reverse("manage:promotion_delete", kwargs={"pk": promotion.pk}))
        self.assertFalse(Promotion.objects.exists())

    def test_a_manual_payment_with_no_amount_uses_the_offer_price(self):
        promotion = make_promotion(self.course)
        student = User.objects.create_user(email="rafiq@example.com", password=PASSWORD)
        self.client.post(
            reverse("manage:student_record_payment", kwargs={"pk": student.pk}),
            {
                "course": self.course.slug,
                "method": PaymentMethod.BKASH,
                "gateway_reference": "BK123456",
            },
        )
        order = Order.objects.get(student=student)
        self.assertEqual(order.amount, Decimal(2500))
        self.assertEqual(order.promotion, promotion)

"""Checkout, payment callbacks and the enrolment they grant.

The forged-callback cases matter most: a payment callback is the one request
that turns into free course access, so it must prove itself.
"""

from django.contrib.auth import get_user_model
from django.core import mail
from django.test import TestCase, override_settings
from django.urls import reverse

from courses.models import Course, Enrollment, Module
from orders.gateways import SandboxGateway
from orders.models import Order, PaymentMethod

User = get_user_model()
PASSWORD = "quite-a-long-test-password"


def make_course(**extra):
    defaults = {
        "title": "Foundations of Music",
        "slug": "foundations-of-music",
        "summary": "Summary.",
        "description": "Description.",
        "price": 3500,
        "status": Course.Status.PUBLISHED,
    }
    defaults.update(extra)
    course = Course.objects.create(**defaults)
    Module.objects.create(
        course=course,
        number="01",
        slug="sound",
        title="Sound",
        access=Module.Access.FREE,
        status=Module.Status.PUBLISHED,
    )
    return course


@override_settings(PAYMENT_GATEWAY="sandbox")
class CheckoutTests(TestCase):
    def setUp(self):
        self.course = make_course()
        self.student = User.objects.create_user(
            email="rafiq@example.com", password=PASSWORD, full_name="Rafiq Ahmed"
        )
        self.client.force_login(self.student)
        self.url = reverse("orders:checkout", kwargs={"slug": self.course.slug})

    def test_the_checkout_page_lists_every_payment_method(self):
        response = self.client.get(self.url)
        self.assertContains(response, "bKash")
        self.assertContains(response, "Nagad")
        self.assertContains(response, "Visa or Mastercard")
        self.assertContains(response, "International card")

    def test_checkout_requires_a_signed_in_user(self):
        self.client.logout()
        response = self.client.get(self.url)
        self.assertIn(reverse("accounts:login"), response["Location"])

    def test_choosing_a_method_creates_a_pending_order(self):
        response = self.client.post(self.url, {"method": PaymentMethod.BKASH})
        order = Order.objects.get()
        self.assertEqual(order.status, Order.Status.PENDING)
        self.assertEqual(order.method, PaymentMethod.BKASH)
        self.assertEqual(order.amount, self.course.price)
        self.assertRedirects(
            response,
            reverse("orders:sandbox", kwargs={"reference": order.reference}),
        )

    def test_an_unknown_method_is_refused(self):
        response = self.client.post(self.url, {"method": "bitcoin"})
        self.assertEqual(Order.objects.count(), 0)
        self.assertContains(response, "Choose a payment method")

    def test_an_already_enrolled_student_is_sent_to_their_courses(self):
        Enrollment.objects.create(student=self.student, course=self.course)
        response = self.client.get(self.url)
        self.assertRedirects(response, reverse("courses:dashboard"))

    def test_a_course_with_an_unmet_prerequisite_cannot_be_bought(self):
        part_one = self.course
        part_two = make_course(
            title="Foundations of Music",
            slug="foundations-of-music-part-2",
            requires=part_one,
        )
        response = self.client.get(
            reverse("orders:checkout", kwargs={"slug": part_two.slug})
        )
        self.assertRedirects(response, part_one.get_absolute_url())

    def test_the_prerequisite_being_met_allows_the_purchase(self):
        part_two = make_course(slug="foundations-of-music-part-2", requires=self.course)
        Enrollment.objects.create(student=self.student, course=self.course)
        response = self.client.get(
            reverse("orders:checkout", kwargs={"slug": part_two.slug})
        )
        self.assertEqual(response.status_code, 200)

    def test_card_details_are_never_asked_for(self):
        response = self.client.get(self.url)
        body = response.content.decode().lower()
        for field in ("card number", 'name="cvv"', 'name="card_number"', "expiry"):
            self.assertNotIn(field, body)


@override_settings(PAYMENT_GATEWAY="sandbox")
class PaymentOutcomeTests(TestCase):
    def setUp(self):
        self.course = make_course()
        self.student = User.objects.create_user(
            email="rafiq@example.com", password=PASSWORD, full_name="Rafiq Ahmed"
        )
        self.client.force_login(self.student)
        self.order = Order.objects.create(
            student=self.student,
            course=self.course,
            amount=self.course.price,
            method=PaymentMethod.BKASH,
            gateway="sandbox",
        )
        self.complete = reverse(
            "orders:sandbox_complete", kwargs={"reference": self.order.reference}
        )

    def test_a_successful_payment_enrols_the_student_and_emails_a_receipt(self):
        response = self.client.post(self.complete, {"result": "success"})
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, Order.Status.PAID)
        self.assertIsNotNone(self.order.paid_at)
        self.assertTrue(
            Enrollment.objects.filter(
                student=self.student, course=self.course, is_active=True
            ).exists()
        )
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn(self.order.reference, mail.outbox[0].subject)
        self.assertRedirects(
            response,
            reverse("orders:receipt", kwargs={"reference": self.order.reference}),
        )

    def test_a_failed_payment_grants_nothing(self):
        self.client.post(self.complete, {"result": "failure"})
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, Order.Status.FAILED)
        self.assertEqual(Enrollment.objects.count(), 0)
        self.assertEqual(len(mail.outbox), 0)

    def test_paying_twice_does_not_duplicate_the_enrolment_or_the_receipt(self):
        for _ in range(2):
            self.client.post(self.complete, {"result": "success"})
        self.assertEqual(Enrollment.objects.count(), 1)
        self.assertEqual(len(mail.outbox), 1)

    def test_a_callback_with_the_wrong_token_is_refused(self):
        is_paid, _, reason = SandboxGateway().verify(
            self.order, {"token": "forged", "result": "success"}
        )
        self.assertFalse(is_paid)
        self.assertIn("token", reason)

    def test_another_student_cannot_complete_this_order(self):
        intruder = User.objects.create_user(email="intruder@example.com", password=PASSWORD)
        self.client.force_login(intruder)
        response = self.client.post(self.complete, {"result": "success"})
        self.assertEqual(response.status_code, 404)
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, Order.Status.PENDING)

    def test_another_student_cannot_read_this_receipt(self):
        self.order.mark_paid()
        intruder = User.objects.create_user(email="intruder@example.com", password=PASSWORD)
        self.client.force_login(intruder)
        response = self.client.get(
            reverse("orders:receipt", kwargs={"reference": self.order.reference})
        )
        self.assertEqual(response.status_code, 404)

    def test_the_sandbox_page_is_unavailable_with_a_real_gateway(self):
        with override_settings(PAYMENT_GATEWAY="sslcommerz"):
            response = self.client.get(
                reverse("orders:sandbox", kwargs={"reference": self.order.reference})
            )
        self.assertEqual(response.status_code, 404)

    def test_an_ipn_for_an_unknown_order_is_a_404(self):
        response = self.client.post(reverse("orders:ipn"), {"tran_id": "DB-00000"})
        self.assertEqual(response.status_code, 404)

    def test_a_cancelled_return_marks_the_order_failed(self):
        session = self.client.session
        session["pending_order"] = self.order.reference
        session.save()
        self.client.get(reverse("orders:callback", kwargs={"outcome": "cancel"}))
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, Order.Status.FAILED)
        self.assertEqual(Enrollment.objects.count(), 0)


class OrderModelTests(TestCase):
    def setUp(self):
        self.course = make_course()
        self.student = User.objects.create_user(email="rafiq@example.com", password=PASSWORD)

    def order(self, **extra):
        defaults = {
            "student": self.student,
            "course": self.course,
            "amount": 3500,
            "method": PaymentMethod.BKASH,
        }
        defaults.update(extra)
        return Order.objects.create(**defaults)

    def test_every_order_gets_a_unique_reference_and_callback_token(self):
        first, second = self.order(), self.order()
        self.assertNotEqual(first.reference, second.reference)
        self.assertNotEqual(first.callback_token, second.callback_token)
        self.assertGreaterEqual(len(first.callback_token), 32)

    def test_a_refund_is_displayed_as_a_negative_amount(self):
        order = self.order(status=Order.Status.REFUNDED)
        self.assertEqual(order.amount_display, "−৳3,500")

    def test_mark_paid_reports_whether_it_changed_anything(self):
        order = self.order()
        self.assertTrue(order.mark_paid("TRX1"))
        self.assertFalse(order.mark_paid("TRX2"))
        order.refresh_from_db()
        self.assertEqual(order.gateway_reference, "TRX1")

    def test_a_late_failure_does_not_undo_a_payment(self):
        order = self.order()
        order.mark_paid("TRX1")
        order.mark_failed("Payment cancelled.")
        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.PAID)
        self.assertEqual(order.failure_reason, "")

    def test_a_refund_withdraws_the_paid_access(self):
        order = self.order()
        order.mark_paid("TRX1")
        self.assertTrue(order.mark_refunded())
        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.REFUNDED)
        self.assertFalse(Enrollment.objects.get(student=self.student).is_active)

    def test_a_refund_keeps_a_manual_grant(self):
        order = self.order(status=Order.Status.PAID)
        Enrollment.objects.create(
            student=self.student, course=self.course, granted_manually=True
        )
        self.assertTrue(order.mark_refunded())
        self.assertTrue(Enrollment.objects.get(student=self.student).is_active)

    def test_only_a_paid_order_can_be_refunded(self):
        order = self.order()
        self.assertFalse(order.mark_refunded())
        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.PENDING)

    def test_an_order_stores_no_card_data(self):
        """A regression guard: no field here should ever hold card details."""
        fields = {f.name for f in Order._meta.get_fields()}
        for forbidden in ("card_number", "cvv", "pan", "expiry", "card_holder"):
            self.assertNotIn(forbidden, fields)

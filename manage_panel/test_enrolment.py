"""Granting, revoking, manual payments and refunds from /manage/."""

from django.contrib.auth import get_user_model
from django.core import mail
from django.test import TestCase
from django.urls import reverse

from courses.access import CourseAccess
from courses.models import Enrollment
from orders.models import MANUAL_GATEWAY, Order, PaymentMethod

from .tests import PASSWORD, make_course

User = get_user_model()


class EnrollmentControlTests(TestCase):
    """Revoking a course, recording a manual payment and refunding an order."""

    def setUp(self):
        self.course, self.modules = make_course()
        self.staff = User.objects.create_user(
            email="tanveer@example.com", password=PASSWORD, is_staff=True
        )
        self.student = User.objects.create_user(
            email="rafiq@example.com", password=PASSWORD, full_name="Rafiq Ahmed"
        )
        self.client.force_login(self.staff)

    def is_enrolled(self):
        return CourseAccess(self.student, self.course).is_enrolled

    def pay(self, **extra):
        data = {
            "course": self.course.slug,
            "method": PaymentMethod.BKASH,
            "gateway_reference": "BK123456",
        }
        data.update(extra)
        return self.client.post(
            reverse("manage:student_record_payment", kwargs={"pk": self.student.pk}), data
        )

    def test_revoking_removes_access_to_one_course(self):
        Enrollment.objects.create(student=self.student, course=self.course)
        self.client.post(
            reverse("manage:student_revoke", kwargs={"pk": self.student.pk}),
            {"course": self.course.slug},
        )
        self.assertFalse(Enrollment.objects.get(student=self.student).is_active)
        self.assertFalse(self.is_enrolled())

    def test_a_manual_payment_creates_a_paid_order_and_enrols(self):
        self.pay()
        order = Order.objects.get(student=self.student)
        self.assertEqual(order.status, Order.Status.PAID)
        self.assertEqual(order.gateway, MANUAL_GATEWAY)
        self.assertEqual(order.gateway_reference, "BK123456")
        # A blank amount falls back to the course price.
        self.assertEqual(order.amount, self.course.price)
        enrollment = Enrollment.objects.get(student=self.student)
        self.assertFalse(enrollment.granted_manually)
        self.assertTrue(self.is_enrolled())
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn(order.reference, mail.outbox[0].subject)

    def test_a_manual_payment_records_the_amount_received(self):
        self.pay(amount="2000")
        self.assertEqual(Order.objects.get(student=self.student).amount, 2000)

    def test_an_enrolled_student_cannot_be_charged_again(self):
        Enrollment.objects.create(student=self.student, course=self.course)
        self.pay()
        self.assertFalse(Order.objects.exists())

    def test_a_transaction_id_cannot_pay_twice(self):
        other = User.objects.create_user(email="nadia@example.com", password=PASSWORD)
        Order.objects.create(
            student=other,
            course=self.course,
            amount=3500,
            method=PaymentMethod.BKASH,
            gateway_reference="BK123456",
            status=Order.Status.PAID,
        )
        self.pay()
        self.assertFalse(Order.objects.filter(student=self.student).exists())
        self.assertFalse(self.is_enrolled())

    def test_a_refunded_transaction_id_cannot_pay_again(self):
        self.pay()
        Order.objects.get(student=self.student).mark_refunded()
        self.pay()
        self.assertEqual(Order.objects.filter(gateway_reference="BK123456").count(), 1)
        self.assertFalse(self.is_enrolled())

    def test_a_refund_withdraws_the_access_it_paid_for(self):
        self.pay()
        order = Order.objects.get(student=self.student)
        response = self.client.post(
            reverse("manage:order_refund", kwargs={"reference": order.reference})
        )
        self.assertRedirects(response, reverse("manage:orders"))
        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.REFUNDED)
        self.assertFalse(self.is_enrolled())

    def test_the_pages_offer_refund_and_revoke(self):
        self.pay()
        detail = self.client.get(
            reverse("manage:student_detail", kwargs={"pk": self.student.pk})
        )
        self.assertContains(detail, "Revoke access")
        self.assertContains(detail, ">Refund<")
        self.assertContains(self.client.get(reverse("manage:orders")), ">Refund<")

    def test_the_new_actions_are_staff_only_and_post_only(self):
        order = Order.objects.create(
            student=self.student,
            course=self.course,
            amount=3500,
            method=PaymentMethod.BKASH,
            status=Order.Status.PAID,
        )
        urls = [
            reverse("manage:student_revoke", kwargs={"pk": self.student.pk}),
            reverse("manage:student_record_payment", kwargs={"pk": self.student.pk}),
            reverse("manage:order_refund", kwargs={"reference": order.reference}),
        ]
        for url in urls:
            self.assertEqual(self.client.get(url).status_code, 405)
        self.client.force_login(self.student)
        for url in urls:
            self.assertEqual(self.client.post(url).status_code, 404)
        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.PAID)

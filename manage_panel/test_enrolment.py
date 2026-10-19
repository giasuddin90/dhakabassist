"""Granting, revoking, manual payments, adding and editing orders, refunds and students."""

from urllib.parse import urlsplit

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


class OrderEditTests(TestCase):
    """Correcting an order by hand keeps course access in step with its status."""

    def setUp(self):
        self.course, self.modules = make_course()
        self.staff = User.objects.create_user(
            email="tanveer@example.com", password=PASSWORD, is_staff=True
        )
        self.student = User.objects.create_user(
            email="rafiq@example.com", password=PASSWORD, full_name="Rafiq Ahmed"
        )
        self.order = Order.objects.create(
            student=self.student,
            course=self.course,
            amount=3500,
            method=PaymentMethod.BKASH,
            gateway_reference="BK123456",
        )
        self.url = reverse("manage:order_edit", kwargs={"reference": self.order.reference})
        self.client.force_login(self.staff)

    def is_enrolled(self):
        return CourseAccess(self.student, self.course).is_enrolled

    def edit(self, **extra):
        data = {
            "status": Order.Status.PENDING,
            "amount": "3500",
            "method": PaymentMethod.BKASH,
            "gateway_reference": "BK123456",
        }
        data.update(extra)
        return self.client.post(self.url, data)

    def test_the_details_can_be_corrected(self):
        response = self.edit(amount="3000", method=PaymentMethod.NAGAD, gateway_reference="NG9")
        self.assertRedirects(response, reverse("manage:orders"))
        self.order.refresh_from_db()
        self.assertEqual(self.order.amount, 3000)
        self.assertEqual(self.order.method, PaymentMethod.NAGAD)
        self.assertEqual(self.order.gateway_reference, "NG9")
        self.assertEqual(self.order.status, Order.Status.PENDING)

    def test_marking_paid_enrols_and_sends_the_receipt(self):
        self.edit(status=Order.Status.PAID)
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, Order.Status.PAID)
        self.assertIsNotNone(self.order.paid_at)
        self.assertTrue(self.is_enrolled())
        self.assertEqual(len(mail.outbox), 1)
        # Saving a paid order again sends nothing new.
        self.edit(status=Order.Status.PAID, amount="3400")
        self.assertEqual(len(mail.outbox), 1)

    def test_leaving_paid_withdraws_the_access_it_paid_for(self):
        self.order.mark_paid()
        self.edit(status=Order.Status.FAILED)
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, Order.Status.FAILED)
        self.assertIsNone(self.order.paid_at)
        self.assertFalse(self.is_enrolled())

    def test_a_manual_grant_survives_a_status_change(self):
        self.order.mark_paid()
        Enrollment.objects.filter(student=self.student).update(granted_manually=True)
        self.edit(status=Order.Status.REFUNDED)
        self.assertTrue(self.is_enrolled())

    def test_another_paid_order_keeps_the_access(self):
        self.order.mark_paid()
        Order.objects.create(
            student=self.student,
            course=self.course,
            amount=3500,
            method=PaymentMethod.NAGAD,
            status=Order.Status.PAID,
        )
        self.edit(status=Order.Status.FAILED)
        self.assertTrue(self.is_enrolled())

    def test_a_paid_status_cannot_reuse_a_transaction_id(self):
        Order.objects.create(
            student=User.objects.create_user(email="nadia@example.com", password=PASSWORD),
            course=self.course,
            amount=3500,
            method=PaymentMethod.BKASH,
            gateway_reference="BK999",
            status=Order.Status.PAID,
        )
        response = self.edit(status=Order.Status.PAID, gateway_reference="BK999")
        self.assertContains(response, "Another order already uses this transaction ID.")
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, Order.Status.PENDING)
        self.assertFalse(self.is_enrolled())

    def test_it_returns_to_the_page_it_came_from_but_never_off_site(self):
        detail = reverse("manage:student_detail", kwargs={"pk": self.student.pk})
        self.assertRedirects(self.edit(next=detail), detail)
        self.assertRedirects(self.edit(next="https://evil.example/"), reverse("manage:orders"))

    def test_the_pages_link_to_the_edit_form(self):
        self.assertContains(self.client.get(reverse("manage:orders")), self.url)
        detail = self.client.get(reverse("manage:student_detail", kwargs={"pk": self.student.pk}))
        self.assertContains(detail, self.url)
        response = self.client.get(self.url)
        self.assertContains(response, f"Edit order {self.order.reference}")
        self.assertContains(response, "noindex")

    def test_it_is_staff_only(self):
        self.client.force_login(self.student)
        self.assertEqual(self.client.get(self.url).status_code, 404)
        self.assertEqual(self.edit(status=Order.Status.PAID).status_code, 404)
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, Order.Status.PENDING)


class StudentCreateTests(TestCase):
    """Adding a student by hand from /manage/students/new/."""

    def setUp(self):
        self.staff = User.objects.create_user(
            email="tanveer@example.com", password=PASSWORD, is_staff=True
        )
        self.url = reverse("manage:student_create")
        self.client.force_login(self.staff)

    def add(self, **extra):
        data = {"full_name": "Nadia Islam", "email": "nadia@example.com", "send_invite": "on"}
        data.update(extra)
        return self.client.post(self.url, data)

    def test_adding_creates_a_student_and_emails_a_password_link(self):
        response = self.add()
        student = User.objects.get(email="nadia@example.com")
        self.assertRedirects(
            response, reverse("manage:student_detail", kwargs={"pk": student.pk})
        )
        self.assertFalse(student.is_staff)
        self.assertTrue(student.is_active)
        # A password nobody knows, but usable so the reset link works.
        self.assertTrue(student.has_usable_password())
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ["nadia@example.com"])
        link = next(w for w in mail.outbox[0].body.split() if "/password/reset/" in w)
        page = self.client.get(urlsplit(link).path, follow=True)
        self.assertContains(page, "new_password1")

    def test_the_invite_is_optional(self):
        self.add(send_invite="")
        self.assertTrue(User.objects.filter(email="nadia@example.com").exists())
        self.assertEqual(len(mail.outbox), 0)

    def test_an_email_already_in_use_is_refused(self):
        User.objects.create_user(email="Nadia@example.com", password=PASSWORD)
        response = self.add()
        self.assertContains(response, "Another account already uses this email.")
        self.assertEqual(User.objects.filter(email__iexact="nadia@example.com").count(), 1)

    def test_a_name_is_required(self):
        self.add(full_name="")
        self.assertFalse(User.objects.filter(email="nadia@example.com").exists())

    def test_the_students_page_links_to_the_form(self):
        self.assertContains(self.client.get(reverse("manage:students")), self.url)
        self.assertContains(self.client.get(self.url), "Add a student")

    def test_it_is_staff_only(self):
        self.client.force_login(User.objects.create_user(email="x@example.com", password=PASSWORD))
        self.assertEqual(self.add().status_code, 404)
        self.assertFalse(User.objects.filter(email="nadia@example.com").exists())


class OrderCreateTests(TestCase):
    """Adding an order by hand from /manage/orders/new/."""

    def setUp(self):
        self.course, self.modules = make_course()
        self.staff = User.objects.create_user(
            email="tanveer@example.com", password=PASSWORD, is_staff=True
        )
        self.student = User.objects.create_user(
            email="rafiq@example.com", password=PASSWORD, full_name="Rafiq Ahmed"
        )
        self.url = reverse("manage:order_create")
        self.client.force_login(self.staff)

    def is_enrolled(self):
        return CourseAccess(self.student, self.course).is_enrolled

    def add(self, **extra):
        data = {
            "student": self.student.pk,
            "course": self.course.slug,
            "status": Order.Status.PAID,
            "method": PaymentMethod.BKASH,
            "gateway_reference": "BK123456",
        }
        data.update(extra)
        return self.client.post(self.url, data)

    def test_a_paid_order_enrols_and_sends_the_receipt(self):
        response = self.add()
        self.assertRedirects(response, reverse("manage:orders"))
        order = Order.objects.get(student=self.student)
        self.assertEqual(order.status, Order.Status.PAID)
        self.assertEqual(order.gateway, MANUAL_GATEWAY)
        self.assertEqual(order.amount, self.course.price)
        self.assertTrue(self.is_enrolled())
        self.assertEqual(len(mail.outbox), 1)

    def test_a_pending_order_needs_no_transaction_id_and_gives_no_access(self):
        self.add(status=Order.Status.PENDING, gateway_reference="", amount="2000")
        order = Order.objects.get(student=self.student)
        self.assertEqual(order.status, Order.Status.PENDING)
        self.assertEqual(order.amount, 2000)
        self.assertFalse(self.is_enrolled())
        self.assertEqual(len(mail.outbox), 0)

    def test_a_paid_order_needs_a_transaction_id(self):
        response = self.add(gateway_reference="")
        self.assertContains(response, "Enter the transaction ID for a paid order.")
        self.assertFalse(Order.objects.exists())

    def test_a_transaction_id_cannot_pay_twice(self):
        self.add()
        other = User.objects.create_user(email="nadia@example.com", password=PASSWORD)
        response = self.add(student=other.pk)
        self.assertContains(response, "Another order already uses this transaction ID.")
        self.assertEqual(Order.objects.count(), 1)

    def test_an_enrolled_student_cannot_be_charged_again(self):
        Enrollment.objects.create(student=self.student, course=self.course)
        response = self.add()
        self.assertContains(response, "already has this course.")
        self.assertFalse(Order.objects.exists())

    def test_staff_cannot_be_chosen(self):
        self.add(student=self.staff.pk)
        self.assertFalse(Order.objects.exists())

    def test_the_orders_page_links_to_the_form_and_a_student_can_be_preset(self):
        self.assertContains(self.client.get(reverse("manage:orders")), self.url)
        response = self.client.get(self.url, {"student": self.student.pk})
        self.assertContains(response, "Add an order")
        self.assertContains(response, f'<option value="{self.student.pk}" selected>')

    def test_it_is_staff_only(self):
        self.client.force_login(self.student)
        self.assertEqual(self.client.get(self.url).status_code, 404)
        self.assertEqual(self.add().status_code, 404)
        self.assertFalse(Order.objects.exists())

"""The administration panel: who may reach it, and what it can change."""

import shutil
import tempfile
from pathlib import Path

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from courses.models import (
    Choice,
    Course,
    Enrollment,
    MediaAsset,
    Module,
    Question,
    Quiz,
)
from pages.models import ContactMessage, Faq, LegalPage

User = get_user_model()
PASSWORD = "quite-a-long-test-password"


def make_course():
    course = Course.objects.create(
        title="Foundations of Music",
        slug="foundations-of-music",
        summary="Summary.",
        description="Description.",
        price=3500,
        status=Course.Status.PUBLISHED,
    )
    modules = [
        Module.objects.create(
            course=course,
            number=f"{i + 1:02d}",
            slug=f"module-{i + 1:02d}",
            title=f"Module {i + 1:02d}",
            summary="Summary.",
            access=Module.Access.FREE if i == 0 else Module.Access.PAID,
            status=Module.Status.PUBLISHED,
            position=i,
        )
        for i in range(3)
    ]
    return course, modules


class AccessTests(TestCase):
    """Nothing under /manage/ may be reachable without staff rights."""

    PATHS = ("overview", "courses", "quizzes", "students", "orders", "content")

    def setUp(self):
        self.staff = User.objects.create_user(
            email="tanveer@example.com", password=PASSWORD, full_name="Tanveer Haque", is_staff=True
        )
        self.student = User.objects.create_user(email="rafiq@example.com", password=PASSWORD)

    def test_an_anonymous_visitor_is_refused(self):
        for name in self.PATHS:
            with self.subTest(page=name):
                response = self.client.get(reverse(f"manage:{name}"))
                self.assertIn(response.status_code, (302, 403))

    def test_a_student_is_refused(self):
        self.client.force_login(self.student)
        for name in self.PATHS:
            with self.subTest(page=name):
                self.assertEqual(self.client.get(reverse(f"manage:{name}")).status_code, 403)

    def test_staff_may_enter(self):
        self.client.force_login(self.staff)
        for name in self.PATHS:
            with self.subTest(page=name):
                self.assertEqual(self.client.get(reverse(f"manage:{name}")).status_code, 200)

    def test_a_deactivated_staff_account_is_refused(self):
        self.staff.is_active = False
        self.staff.save(update_fields=["is_active"])
        self.client.force_login(self.staff)
        response = self.client.get(reverse("manage:overview"))
        self.assertIn(response.status_code, (302, 403))

    def test_the_panel_is_never_indexed(self):
        self.client.force_login(self.staff)
        response = self.client.get(reverse("manage:overview"))
        self.assertContains(response, 'content="noindex, nofollow"')

    def test_a_student_cannot_change_another_student_s_access(self):
        self.client.force_login(self.student)
        response = self.client.post(
            reverse("manage:student_access", kwargs={"pk": self.student.pk})
        )
        self.assertEqual(response.status_code, 404)
        self.student.refresh_from_db()
        self.assertTrue(self.student.access_enabled)


class StaffPanelTests(TestCase):
    def setUp(self):
        self.course, self.modules = make_course()
        self.staff = User.objects.create_user(
            email="tanveer@example.com", password=PASSWORD, full_name="Tanveer Haque", is_staff=True
        )
        self.student = User.objects.create_user(
            email="rafiq@example.com", password=PASSWORD, full_name="Rafiq Ahmed"
        )
        self.client.force_login(self.staff)

    # -- overview ----------------------------------------------------------

    def test_the_overview_reports_paying_and_free_accounts(self):
        Enrollment.objects.create(student=self.student, course=self.course)
        response = self.client.get(reverse("manage:overview"))
        self.assertContains(response, "Paying students")
        self.assertContains(response, "Free accounts")
        self.assertContains(response, "Revenue")

    def test_the_overview_survives_an_empty_database(self):
        Course.objects.all().delete()
        User.objects.filter(is_staff=False).delete()
        self.assertEqual(self.client.get(reverse("manage:overview")).status_code, 200)

    # -- courses and modules -----------------------------------------------

    def test_the_course_list_shows_modules_for_the_chosen_course(self):
        response = self.client.get(reverse("manage:courses"))
        self.assertContains(response, "Module 01")
        self.assertContains(response, "Module 03")

    def test_demo_data_loads_into_an_empty_site(self):
        Course.objects.all().delete()
        response = self.client.get(reverse("manage:courses"))
        self.assertContains(response, "Load demo data")
        self.client.post(reverse("manage:load_demo_data"))
        self.assertTrue(Course.objects.filter(slug="foundations-of-music").exists())
        self.assertTrue(Faq.objects.exists())

    def test_demo_data_never_overwrites_an_existing_site(self):
        self.client.post(reverse("manage:load_demo_data"))
        self.assertEqual(Module.objects.filter(course=self.course).count(), 3)
        self.assertNotContains(self.client.get(reverse("manage:courses")), "Load demo data")

    def test_a_student_cannot_load_demo_data(self):
        Course.objects.all().delete()
        self.client.force_login(self.student)
        self.client.post(reverse("manage:load_demo_data"))
        self.assertFalse(Course.objects.exists())

    def test_a_course_can_be_edited(self):
        response = self.client.post(
            reverse("manage:course_edit", kwargs={"slug": self.course.slug}),
            {
                "title": "Foundations of Music",
                "subtitle": "Part 1",
                "slug": self.course.slug,
                "summary": "A new summary.",
                "description": "Description.",
                "level": "Beginner",
                "price": "4000",
                "status": Course.Status.PUBLISHED,
                "trailer_label": "Watch the trailer",
                "trailer_duration": "2:10",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.course.refresh_from_db()
        self.assertEqual(self.course.summary, "A new summary.")
        self.assertEqual(int(self.course.price), 4000)

    def test_a_module_s_notes_and_access_can_be_changed(self):
        module = self.modules[1]
        response = self.client.post(
            reverse(
                "manage:module_edit",
                kwargs={"slug": self.course.slug, "module_slug": module.slug},
            ),
            {
                "number": module.number,
                "title": "Notation",
                "title_bn": "স্বরলিপি",
                "slug": module.slug,
                "summary": "The staff and clefs.",
                "notes_markdown": "## Notation\n\nThe staff has five lines.",
                "access": Module.Access.FREE,
                "status": Module.Status.PUBLISHED,
                "video_provider": "protected_file",
                "video_uid": "course/module-02.mp4",
                "video_duration_seconds": "902",
                "video_has_subtitles": "on",
            },
        )
        self.assertEqual(response.status_code, 302)
        module.refresh_from_db()
        self.assertEqual(module.title, "Notation")
        self.assertEqual(module.access, Module.Access.FREE)
        self.assertIn("five lines", module.notes_markdown)

    def test_a_new_module_can_be_created(self):
        response = self.client.post(
            reverse("manage:module_new", kwargs={"slug": self.course.slug}),
            {
                "number": "04",
                "title": "Meter",
                "title_bn": "",
                "slug": "meter",
                "summary": "Bars and beats.",
                "notes_markdown": "",
                "access": Module.Access.PAID,
                "status": Module.Status.DRAFT,
                "video_provider": "",
                "video_uid": "",
                "video_duration_seconds": "0",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(self.course.modules.filter(slug="meter").exists())

    def test_modules_can_be_reordered(self):
        order = [self.modules[2].pk, self.modules[0].pk, self.modules[1].pk]
        self.client.post(
            reverse("manage:module_reorder", kwargs={"slug": self.course.slug}),
            {"module": [str(pk) for pk in order]},
        )
        positions = {m.pk: m.position for m in self.course.modules.all()}
        self.assertEqual(positions[order[0]], 0)
        self.assertEqual(positions[order[2]], 2)

    # -- quizzes -----------------------------------------------------------

    def test_opening_the_quiz_editor_creates_a_starter_question(self):
        module = self.modules[0]
        url = reverse(
            "manage:quiz_edit", kwargs={"slug": self.course.slug, "module_slug": module.slug}
        )
        self.assertEqual(self.client.get(url).status_code, 302)
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        quiz = Quiz.objects.get(module=module)
        self.assertEqual(quiz.questions.count(), 1)
        self.assertEqual(quiz.questions.first().choices.count(), 4)

    def test_a_question_and_its_correct_answer_can_be_saved(self):
        module = self.modules[0]
        quiz = Quiz.objects.create(module=module)
        question = Question.objects.create(quiz=quiz, text="Old text", position=0)
        choices = [
            Choice.objects.create(question=question, text=f"Option {i}", position=i)
            for i in range(4)
        ]
        url = reverse(
            "manage:quiz_edit", kwargs={"slug": self.course.slug, "module_slug": module.slug}
        )
        payload = {
            "text": "How many beats in 4/4?",
            "explanation": "Four.",
            "notation": "",
            "audio": "",
            "correct": str(choices[2].pk),
            "choices-TOTAL_FORMS": "4",
            "choices-INITIAL_FORMS": "4",
            "choices-MIN_NUM_FORMS": "0",
            "choices-MAX_NUM_FORMS": "1000",
        }
        for index, choice in enumerate(choices):
            payload[f"choices-{index}-id"] = str(choice.pk)
            payload[f"choices-{index}-text"] = ["Two", "Three", "Four", "Eight"][index]
        response = self.client.post(url, payload)
        self.assertEqual(response.status_code, 302)

        question.refresh_from_db()
        self.assertEqual(question.text, "How many beats in 4/4?")
        self.assertEqual(question.explanation, "Four.")
        correct = question.choices.filter(is_correct=True)
        self.assertEqual(correct.count(), 1, "exactly one answer must be correct")
        self.assertEqual(correct.first().text, "Four")

    def test_quiz_rules_can_be_changed(self):
        module = self.modules[0]
        Quiz.objects.create(module=module, require_perfect_score=True)
        self.client.post(
            reverse(
                "manage:quiz_settings",
                kwargs={"slug": self.course.slug, "module_slug": module.slug},
            ),
            {"title": "Module 1 quiz", "allow_unlimited_retries": "on"},
        )
        quiz = Quiz.objects.get(module=module)
        self.assertFalse(quiz.require_perfect_score)
        self.assertTrue(quiz.allow_unlimited_retries)

    def test_a_question_can_be_added(self):
        module = self.modules[0]
        quiz = Quiz.objects.create(module=module)
        self.client.post(
            reverse(
                "manage:question_add",
                kwargs={"slug": self.course.slug, "module_slug": module.slug},
            )
        )
        self.assertEqual(quiz.questions.count(), 1)
        self.assertEqual(quiz.questions.first().choices.count(), 4)

    # -- students ----------------------------------------------------------

    def test_students_can_be_searched(self):
        response = self.client.get(reverse("manage:students"), {"q": "rafiq"})
        self.assertContains(response, "Rafiq Ahmed")
        response = self.client.get(reverse("manage:students"), {"q": "nobody"})
        self.assertContains(response, "No students match")

    def test_access_can_be_suspended_and_restored(self):
        url = reverse("manage:student_access", kwargs={"pk": self.student.pk})
        self.client.post(url)
        self.student.refresh_from_db()
        self.assertFalse(self.student.access_enabled)
        self.client.post(url)
        self.student.refresh_from_db()
        self.assertTrue(self.student.access_enabled)

    def test_access_can_be_granted_without_a_payment(self):
        self.client.post(
            reverse("manage:student_grant", kwargs={"pk": self.student.pk}),
            {"course": self.course.slug},
        )
        enrollment = Enrollment.objects.get(student=self.student, course=self.course)
        self.assertTrue(enrollment.is_active)
        self.assertTrue(enrollment.granted_manually)

    def test_the_student_list_does_not_include_staff(self):
        response = self.client.get(reverse("manage:students"))
        self.assertNotContains(response, "tanveer@example.com")

    # -- site content ------------------------------------------------------

    def test_a_faq_can_be_added(self):
        self.client.post(
            reverse("manage:faq_create"),
            {"question": "Is there a certificate?", "answer": "Not yet.", "position": "0",
             "is_published": "on"},
        )
        self.assertTrue(Faq.objects.filter(question="Is there a certificate?").exists())

    def test_a_legal_page_can_be_edited(self):
        page = LegalPage.objects.create(
            slug="terms", title="Terms & Conditions", body_markdown="Old text."
        )
        self.client.post(
            reverse("manage:legal_edit", kwargs={"slug": page.slug}),
            {
                "slug": page.slug,
                "title": "Terms & Conditions",
                "body_markdown": "## Terms\n\nNew text.",
                "meta_description": "Our terms.",
                "is_published": "on",
            },
        )
        page.refresh_from_db()
        self.assertIn("New text.", page.body_markdown)

    def test_a_contact_message_can_be_marked_handled(self):
        message = ContactMessage.objects.create(
            name="Nusrat", email="nusrat@example.com", message="Question."
        )
        self.client.post(reverse("manage:message_handled", kwargs={"pk": message.pk}))
        message.refresh_from_db()
        self.assertTrue(message.is_handled)


@override_settings(PROTECTED_MEDIA_ROOT=Path(tempfile.mkdtemp()))
class AssetUploadTests(TestCase):
    def setUp(self):
        self.course, self.modules = make_course()
        self.staff = User.objects.create_user(
            email="tanveer@example.com", password=PASSWORD, is_staff=True
        )
        self.client.force_login(self.staff)
        self.url = reverse(
            "manage:asset_upload",
            kwargs={"slug": self.course.slug, "module_slug": self.modules[0].slug},
        )

    def tearDown(self):
        from django.conf import settings

        shutil.rmtree(settings.PROTECTED_MEDIA_ROOT, ignore_errors=True)

    def test_an_audio_file_can_be_uploaded(self):
        self.client.post(
            self.url,
            {
                "asset-kind": MediaAsset.Kind.AUDIO,
                "asset-title": "Example 4.1",
                "asset-file": SimpleUploadedFile("example.mp3", b"ID3 fake"),
                "asset-duration_seconds": "45",
            },
        )
        asset = MediaAsset.objects.get()
        self.assertEqual(asset.kind, MediaAsset.Kind.AUDIO)
        self.assertEqual(asset.duration_seconds, 45)

    def test_a_notation_image_without_alt_text_is_refused(self):
        response = self.client.post(
            self.url,
            {
                "asset-kind": MediaAsset.Kind.NOTATION,
                "asset-title": "Figure 4.1",
                "asset-file": SimpleUploadedFile("figure.svg", b"<svg></svg>"),
                "asset-alt_text": "",
            },
            follow=True,
        )
        self.assertEqual(MediaAsset.objects.count(), 0)
        self.assertContains(response, "need alt text")

    def test_an_asset_can_be_deleted(self):
        asset = MediaAsset.objects.create(
            module=self.modules[0],
            kind=MediaAsset.Kind.DOWNLOAD,
            title="Worksheet",
            file=SimpleUploadedFile("w.pdf", b"%PDF"),
        )
        self.client.post(reverse("manage:asset_delete", kwargs={"pk": asset.pk}))
        self.assertEqual(MediaAsset.objects.count(), 0)

    def test_a_student_cannot_upload(self):
        student = User.objects.create_user(email="rafiq@example.com", password=PASSWORD)
        self.client.force_login(student)
        response = self.client.post(
            self.url,
            {
                "asset-kind": MediaAsset.Kind.AUDIO,
                "asset-title": "Sneaky",
                "asset-file": SimpleUploadedFile("x.mp3", b"ID3"),
            },
        )
        self.assertEqual(response.status_code, 404)
        self.assertEqual(MediaAsset.objects.count(), 0)

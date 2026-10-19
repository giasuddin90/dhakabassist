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
    LibraryFile,
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

    PATHS = ("overview", "courses", "library", "quizzes", "students", "orders", "content")

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
class ModuleEditorLibraryTests(TestCase):
    """The module editor takes its files from the media library, not uploads."""

    def setUp(self):
        self.course, self.modules = make_course()
        self.staff = User.objects.create_user(
            email="tanveer@example.com", password=PASSWORD, is_staff=True
        )
        self.client.force_login(self.staff)
        self.module = self.modules[1]
        self.url = reverse(
            "manage:module_edit",
            kwargs={"slug": self.course.slug, "module_slug": self.module.slug},
        )

    def tearDown(self):
        from django.conf import settings

        shutil.rmtree(settings.PROTECTED_MEDIA_ROOT, ignore_errors=True)

    def test_the_editor_has_no_file_uploads(self):
        response = self.client.get(self.url)
        self.assertNotContains(response, 'type="file"')
        self.assertNotContains(response, "multipart/form-data")

    def test_library_files_are_offered_with_their_markdown(self):
        item = LibraryFile.objects.create(
            title="Worksheet 1",
            purpose=LibraryFile.Purpose.DOWNLOAD,
            file=SimpleUploadedFile("worksheet-1.pdf", b"%PDF"),
        )
        response = self.client.get(self.url)
        self.assertContains(response, f'data-insert="{item.markdown}"')
        self.assertContains(response, 'data-picker-purpose="download"')

    def test_files_linked_from_the_notes_or_quiz_are_listed(self):
        in_notes = LibraryFile.objects.create(
            title="Scale", file=SimpleUploadedFile("scale.mp3", b"ID3")
        )
        in_quiz = LibraryFile.objects.create(
            title="Clip", file=SimpleUploadedFile("clip.mp3", b"ID3")
        )
        LibraryFile.objects.create(title="Unused", file=SimpleUploadedFile("u.mp3", b"ID3"))
        self.module.notes_markdown = f"Listen.\n\n{in_notes.markdown}"
        self.module.save(update_fields=["notes_markdown"])
        quiz = Quiz.objects.create(module=self.module)
        Question.objects.create(quiz=quiz, text=f"Which? {in_quiz.markdown}")

        response = self.client.get(self.url)
        linked = [item.title for item in response.context["linked_files"]]
        self.assertEqual(sorted(linked), ["Clip", "Scale"])

    def test_a_new_module_lists_no_linked_files(self):
        LibraryFile.objects.create(title="Scale", file=SimpleUploadedFile("s.mp3", b"ID3"))
        response = self.client.get(reverse("manage:module_new", kwargs={"slug": self.course.slug}))
        self.assertEqual(response.context["linked_files"], [])
        self.assertContains(response, "Scale")


@override_settings(PROTECTED_MEDIA_ROOT=Path(tempfile.mkdtemp()))
class LibraryTests(TestCase):
    def setUp(self):
        self.course, self.modules = make_course()
        self.staff = User.objects.create_user(
            email="tanveer@example.com", password=PASSWORD, is_staff=True
        )
        self.client.force_login(self.staff)
        self.url = reverse("manage:library_upload")

    def tearDown(self):
        from django.conf import settings

        shutil.rmtree(settings.PROTECTED_MEDIA_ROOT, ignore_errors=True)

    def test_several_files_upload_into_one_folder(self):
        response = self.client.post(
            self.url,
            {
                "purpose": LibraryFile.Purpose.LESSON,
                "folder": "  Lesson   material ",
                "files": [
                    SimpleUploadedFile("c-major_scale.mp3", b"ID3"),
                    SimpleUploadedFile("treble-clef.svg", b"<svg></svg>"),
                ],
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            sorted(LibraryFile.objects.values_list("title", "folder")),
            [("C major scale", "Lesson material"), ("Treble clef", "Lesson material")],
        )

    def test_uploads_are_filed_under_the_chosen_material(self):
        self.client.post(
            self.url,
            {
                "purpose": LibraryFile.Purpose.DOWNLOAD,
                "folder": "Module 3",
                "files": [
                    SimpleUploadedFile("worksheet.pdf", b"%PDF"),
                    SimpleUploadedFile("groove.gp5", b"FICHIER"),
                    SimpleUploadedFile("notes.docx", b"PK"),
                ],
            },
        )
        self.assertEqual(
            sorted(LibraryFile.objects.values_list("purpose", flat=True)),
            [LibraryFile.Purpose.DOWNLOAD] * 3,
        )

    def test_a_material_must_be_chosen(self):
        self.client.post(
            self.url,
            {"folder": "Module 3", "files": [SimpleUploadedFile("a.pdf", b"%PDF")]},
        )
        self.assertEqual(LibraryFile.objects.count(), 0)

    def test_a_material_tab_narrows_the_list(self):
        LibraryFile.objects.create(
            title="Quiz clip",
            purpose=LibraryFile.Purpose.QUIZ,
            file=SimpleUploadedFile("a.mp3", b"ID3"),
        )
        LibraryFile.objects.create(
            title="Lesson clip", file=SimpleUploadedFile("b.mp3", b"ID3")
        )
        response = self.client.get(reverse("manage:library"), {"purpose": "quiz"})
        self.assertContains(response, "Quiz clip")
        self.assertNotContains(response, "Lesson clip")
        self.assertContains(response, f"{self.url}?purpose=quiz")

    def test_the_upload_page_starts_on_the_material_being_viewed(self):
        response = self.client.get(self.url, {"purpose": "download"})
        self.assertContains(response, 'value="download" id="id_purpose_2" required checked')

    def test_an_unsupported_file_type_is_refused(self):
        self.client.post(
            self.url,
            {"folder": "Lesson material", "files": [SimpleUploadedFile("run.exe", b"MZ")]},
        )
        self.assertEqual(LibraryFile.objects.count(), 0)

    def test_the_page_shows_the_markdown_and_where_a_file_is_used(self):
        item = LibraryFile.objects.create(
            title="Stave", file=SimpleUploadedFile("stave.svg", b"<svg></svg>")
        )
        self.modules[0].notes_markdown = item.markdown
        self.modules[0].save(update_fields=["notes_markdown"])
        response = self.client.get(reverse("manage:library"))
        self.assertContains(response, item.get_absolute_url())
        self.assertContains(response, "Module 01")

    def test_a_file_used_only_in_a_quiz_lists_its_module(self):
        item = LibraryFile.objects.create(
            title="Clip", file=SimpleUploadedFile("clip.mp3", b"ID3")
        )
        quiz = Quiz.objects.create(module=self.modules[1])
        Question.objects.create(quiz=quiz, text=f"Listen. {item.markdown}")
        response = self.client.get(reverse("manage:library"))
        self.assertContains(response, "Module 02")
        self.assertNotContains(response, "Not linked from any lesson or quiz yet")

    def test_a_folder_filter_narrows_the_list(self):
        LibraryFile.objects.create(
            title="Kept", folder="Module 3", file=SimpleUploadedFile("a.mp3", b"ID3")
        )
        LibraryFile.objects.create(
            title="Hidden", folder="Module 4", file=SimpleUploadedFile("b.mp3", b"ID3")
        )
        response = self.client.get(reverse("manage:library"), {"folder": "Module 3"})
        self.assertContains(response, "Kept")
        self.assertNotContains(response, "Hidden")

    def test_a_file_can_be_removed(self):
        item = LibraryFile.objects.create(
            title="Old", file=SimpleUploadedFile("old.mp3", b"ID3")
        )
        self.client.post(reverse("manage:library_delete", kwargs={"pk": item.pk}))
        self.assertEqual(LibraryFile.objects.count(), 0)

    def test_a_student_cannot_upload(self):
        student = User.objects.create_user(email="rafiq@example.com", password=PASSWORD)
        self.client.force_login(student)
        response = self.client.post(
            self.url,
            {"purpose": "lesson", "folder": "x", "files": [SimpleUploadedFile("x.mp3", b"ID3")]},
        )
        self.assertEqual(response.status_code, 404)
        self.assertEqual(LibraryFile.objects.count(), 0)

    def test_the_upload_page_has_its_own_form(self):
        response = self.client.get(self.url, {"folder": "Module 3"})
        self.assertContains(response, 'enctype="multipart/form-data"')
        self.assertContains(response, 'value="Module 3"')

    def test_a_refused_upload_stays_on_the_form_with_the_error(self):
        response = self.client.post(
            self.url,
            {"folder": "Lesson material", "files": [SimpleUploadedFile("run.exe", b"MZ")]},
        )
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "manage_panel/library_upload.html")
        self.assertContains(response, "field__error")

    def test_a_type_filter_shows_only_that_kind(self):
        LibraryFile.objects.create(title="Scale clip", file=SimpleUploadedFile("a.mp3", b"ID3"))
        LibraryFile.objects.create(title="Stave chart", file=SimpleUploadedFile("b.svg", b"<svg/>"))
        response = self.client.get(reverse("manage:library"), {"kind": "audio"})
        self.assertContains(response, "Scale clip")
        self.assertNotContains(response, "Stave chart")

    def test_a_status_filter_shows_only_unlinked_files(self):
        used = LibraryFile.objects.create(
            title="Linked clip", file=SimpleUploadedFile("a.mp3", b"ID3")
        )
        LibraryFile.objects.create(title="Spare clip", file=SimpleUploadedFile("b.mp3", b"ID3"))
        self.modules[0].notes_markdown = used.markdown
        self.modules[0].save(update_fields=["notes_markdown"])
        response = self.client.get(reverse("manage:library"), {"usage": "unused"})
        self.assertContains(response, "Spare clip")
        self.assertNotContains(response, "Linked clip")

    def test_the_list_is_paginated_and_page_links_keep_the_filters(self):
        for number in range(14):
            LibraryFile.objects.create(
                title=f"Clip {number:02}", file=SimpleUploadedFile(f"c{number}.mp3", b"ID3")
            )
        url = reverse("manage:library")
        first = self.client.get(url, {"kind": "audio", "sort": "title"})
        self.assertContains(first, "Clip 11")
        self.assertNotContains(first, "Clip 12")
        self.assertContains(first, "?kind=audio&amp;sort=title&amp;page=2")
        second = self.client.get(url, {"kind": "audio", "sort": "title", "page": 2})
        self.assertContains(second, "Clip 13")
        self.assertNotContains(second, "Clip 11")

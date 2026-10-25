"""Access rules, progression, the quiz and course media.

These are the behaviours that keep paid material paid, so they are tested
directly rather than through the UI.
"""

import base64
import functools
import shutil
import tempfile
import time
from pathlib import Path

import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from core.testing import EnglishPagesMixin
from courses.access import CourseAccess
from courses.markup import render_inline, render_notes, split_audio
from courses.models import (
    Choice,
    Course,
    Enrollment,
    LibraryFile,
    MediaAsset,
    Module,
    ModuleProgress,
    Question,
    Quiz,
    QuizAttempt,
)
from courses.video import playback, trailer_embed_url

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
    modules = []
    for index in range(3):
        number = f"{index + 1:02d}"
        modules.append(
            Module.objects.create(
                course=course,
                number=number,
                slug=f"module-{number}",
                title=f"Module {number}",
                summary="Summary.",
                notes_markdown="## Notes\n\nText.",
                access=Module.Access.FREE if index == 0 else Module.Access.PAID,
                status=Module.Status.PUBLISHED,
                video_duration_seconds=600,
            )
        )
    return course, modules


def make_quiz(module, correct_index=2):
    quiz = Quiz.objects.create(module=module, require_perfect_score=True)
    question = Question.objects.create(
        quiz=quiz, text="How many beats in 4/4?", position=0, explanation="Four."
    )
    for index, text in enumerate(["Two", "Three", "Four", "Eight"]):
        Choice.objects.create(
            question=question, text=text, position=index, is_correct=index == correct_index
        )
    return quiz, question


class AccessRuleTests(TestCase):
    def setUp(self):
        self.course, self.modules = make_course()
        self.student = User.objects.create_user(
            email="rafiq@example.com", password=PASSWORD, full_name="Rafiq Ahmed"
        )

    def test_anonymous_visitors_unlock_nothing(self):
        access = CourseAccess(self.client.request().wsgi_request.user, self.course)
        self.assertFalse(any(s.is_unlocked for s in access.module_states()))

    def test_a_registered_account_unlocks_only_the_free_module(self):
        access = CourseAccess(self.student, self.course)
        states = access.module_states()
        self.assertTrue(states[0].is_unlocked)
        self.assertFalse(states[1].is_unlocked)
        self.assertFalse(states[2].is_unlocked)

    def test_enrolment_alone_does_not_skip_the_progression(self):
        """Paying opens the course, but each module still waits for the one before.

        The brief is explicit: "a module remains locked until the student
        completes its quiz with 100% accuracy".
        """
        Enrollment.objects.create(student=self.student, course=self.course)
        states = CourseAccess(self.student, self.course).module_states()
        self.assertTrue(states[0].is_unlocked)
        self.assertFalse(states[1].is_unlocked, "module 1 is not finished yet")
        self.assertFalse(states[2].is_unlocked)

    def test_finishing_the_free_module_opens_the_next_one_for_an_enrolled_student(self):
        Enrollment.objects.create(student=self.student, course=self.course)
        ModuleProgress.objects.create(
            student=self.student, module=self.modules[0]
        ).mark_complete()
        states = CourseAccess(self.student, self.course).module_states()
        self.assertTrue(states[1].is_unlocked)
        self.assertFalse(states[2].is_unlocked)

    def test_finishing_the_free_module_without_paying_opens_nothing(self):
        ModuleProgress.objects.create(
            student=self.student, module=self.modules[0]
        ).mark_complete()
        states = CourseAccess(self.student, self.course).module_states()
        self.assertFalse(states[1].is_unlocked)

    def test_finishing_a_module_unlocks_the_next_one(self):
        Enrollment.objects.create(student=self.student, course=self.course)
        for module in self.modules[:2]:
            ModuleProgress.objects.create(student=self.student, module=module).mark_complete()
        states = CourseAccess(self.student, self.course).module_states()
        self.assertTrue(all(s.is_unlocked for s in states))

    def test_suspending_access_locks_paid_modules_immediately(self):
        Enrollment.objects.create(student=self.student, course=self.course)
        self.student.access_enabled = False
        self.student.save(update_fields=["access_enabled"])
        access = CourseAccess(self.student, self.course)
        self.assertFalse(access.is_enrolled)
        self.assertFalse(access.module_states()[1].is_unlocked)

    def test_an_inactive_enrolment_does_not_grant_access(self):
        Enrollment.objects.create(student=self.student, course=self.course, is_active=False)
        self.assertFalse(CourseAccess(self.student, self.course).is_enrolled)

    def test_a_superuser_previews_every_module_without_enrolling(self):
        owner = User.objects.create_superuser(email="owner@example.com", password=PASSWORD)
        access = CourseAccess(owner, self.course)
        self.assertTrue(access.is_previewing)
        self.assertTrue(access.is_enrolled)
        self.assertTrue(all(s.is_unlocked for s in access.module_states()))
        self.assertTrue(all(access.can_view(m) for m in self.modules))

    def test_a_superuser_preview_opens_a_later_module_page_and_its_media(self):
        owner = User.objects.create_superuser(email="owner@example.com", password=PASSWORD)
        self.client.force_login(owner)
        response = self.client.get(self.modules[2].get_absolute_url())
        self.assertTemplateUsed(response, "courses/lesson.html")

    def test_staff_who_is_not_a_superuser_still_follows_the_progression(self):
        staff = User.objects.create_user(
            email="staff@example.com", password=PASSWORD, is_staff=True
        )
        access = CourseAccess(staff, self.course)
        self.assertFalse(access.is_previewing)
        self.assertFalse(access.module_states()[1].is_unlocked)

    def test_an_inactive_superuser_previews_nothing(self):
        owner = User.objects.create_superuser(email="owner@example.com", password=PASSWORD)
        owner.is_active = False
        self.assertFalse(CourseAccess(owner, self.course).is_previewing)

    def test_draft_modules_are_invisible_to_students(self):
        self.modules[1].status = Module.Status.DRAFT
        self.modules[1].save(update_fields=["status"])
        states = CourseAccess(self.student, self.course).module_states()
        self.assertEqual([s.module.number for s in states], ["01", "03"])

    def test_percent_complete_counts_published_modules(self):
        ModuleProgress.objects.create(student=self.student, module=self.modules[0]).mark_complete()
        access = CourseAccess(self.student, self.course)
        self.assertEqual(access.completed_count, 1)
        self.assertEqual(access.percent_complete, 33)


class LessonViewTests(TestCase):
    def setUp(self):
        self.course, self.modules = make_course()
        self.student = User.objects.create_user(email="rafiq@example.com", password=PASSWORD)
        self.client.force_login(self.student)

    def url(self, module):
        return reverse(
            "courses:lesson",
            kwargs={"slug": self.course.slug, "module_slug": module.slug},
        )

    def test_the_free_module_renders_its_notes(self):
        response = self.client.get(self.url(self.modules[0]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "<h2>Notes</h2>", html=False)

    def test_a_locked_module_shows_the_paywall_not_the_notes(self):
        response = self.client.get(self.url(self.modules[1]))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "courses/paywall.html")
        self.assertNotContains(response, "<h2>Notes</h2>", html=False)

    def test_lesson_pages_are_marked_noindex(self):
        response = self.client.get(self.url(self.modules[0]))
        self.assertContains(response, 'content="noindex, nofollow"')

    def test_signing_out_redirects_a_lesson_to_the_login_page(self):
        self.client.logout()
        response = self.client.get(self.url(self.modules[0]))
        self.assertRedirects(
            response, f"{reverse('accounts:login')}?next={self.url(self.modules[0])}"
        )

    def test_opening_a_lesson_records_progress(self):
        self.client.get(self.url(self.modules[0]))
        self.assertTrue(
            ModuleProgress.objects.filter(
                student=self.student, module=self.modules[0]
            ).exists()
        )

    def test_the_video_position_is_saved_and_bounded(self):
        response = self.client.post(
            reverse("courses:video_position", kwargs={"pk": self.modules[0].pk}),
            {"seconds": "-50"},
        )
        self.assertEqual(response.status_code, 200)
        progress = ModuleProgress.objects.get(student=self.student, module=self.modules[0])
        self.assertEqual(progress.video_position_seconds, 0)

    def test_watch_time_adds_up_across_reports_and_is_capped(self):
        url = reverse("courses:video_position", kwargs={"pk": self.modules[0].pk})
        self.client.post(url, {"seconds": "40", "watched": "15"})
        self.client.post(url, {"seconds": "55", "watched": "15"})
        self.client.post(url, {"seconds": "60", "watched": "99999"})
        self.client.post(url, {"seconds": "60", "watched": "nonsense"})
        progress = ModuleProgress.objects.get(student=self.student, module=self.modules[0])
        self.assertEqual(progress.video_position_seconds, 60)
        self.assertEqual(
            progress.watched_seconds, 30 + ModuleProgress.MAX_WATCHED_PER_REPORT
        )

    def test_the_position_endpoint_rejects_a_locked_module(self):
        response = self.client.post(
            reverse("courses:video_position", kwargs={"pk": self.modules[1].pk}),
            {"seconds": "30"},
        )
        self.assertEqual(response.status_code, 404)


class QuizTests(TestCase):
    def setUp(self):
        self.course, self.modules = make_course()
        self.module = self.modules[0]
        self.quiz, self.question = make_quiz(self.module)
        self.student = User.objects.create_user(email="rafiq@example.com", password=PASSWORD)
        self.client.force_login(self.student)
        self.kwargs = {"slug": self.course.slug, "module_slug": self.module.slug}

    def test_the_quiz_page_does_not_disclose_the_answer(self):
        response = self.client.get(reverse("courses:quiz", kwargs=self.kwargs))
        body = response.content.decode()
        self.assertIn("How many beats in 4/4?", body)
        self.assertNotIn("is_correct", body)
        self.assertNotIn("Correct answer", body)

    def test_a_wrong_pick_is_reported_and_counted(self):
        wrong = self.question.choices.get(position=0)
        response = self.client.post(
            reverse("courses:quiz_answer", kwargs=self.kwargs),
            {"question": self.question.pk, "choice": wrong.pk},
            HTTP_X_REQUESTED_WITH="fetch",
        )
        self.assertFalse(response.json()["correct"])
        self.assertEqual(QuizAttempt.objects.get().wrong_picks, 1)

    def test_a_right_pick_returns_the_explanation(self):
        right = self.question.choices.get(position=2)
        response = self.client.post(
            reverse("courses:quiz_answer", kwargs=self.kwargs),
            {"question": self.question.pk, "choice": right.pk},
            HTTP_X_REQUESTED_WITH="fetch",
        )
        data = response.json()
        self.assertTrue(data["correct"])
        self.assertEqual(data["explanation"], "<p>Four.</p>")

    def test_repeating_the_same_wrong_pick_is_not_counted_twice(self):
        wrong = self.question.choices.get(position=0)
        payload = {"question": self.question.pk, "choice": wrong.pk}
        for _ in range(3):
            self.client.post(reverse("courses:quiz_answer", kwargs=self.kwargs), payload)
        self.assertEqual(QuizAttempt.objects.get().wrong_picks, 1)

    def test_finishing_the_quiz_completes_the_module(self):
        right = self.question.choices.get(position=2)
        self.client.post(
            reverse("courses:quiz_answer", kwargs=self.kwargs),
            {"question": self.question.pk, "choice": right.pk},
        )
        self.client.post(reverse("courses:quiz_advance", kwargs=self.kwargs))
        progress = ModuleProgress.objects.get(student=self.student, module=self.module)
        self.assertIsNotNone(progress.completed_at)
        self.assertEqual(QuizAttempt.objects.get().score_percent, 100)

    def test_the_quiz_cannot_be_finished_with_a_question_unsolved(self):
        self.client.get(reverse("courses:quiz", kwargs=self.kwargs))
        self.client.post(reverse("courses:quiz_advance", kwargs=self.kwargs))
        self.assertFalse(
            ModuleProgress.objects.filter(
                student=self.student, module=self.module, completed_at__isnull=False
            ).exists()
        )

    def test_the_correct_answer_is_never_in_the_page_source(self):
        """A student reading the HTML must not be able to see the answer."""
        response = self.client.get(reverse("courses:quiz", kwargs=self.kwargs))
        body = response.content.decode()
        # All four options appear; nothing distinguishes the right one.
        for text in ("Two", "Three", "Four", "Eight"):
            self.assertIn(text, body)
        self.assertNotIn("Four.", body, "the explanation leaks the answer")

    def test_a_wrong_first_pick_lowers_the_score_but_still_passes(self):
        wrong = self.question.choices.get(position=0)
        right = self.question.choices.get(position=2)
        for choice in (wrong, right):
            self.client.post(
                reverse("courses:quiz_answer", kwargs=self.kwargs),
                {"question": self.question.pk, "choice": choice.pk},
            )
        self.client.post(reverse("courses:quiz_advance", kwargs=self.kwargs))
        attempt = QuizAttempt.objects.get()
        self.assertEqual(attempt.score_percent, 0)
        self.assertIsNotNone(attempt.completed_at)

    def test_answering_a_locked_module_is_rejected(self):
        locked_quiz, locked_question = make_quiz(self.modules[1])
        response = self.client.post(
            reverse(
                "courses:quiz_answer",
                kwargs={"slug": self.course.slug, "module_slug": self.modules[1].slug},
            ),
            {"question": locked_question.pk, "choice": locked_question.choices.first().pk},
        )
        self.assertEqual(response.status_code, 404)

    def test_restarting_creates_a_fresh_attempt(self):
        self.client.get(reverse("courses:quiz", kwargs=self.kwargs))
        self.client.post(reverse("courses:quiz_restart", kwargs=self.kwargs))
        self.assertEqual(QuizAttempt.objects.count(), 2)


class MarkCompleteTests(EnglishPagesMixin, TestCase):
    """Modules without a quiz are finished by the student, not by a quiz."""

    def setUp(self):
        self.course, self.modules = make_course()
        self.student = User.objects.create_user(email="rafiq@example.com", password=PASSWORD)
        Enrollment.objects.create(student=self.student, course=self.course)
        self.client.force_login(self.student)

    def complete_url(self, module):
        return reverse(
            "courses:module_complete",
            kwargs={"slug": self.course.slug, "module_slug": module.slug},
        )

    def is_complete(self, module):
        return ModuleProgress.objects.filter(
            student=self.student, module=module, completed_at__isnull=False
        ).exists()

    def test_marking_a_module_without_a_quiz_opens_the_next_one(self):
        response = self.client.post(self.complete_url(self.modules[0]))
        self.assertRedirects(response, self.modules[1].get_absolute_url())
        progress = ModuleProgress.objects.get(student=self.student, module=self.modules[0])
        self.assertIsNotNone(progress.completed_at)
        self.assertIsNone(progress.quiz_passed_at, "no quiz was passed")
        states = CourseAccess(self.student, self.course).module_states()
        self.assertTrue(states[1].is_unlocked)
        self.assertFalse(states[2].is_unlocked)

    def test_the_last_module_returns_to_its_lesson(self):
        for module in self.modules[:2]:
            ModuleProgress.objects.create(student=self.student, module=module).mark_complete()
        response = self.client.post(self.complete_url(self.modules[2]))
        self.assertRedirects(response, self.modules[2].get_absolute_url())

    def test_a_module_with_a_quiz_cannot_be_marked_complete(self):
        make_quiz(self.modules[0])
        response = self.client.post(self.complete_url(self.modules[0]))
        self.assertEqual(response.status_code, 404)
        self.assertFalse(self.is_complete(self.modules[0]))

    def test_a_quiz_without_questions_does_not_block_the_module(self):
        Quiz.objects.create(module=self.modules[0])
        self.client.post(self.complete_url(self.modules[0]))
        self.assertTrue(self.is_complete(self.modules[0]))

    def test_a_locked_module_cannot_be_marked_complete(self):
        response = self.client.post(self.complete_url(self.modules[1]))
        self.assertEqual(response.status_code, 404)
        self.assertFalse(self.is_complete(self.modules[1]))

    def test_only_a_post_completes_a_module(self):
        response = self.client.get(self.complete_url(self.modules[0]))
        self.assertEqual(response.status_code, 405)
        self.assertFalse(self.is_complete(self.modules[0]))

    def test_an_anonymous_visitor_is_sent_to_the_login_page(self):
        self.client.logout()
        url = self.complete_url(self.modules[0])
        response = self.client.post(url)
        self.assertRedirects(response, f"{reverse('accounts:login')}?next={url}")

    def test_the_lesson_offers_the_button_only_without_a_quiz(self):
        response = self.client.get(self.modules[0].get_absolute_url())
        self.assertContains(response, self.complete_url(self.modules[0]))
        self.assertContains(response, "Mark as complete")
        make_quiz(self.modules[0])
        response = self.client.get(self.modules[0].get_absolute_url())
        self.assertNotContains(response, "Mark as complete")
        self.assertContains(response, "Start quiz")

    def test_a_completed_module_shows_no_button(self):
        self.client.post(self.complete_url(self.modules[0]))
        response = self.client.get(self.modules[0].get_absolute_url())
        self.assertNotContains(response, "Mark as complete")
        self.assertContains(response, "Module 1 complete")


@override_settings(MEDIA_ROOT=Path(tempfile.mkdtemp()))
class CourseMediaTests(TestCase):
    def setUp(self):
        self.course, self.modules = make_course()
        self.student = User.objects.create_user(email="rafiq@example.com", password=PASSWORD)
        self.other = User.objects.create_user(email="other@example.com", password=PASSWORD)

    def tearDown(self):
        shutil.rmtree(settings.MEDIA_ROOT, ignore_errors=True)

    def asset(self, module):
        return MediaAsset.objects.create(
            module=module,
            kind=MediaAsset.Kind.DOWNLOAD,
            title="Worksheet 1",
            file=SimpleUploadedFile("worksheet.pdf", b"%PDF-1.4 fake"),
        )

    def test_a_signed_in_student_can_fetch_a_free_module_asset(self):
        asset = self.asset(self.modules[0])
        self.client.force_login(self.student)
        response = self.client.get(asset.get_absolute_url())
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["X-Robots-Tag"], "noindex, nofollow")

    def test_a_locked_module_asset_is_not_served(self):
        asset = self.asset(self.modules[1])
        self.client.force_login(self.student)
        self.assertEqual(self.client.get(asset.get_absolute_url()).status_code, 404)

    def test_an_anonymous_visitor_is_sent_to_the_login_page(self):
        asset = self.asset(self.modules[0])
        response = self.client.get(asset.get_absolute_url())
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("accounts:login"), response["Location"])

    def test_files_are_stored_in_media_but_not_served_from_it(self):
        asset = self.asset(self.modules[0])
        self.assertTrue((Path(settings.MEDIA_ROOT) / asset.file.name).is_file())
        self.client.force_login(self.student)
        self.assertEqual(self.client.get(asset.file.url).status_code, 404)

    def test_a_locked_module_video_is_not_served(self):
        self.modules[1].video_uid = "foundations/module-02.mp4"
        self.modules[1].save(update_fields=["video_uid_bn"])
        self.client.force_login(self.student)
        url = reverse("courses:video", kwargs={"pk": self.modules[1].pk})
        self.assertEqual(self.client.get(url).status_code, 404)


class MarkupTests(TestCase):
    def test_headings_and_emphasis_survive(self):
        html = render_notes("## Title\n\nSome **bold** text.")
        self.assertIn("<h2>Title</h2>", html)
        self.assertIn("<strong>bold</strong>", html)

    def test_script_tags_are_stripped(self):
        html = render_notes("Hello <script>alert(1)</script> world")
        self.assertNotIn("<script", html)
        self.assertNotIn("alert(1)", html)

    def test_event_handlers_are_stripped(self):
        html = render_notes('<img src="x.png" alt="x" onerror="alert(1)">')
        self.assertNotIn("onerror", html)

    def test_javascript_urls_are_rejected(self):
        html = render_notes("[click](javascript:alert(1))")
        self.assertNotIn("javascript:", html)

    def test_images_are_lazy_loaded(self):
        html = render_notes("![Figure 4.1](figure.svg)")
        self.assertIn('loading="lazy"', html)

    def test_an_image_link_to_audio_becomes_a_player(self):
        html = render_notes("![C major scale](/library/abc/c-major.mp3)")
        self.assertIn('<audio controls preload="none" src="/library/abc/c-major.mp3">', html)
        self.assertNotIn("<img", html)

    def test_an_image_link_to_svg_stays_an_image(self):
        html = render_notes("![The stave](/library/abc/stave.svg)")
        self.assertIn('src="/library/abc/stave.svg"', html)
        self.assertIn("<img", html)

    def test_empty_notes_render_as_nothing(self):
        self.assertEqual(render_notes(""), "")

    def test_inline_markdown_drops_the_paragraph(self):
        self.assertEqual(render_inline("A **major** third"), "A <strong>major</strong> third")

    def test_inline_markdown_keeps_several_paragraphs(self):
        self.assertIn("<p>two</p>", render_inline("one\n\ntwo"))

    def test_audio_players_split_from_the_text(self):
        text, audio = split_audio(render_inline("Listen ![Clip](/library/a/clip.mp3)"))
        self.assertEqual(text, "Listen")
        self.assertIn('<audio controls preload="none" src="/library/a/clip.mp3">', audio)


class CoursePageTests(EnglishPagesMixin, TestCase):
    def setUp(self):
        self.course, self.modules = make_course()

    def test_the_curriculum_lists_every_published_module(self):
        response = self.client.get(self.course.get_absolute_url())
        for module in self.modules:
            self.assertContains(response, module.title)

    def test_a_draft_course_is_not_public(self):
        self.course.status = Course.Status.DRAFT
        self.course.save(update_fields=["status"])
        self.assertEqual(self.client.get(self.course.get_absolute_url()).status_code, 404)

    def test_total_runtime_is_summed_from_the_modules(self):
        self.assertEqual(self.course.total_runtime, "30 min")
        self.assertEqual(self.course.iso_duration, "PT30M")

    def test_every_free_module_is_named_as_a_free_preview(self):
        for module in self.modules[1:]:
            module.access = Module.Access.FREE
            module.save(update_fields=["access"])
        response = self.client.get(self.course.get_absolute_url())
        self.assertContains(response, "Module 1, 2 &amp; 3")
        self.assertContains(response, "Module 1, 2 &amp; 3 are free.")

    def test_the_dashboard_hides_courses_with_nothing_unlocked(self):
        student = User.objects.create_user(email="rafiq@example.com", password=PASSWORD)
        self.modules[0].access = Module.Access.PAID
        self.modules[0].save(update_fields=["access"])
        self.client.force_login(student)
        response = self.client.get(reverse("courses:dashboard"))
        self.assertContains(response, "You have not enrolled yet")

    def test_the_trailer_is_not_shown_on_the_course_page(self):
        self.course.trailer_url_en = "https://youtu.be/dQw4w9WgXcQ"
        self.course.save(update_fields=["trailer_url_en"])
        response = self.client.get(self.course.get_absolute_url())
        self.assertNotContains(response, "<iframe")

    @override_settings(SITE={**settings.SITE, "course_banner_placeholder": "img/logo-full.svg"})
    def test_without_a_banner_the_placeholder_from_settings_shows(self):
        response = self.client.get(self.course.get_absolute_url())
        self.assertContains(response, 'src="/static/img/logo-full.svg"')


@override_settings(MEDIA_ROOT=Path(tempfile.mkdtemp()))
class CourseBannerTests(EnglishPagesMixin, TestCase):
    def setUp(self):
        self.course, _ = make_course()
        self.course.banner.save("banner.png", ContentFile(b"banner bytes"))

    def tearDown(self):
        shutil.rmtree(settings.MEDIA_ROOT, ignore_errors=True)

    def test_the_banner_shows_on_the_course_page_and_when_shared(self):
        response = self.client.get(self.course.get_absolute_url())
        self.assertContains(response, f'src="{self.course.banner_url}"')
        self.assertContains(response, f'alt="{self.course.title}"')
        self.assertContains(response, f'content="{settings.SITE_BASE_URL}{self.course.banner_url}"')

    def test_the_banner_is_stored_in_the_course_s_media_folder(self):
        self.assertTrue(self.course.banner.name.startswith("courses/foundations-of-music/banner/"))

    def test_a_published_course_s_banner_is_public(self):
        response = self.client.get(reverse("courses:banner", kwargs={"slug": self.course.slug}))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(b"".join(response.streaming_content), b"banner bytes")
        self.assertIn("public", response["Cache-Control"])

    def test_a_draft_course_s_banner_is_for_staff_only(self):
        Course.objects.filter(pk=self.course.pk).update(status=Course.Status.DRAFT)
        url = reverse("courses:banner", kwargs={"slug": self.course.slug})
        self.assertEqual(self.client.get(url).status_code, 404)
        staff = User.objects.create_user(
            email="staff@example.com", password=PASSWORD, is_staff=True
        )
        self.client.force_login(staff)
        self.assertEqual(self.client.get(url).status_code, 200)

    def test_no_banner_is_a_404(self):
        Course.objects.filter(pk=self.course.pk).update(banner="")
        url = reverse("courses:banner", kwargs={"slug": self.course.slug})
        self.assertEqual(self.client.get(url).status_code, 404)


CF_UID = "31c9291ab41fac05471db4e73aa11717"


class TrailerLinkTests(TestCase):
    def test_youtube_links_become_privacy_enhanced_embeds(self):
        embed = "https://www.youtube-nocookie.com/embed/dQw4w9WgXcQ?rel=0"
        for url in (
            "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            "https://youtube.com/watch?feature=share&v=dQw4w9WgXcQ",
            "https://m.youtube.com/watch?v=dQw4w9WgXcQ&t=42s",
            "https://youtu.be/dQw4w9WgXcQ?si=abc",
            "https://www.youtube.com/embed/dQw4w9WgXcQ",
            "https://www.youtube.com/shorts/dQw4w9WgXcQ",
            "https://www.youtube-nocookie.com/embed/dQw4w9WgXcQ",
        ):
            with self.subTest(url=url):
                self.assertEqual(trailer_embed_url(url), embed)

    def test_cloudflare_links_become_iframe_embeds(self):
        cases = {
            f"https://customer-abc123.cloudflarestream.com/{CF_UID}/watch":
                f"https://customer-abc123.cloudflarestream.com/{CF_UID}/iframe",
            f"https://customer-abc123.cloudflarestream.com/{CF_UID}/iframe":
                f"https://customer-abc123.cloudflarestream.com/{CF_UID}/iframe",
            f"https://iframe.videodelivery.net/{CF_UID}":
                f"https://iframe.videodelivery.net/{CF_UID}",
            f"https://watch.cloudflarestream.com/{CF_UID}":
                f"https://iframe.videodelivery.net/{CF_UID}",
        }
        for url, embed in cases.items():
            with self.subTest(url=url):
                self.assertEqual(trailer_embed_url(url), embed)

    def test_other_links_are_rejected(self):
        for url in (
            "",
            "https://vimeo.com/76979871",
            "https://www.youtube.com/channel/UC123",
            "https://youtu.be/short",
            "javascript:alert(1)//youtu.be/dQw4w9WgXcQ",
            f"https://evil.example/{CF_UID}",
            f"https://customer-abc.cloudflarestream.com.evil.example/{CF_UID}",
            "https://iframe.videodelivery.net/not-a-uid",
        ):
            with self.subTest(url=url):
                self.assertIsNone(trailer_embed_url(url))

    def test_the_model_refuses_an_unsupported_trailer_link(self):
        course, _ = make_course()
        course.trailer_url = "https://vimeo.com/76979871"
        with self.assertRaises(ValidationError) as caught:
            course.full_clean()
        self.assertIn("trailer_url_bn", caught.exception.message_dict)


def stream_settings(**overrides):
    """CLOUDFLARE_STREAM as .env would build it, with test values."""
    config = {
        "account_id": "",
        "signing_key_id": "test-key-id",
        "signing_key_pem": "",
        "customer_code": "abc123",
        "token_ttl_seconds": 7200,
    }
    config.update(overrides)
    return config


@functools.cache
def signing_key():
    """One throwaway RSA key for the run; generating it is the slow part."""
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.TraditionalOpenSSL,
        serialization.NoEncryption(),
    ).decode()
    return key.public_key(), pem


class CloudflarePlaybackTests(SimpleTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.public_key, cls.pem = signing_key()

    def module(self):
        return Module(pk=7, video_provider="cloudflare", video_uid=CF_UID)

    def token_from(self, src):
        prefix = "https://customer-abc123.cloudflarestream.com/"
        self.assertTrue(src.startswith(prefix) and src.endswith("/iframe"), src)
        token = src[len(prefix):-len("/iframe")]
        return jwt.get_unverified_header(token), jwt.decode(
            token, self.public_key, algorithms=["RS256"]
        )

    def test_a_signed_token_plays_on_the_customer_host(self):
        # Cloudflare hands the key out base64-encoded, so test that form.
        encoded = base64.b64encode(self.pem.encode()).decode()
        with self.settings(CLOUDFLARE_STREAM=stream_settings(signing_key_pem=encoded)):
            data = playback(self.module())
        self.assertEqual(data["kind"], "iframe")
        header, claims = self.token_from(data["src"])
        self.assertEqual(header["kid"], "test-key-id")
        self.assertEqual(claims["sub"], CF_UID)
        self.assertEqual(claims["kid"], "test-key-id")
        self.assertFalse(claims["downloadable"])
        self.assertLessEqual(claims["exp"], int(time.time()) + 7200)

    def test_a_decoded_pem_works_too(self):
        with self.settings(CLOUDFLARE_STREAM=stream_settings(signing_key_pem=self.pem)):
            self.token_from(playback(self.module())["src"])

    def test_without_a_customer_code_the_legacy_host_is_used(self):
        config = stream_settings(signing_key_pem=self.pem, customer_code="")
        with self.settings(CLOUDFLARE_STREAM=config):
            src = playback(self.module())["src"]
        self.assertTrue(src.startswith("https://iframe.videodelivery.net/"), src)

    def test_an_unconfigured_key_falls_back_and_says_so(self):
        with (
            self.settings(CLOUDFLARE_STREAM=stream_settings()),
            self.assertLogs("courses.video", "WARNING"),
        ):
            data = playback(self.module())
        self.assertEqual(data["kind"], "file")
        self.assertNotIn(CF_UID, data["src"])

    def test_a_broken_key_falls_back_instead_of_failing_the_page(self):
        with (
            self.settings(CLOUDFLARE_STREAM=stream_settings(signing_key_pem="not a key")),
            self.assertLogs("courses.video", "ERROR"),
        ):
            data = playback(self.module())
        self.assertEqual(data["kind"], "file")


class CloudflareLessonPageTests(TestCase):
    def setUp(self):
        self.course, self.modules = make_course()
        for module in self.modules[:2]:
            module.video_provider = "cloudflare"
            module.video_uid = CF_UID
            module.save(update_fields=["video_provider", "video_uid_bn"])
        self.client.force_login(
            User.objects.create_user(email="rafiq@example.com", password=PASSWORD)
        )
        stream = stream_settings(signing_key_pem=signing_key()[1])
        self.enterContext(self.settings(CLOUDFLARE_STREAM=stream))

    def test_the_player_gets_a_signed_token_never_the_video_id(self):
        response = self.client.get(self.modules[0].get_absolute_url())
        self.assertContains(response, 'src="https://customer-abc123.cloudflarestream.com/ey')
        # The bare UID would play publicly if the video's "require signed
        # URLs" switch were ever off, so the page must not reveal it.
        self.assertNotContains(response, CF_UID)

    def test_a_locked_module_signs_nothing(self):
        response = self.client.get(self.modules[1].get_absolute_url())
        self.assertTemplateUsed(response, "courses/paywall.html")
        self.assertNotContains(response, "cloudflarestream.com")


class CloudflareVideoIdTests(SimpleTestCase):
    def test_the_id_is_trimmed_and_lowercased(self):
        module = Module(video_provider="cloudflare", video_uid=f"  {CF_UID.upper()} ")
        module.clean()
        self.assertEqual(module.video_uid, CF_UID)

    def test_a_link_or_typo_is_refused(self):
        for value in (
            f"https://customer-abc123.cloudflarestream.com/{CF_UID}/watch",
            CF_UID[:-1],
            "foundations/module-01.mp4",
        ):
            with self.subTest(value=value):
                module = Module(video_provider="cloudflare", video_uid=value)
                with self.assertRaises(ValidationError) as caught:
                    module.clean()
                self.assertIn("video_uid_bn", caught.exception.message_dict)

    def test_an_uploaded_file_path_is_not_checked_as_an_id(self):
        Module(video_provider="protected_file", video_uid="foundations/module-01.mp4").clean()


class PromoteOnHomeTests(TestCase):
    def test_promoting_a_course_clears_the_flag_on_the_others(self):
        first, _ = make_course()
        second = Course.objects.create(
            title="Part 2", slug="part-2", summary="S.", description="D.",
            status=Course.Status.PUBLISHED, promote_on_home=True,
        )
        first.promote_on_home = True
        first.save()
        second.refresh_from_db()
        self.assertFalse(second.promote_on_home)
        self.assertEqual(
            list(Course.objects.filter(promote_on_home=True)), [first]
        )


@override_settings(
    MEDIA_ROOT=Path(tempfile.mkdtemp()),
    MEDIA_INTERNAL_URL="/_media/",
)
class XAccelRedirectTests(TestCase):
    """With nginx configured, Django hands off the stream but still gates it."""

    def setUp(self):
        self.course, self.modules = make_course()
        self.student = User.objects.create_user(email="rafiq@example.com", password=PASSWORD)
        self.asset = MediaAsset.objects.create(
            module=self.modules[0],
            kind=MediaAsset.Kind.DOWNLOAD,
            title="Worksheet 1",
            file=SimpleUploadedFile("worksheet.pdf", b"%PDF-1.4 fake"),
        )

    def tearDown(self):
        shutil.rmtree(settings.MEDIA_ROOT, ignore_errors=True)

    def test_an_allowed_request_hands_the_path_to_nginx(self):
        self.client.force_login(self.student)
        response = self.client.get(self.asset.get_absolute_url())
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response["X-Accel-Redirect"].startswith("/_media/"))
        self.assertIn(self.asset.file.name, response["X-Accel-Redirect"])
        self.assertEqual(response["X-Robots-Tag"], "noindex, nofollow")
        self.assertEqual(response.content, b"", "Django must not stream the bytes")

    def test_a_locked_module_never_reaches_the_handoff(self):
        locked = MediaAsset.objects.create(
            module=self.modules[1],
            kind=MediaAsset.Kind.DOWNLOAD,
            title="Worksheet 2",
            file=SimpleUploadedFile("w2.pdf", b"%PDF"),
        )
        self.client.force_login(self.student)
        response = self.client.get(locked.get_absolute_url())
        self.assertEqual(response.status_code, 404)
        self.assertNotIn("X-Accel-Redirect", response)


class NoJavaScriptTests(EnglishPagesMixin, TestCase):
    """The whole student path must work through plain requests and forms.

    This is what a crawler, a text browser, and a student on a flaky mobile
    connection get. It is also what keeps the content indexable.
    """

    def setUp(self):
        self.course, self.modules = make_course()
        self.module = self.modules[0]
        self.quiz, _ = make_quiz(self.module)
        # A second question, so advancing between questions is exercised too.
        second = Question.objects.create(quiz=self.quiz, text="Pitch is measured in?", position=1)
        for index, text in enumerate(["Decibels", "Hertz", "Octaves", "Beats"]):
            Choice.objects.create(
                question=second, text=text, position=index, is_correct=index == 1
            )
        self.student = User.objects.create_user(email="nojs@example.com", password=PASSWORD)
        self.client.force_login(self.student)
        self.base = reverse(
            "courses:quiz",
            kwargs={"slug": self.course.slug, "module_slug": self.module.slug},
        )

    def test_public_content_is_in_the_html_without_scripts(self):
        self.client.logout()
        body = self.client.get(self.course.get_absolute_url()).content.decode()
        for module in self.modules:
            self.assertIn(module.title, body)
        self.assertIn("Curriculum", body)

    def test_lesson_notes_are_in_the_html_without_scripts(self):
        body = self.client.get(self.module.get_absolute_url()).content.decode()
        self.assertIn("<h2>Notes</h2>", body)

    def test_every_lesson_tab_panel_is_rendered_server_side(self):
        """The tab script hides panels; it must never be what creates them."""
        MediaAsset.objects.create(
            module=self.module,
            kind=MediaAsset.Kind.AUDIO,
            title="Example 1.1",
            file=SimpleUploadedFile("a.mp3", b"ID3"),
        )
        MediaAsset.objects.create(
            module=self.module,
            kind=MediaAsset.Kind.DOWNLOAD,
            title="Worksheet 1",
            file=SimpleUploadedFile("w.pdf", b"%PDF"),
        )
        body = self.client.get(self.module.get_absolute_url()).content.decode()
        self.assertIn('id="panel-notes"', body)
        self.assertIn('id="panel-audio"', body)
        self.assertIn('id="panel-files"', body)
        self.assertIn("Example 1.1", body)
        self.assertIn("Worksheet 1", body)

    def test_the_whole_quiz_can_be_completed_with_form_posts_alone(self):
        self.client.get(self.base)
        for question in self.quiz.questions.all():
            correct = question.choices.get(is_correct=True)
            wrong = question.choices.exclude(pk=correct.pk).first()
            # A wrong try first, exactly as a student would.
            response = self.client.post(
                self.base + "answer/", {"question": question.pk, "choice": wrong.pk}
            )
            self.assertEqual(response.status_code, 302, "must redirect, not return JSON")
            self.client.post(
                self.base + "answer/", {"question": question.pk, "choice": correct.pk}
            )
            self.client.post(self.base + "next/")

        attempt = QuizAttempt.objects.filter(student=self.student, quiz=self.quiz).first()
        self.assertIsNotNone(attempt.completed_at)
        self.assertEqual(attempt.wrong_picks, self.quiz.questions.count())
        self.assertTrue(
            ModuleProgress.objects.filter(
                student=self.student, module=self.module, completed_at__isnull=False
            ).exists()
        )

    def test_the_accordions_are_details_elements(self):
        self.client.logout()
        body = self.client.get(self.course.get_absolute_url()).content.decode()
        self.assertIn("<details", body)
        self.assertIn("<summary", body)


@override_settings(MEDIA_ROOT=Path(tempfile.mkdtemp()))
class LibraryFileTests(TestCase):
    """Shared library files follow the paywall of whatever links to them."""

    def setUp(self):
        self.course, self.modules = make_course()
        self.student = User.objects.create_user(email="rafiq@example.com", password=PASSWORD)
        self.staff = User.objects.create_user(
            email="tanveer@example.com", password=PASSWORD, is_staff=True
        )
        self.audio = LibraryFile.objects.create(
            title="C major scale", file=SimpleUploadedFile("c-major.mp3", b"ID3")
        )
        self.diagram = LibraryFile.objects.create(
            title="The stave", file=SimpleUploadedFile("stave.svg", b"<svg></svg>")
        )

    def tearDown(self):
        shutil.rmtree(settings.MEDIA_ROOT, ignore_errors=True)

    def link(self, module, item):
        module.notes_markdown_bn += f"\n\n{item.markdown}\n"
        module.save(update_fields=["notes_markdown_bn"])

    def test_markdown_uses_image_syntax_for_audio_and_images(self):
        self.assertEqual(
            self.audio.markdown, f"![C major scale]({self.audio.get_absolute_url()})"
        )
        pdf = LibraryFile(title="Worksheet", file="library/x/sheet.pdf")
        self.assertTrue(pdf.markdown.startswith("[Worksheet]("))

    def test_download_material_is_a_plain_link_even_for_audio(self):
        track = LibraryFile(
            title="Backing track",
            purpose=LibraryFile.Purpose.DOWNLOAD,
            file="library/x/groove.mp3",
        )
        self.assertTrue(track.is_download)
        self.assertTrue(track.markdown.startswith("[Backing track]("))

    def test_download_material_is_sent_as_an_attachment(self):
        track = LibraryFile.objects.create(
            title="Backing track",
            purpose=LibraryFile.Purpose.DOWNLOAD,
            file=SimpleUploadedFile("groove.mp3", b"ID3"),
        )
        self.client.force_login(self.staff)
        response = self.client.get(track.get_absolute_url())
        self.assertIn("attachment", response["Content-Disposition"])

    def test_lesson_audio_plays_inline(self):
        self.client.force_login(self.staff)
        response = self.client.get(self.audio.get_absolute_url())
        self.assertNotIn("attachment", response.get("Content-Disposition", ""))

    def test_a_link_to_a_library_file_is_marked_as_a_download(self):
        sheet = LibraryFile.objects.create(
            title="Worksheet", file=SimpleUploadedFile("sheet.pdf", b"%PDF")
        )
        self.link(self.modules[0], sheet)
        self.client.force_login(self.student)
        response = self.client.get(self.modules[0].get_absolute_url())
        self.assertContains(
            response, f'<a class="file-link" href="{sheet.get_absolute_url()}">Worksheet</a>'
        )

    def test_keys_are_random_not_sequential(self):
        self.assertNotEqual(self.audio.key, self.diagram.key)
        self.assertGreaterEqual(len(self.audio.key), 16)

    def test_staff_can_fetch_an_unlinked_file(self):
        self.client.force_login(self.staff)
        self.assertEqual(self.client.get(self.audio.get_absolute_url()).status_code, 200)

    def test_an_unlinked_file_is_hidden_from_students(self):
        self.client.force_login(self.student)
        self.assertEqual(self.client.get(self.audio.get_absolute_url()).status_code, 404)

    def test_a_file_linked_from_the_free_module_is_served(self):
        self.link(self.modules[0], self.audio)
        self.client.force_login(self.student)
        response = self.client.get(self.audio.get_absolute_url())
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["X-Robots-Tag"], "noindex, nofollow")

    def test_a_file_linked_only_from_a_locked_module_is_not_served(self):
        self.link(self.modules[1], self.audio)
        self.client.force_login(self.student)
        self.assertEqual(self.client.get(self.audio.get_absolute_url()).status_code, 404)

    def test_an_enrolled_student_gets_files_from_unlocked_paid_modules(self):
        self.link(self.modules[1], self.audio)
        Enrollment.objects.create(student=self.student, course=self.course)
        ModuleProgress.objects.create(
            student=self.student, module=self.modules[0], completed_at=timezone.now()
        )
        self.client.force_login(self.student)
        self.assertEqual(self.client.get(self.audio.get_absolute_url()).status_code, 200)

    def test_a_draft_module_link_does_not_open_the_file(self):
        self.link(self.modules[0], self.audio)
        self.modules[0].status = Module.Status.DRAFT
        self.modules[0].save(update_fields=["status"])
        self.client.force_login(self.student)
        self.assertEqual(self.client.get(self.audio.get_absolute_url()).status_code, 404)

    def test_anonymous_visitors_get_nothing_from_lesson_notes(self):
        self.link(self.modules[0], self.audio)
        self.assertEqual(self.client.get(self.audio.get_absolute_url()).status_code, 404)

    def test_a_file_in_a_published_course_description_is_public(self):
        self.course.description_bn += f"\n\n{self.diagram.markdown}"
        self.course.save(update_fields=["description_bn"])
        self.assertEqual(self.client.get(self.diagram.get_absolute_url()).status_code, 200)

    def test_a_wrong_file_name_is_not_found(self):
        self.client.force_login(self.staff)
        url = reverse(
            "library:file", kwargs={"key": self.audio.key, "name": "other.mp3"}
        )
        self.assertEqual(self.client.get(url).status_code, 404)

    def test_svg_is_sandboxed_when_opened_directly(self):
        self.client.force_login(self.staff)
        response = self.client.get(self.diagram.get_absolute_url())
        self.assertIn("sandbox", response["Content-Security-Policy"])

    def test_the_lesson_page_renders_library_audio_as_a_player(self):
        self.link(self.modules[0], self.audio)
        self.client.force_login(self.student)
        response = self.client.get(self.modules[0].get_absolute_url())
        self.assertContains(
            response, f'<audio controls preload="none" src="{self.audio.get_absolute_url()}">'
        )


@override_settings(MEDIA_ROOT=Path(tempfile.mkdtemp()))
class ModuleDownloadTests(TestCase):
    """Library files picked as a module's downloads, free with the module."""

    def setUp(self):
        self.course, self.modules = make_course()
        self.student = User.objects.create_user(email="rafiq@example.com", password=PASSWORD)
        self.sheet = LibraryFile.objects.create(
            title="Worksheet 1",
            purpose=LibraryFile.Purpose.DOWNLOAD,
            file=SimpleUploadedFile("worksheet-1.pdf", b"%PDF"),
        )
        self.client.force_login(self.student)

    def tearDown(self):
        shutil.rmtree(settings.MEDIA_ROOT, ignore_errors=True)

    def test_the_lesson_lists_the_module_downloads(self):
        self.modules[0].downloads.add(self.sheet)
        response = self.client.get(self.modules[0].get_absolute_url())
        self.assertContains(response, 'id="tab-files"')
        self.assertContains(response, "Worksheet 1")
        self.assertContains(response, "PDF · 4 B")
        self.assertContains(response, f'href="{self.sheet.get_absolute_url()}" download')

    def test_a_module_without_downloads_has_no_downloads_tab(self):
        response = self.client.get(self.modules[0].get_absolute_url())
        self.assertNotContains(response, 'id="tab-files"')

    def test_a_download_on_the_free_module_is_served_as_an_attachment(self):
        self.modules[0].downloads.add(self.sheet)
        response = self.client.get(self.sheet.get_absolute_url())
        self.assertEqual(response.status_code, 200)
        self.assertIn("attachment", response["Content-Disposition"])

    def test_a_download_on_a_locked_module_is_not_served(self):
        self.modules[1].downloads.add(self.sheet)
        self.assertEqual(self.client.get(self.sheet.get_absolute_url()).status_code, 404)

    def test_an_enrolled_student_gets_downloads_from_unlocked_paid_modules(self):
        self.modules[1].downloads.add(self.sheet)
        Enrollment.objects.create(student=self.student, course=self.course)
        ModuleProgress.objects.create(
            student=self.student, module=self.modules[0], completed_at=timezone.now()
        )
        self.assertEqual(self.client.get(self.sheet.get_absolute_url()).status_code, 200)


@override_settings(MEDIA_ROOT=Path(tempfile.mkdtemp()))
class QuizLibraryMediaTests(TestCase):
    """Library audio and diagrams pasted anywhere into a quiz."""

    def setUp(self):
        self.course, self.modules = make_course()
        self.student = User.objects.create_user(email="rafiq@example.com", password=PASSWORD)
        self.audio = LibraryFile.objects.create(
            title="Interval", file=SimpleUploadedFile("interval.mp3", b"ID3")
        )
        self.diagram = LibraryFile.objects.create(
            title="Stave", file=SimpleUploadedFile("stave.svg", b"<svg></svg>")
        )
        self.quiz, self.question = make_quiz(self.modules[0])
        self.client.force_login(self.student)

    @property
    def quiz_url(self):
        return reverse(
            "courses:quiz",
            kwargs={"slug": self.course.slug, "module_slug": self.modules[0].slug},
        )

    def tearDown(self):
        shutil.rmtree(settings.MEDIA_ROOT, ignore_errors=True)

    def test_question_markdown_renders_audio_and_diagrams(self):
        self.question.text_bn = (
            f"Name this interval.\n\n{self.audio.markdown}\n\n{self.diagram.markdown}"
        )
        self.question.save(update_fields=["text_bn"])
        response = self.client.get(self.quiz_url)
        self.assertContains(
            response, f'<audio controls preload="none" src="{self.audio.get_absolute_url()}">'
        )
        self.assertContains(response, f'src="{self.diagram.get_absolute_url()}"')

    def test_option_audio_sits_outside_the_answer_button(self):
        choice = self.question.choices.get(position=0)
        choice.text_bn = f"{self.audio.markdown}"
        choice.save(update_fields=["text_bn"])
        html = self.client.get(self.quiz_url).content.decode()
        player = html.index(f'src="{self.audio.get_absolute_url()}"')
        button = html.index('class="answer', player)
        self.assertNotIn("<button", html[html.rindex("answer-option", 0, player):player])
        self.assertGreater(button, player)

    def test_option_images_show_inside_the_button(self):
        choice = self.question.choices.get(position=1)
        choice.text_bn = f"This one {self.diagram.markdown}"
        choice.save(update_fields=["text_bn"])
        response = self.client.get(self.quiz_url)
        self.assertContains(response, '<span class="answer__text">This one <img')

    def test_the_explanation_arrives_rendered(self):
        self.question.explanation_bn = f"Four. {self.diagram.markdown}"
        self.question.save(update_fields=["explanation_bn"])
        correct = self.question.choices.get(is_correct=True)
        response = self.client.post(
            reverse(
                "courses:quiz_answer",
                kwargs={"slug": self.course.slug, "module_slug": self.modules[0].slug},
            ),
            {"question": self.question.pk, "choice": correct.pk},
            headers={"X-Requested-With": "fetch"},
        )
        self.assertIn("<img", response.json()["explanation"])

    def test_markdown_in_the_title_stays_out_of_the_browser_tab(self):
        self.quiz.title_bn = "Rhythm **check**"
        self.quiz.save(update_fields=["title_bn"])
        response = self.client.get(self.quiz_url)
        self.assertContains(response, "Rhythm <strong>check</strong>")
        self.assertContains(response, "<title>Rhythm check")

    def test_a_file_linked_from_an_unlocked_quiz_is_served(self):
        choice = self.question.choices.first()
        choice.text_bn = self.audio.markdown
        choice.save(update_fields=["text_bn"])
        self.assertEqual(self.client.get(self.audio.get_absolute_url()).status_code, 200)

    def test_a_file_linked_from_a_locked_quiz_is_not_served(self):
        _, question = make_quiz(self.modules[1])
        question.explanation_bn = self.diagram.markdown
        question.save(update_fields=["explanation_bn"])
        self.assertEqual(self.client.get(self.diagram.get_absolute_url()).status_code, 404)

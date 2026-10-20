"""Authors: kept on their own, linked to courses, shown on the public pages."""

import io
import shutil
import tempfile
from pathlib import Path

from django.conf import settings
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db.models import ProtectedError
from django.templatetags.static import static
from django.test import TestCase, override_settings
from django.urls import reverse
from PIL import Image

from core.testing import EnglishPagesMixin
from courses.models import Author, Course


def published_course(**extra):
    """The published course every test here links an author to."""
    return Course.objects.create(
        title="Foundations of Music",
        slug="foundations-of-music",
        summary="Summary.",
        description="Description.",
        status=Course.Status.PUBLISHED,
        **extra,
    )


def png_upload(name="author.png"):
    """A real (tiny) PNG, since an ImageField checks the bytes are an image."""
    buffer = io.BytesIO()
    Image.new("RGB", (8, 8), "black").save(buffer, format="PNG")
    return SimpleUploadedFile(name, buffer.getvalue(), content_type="image/png")


@override_settings(MEDIA_ROOT=Path(tempfile.mkdtemp()))
class AuthorProfileTests(EnglishPagesMixin, TestCase):
    """The course page's author card and the public author photo."""

    def setUp(self):
        self.course = published_course()
        self.author = Author.objects.create(
            name="Tanveer Haque",
            bio="Plays **bass** in Dhaka.<script>alert(1)</script>",
            photo=png_upload(),
        )

    def tearDown(self):
        shutil.rmtree(settings.MEDIA_ROOT, ignore_errors=True)

    def link_author(self):
        self.course.author = self.author
        self.course.save(update_fields=["author"])

    def test_no_author_means_no_author_card(self):
        response = self.client.get(self.course.get_absolute_url())
        self.assertNotContains(response, "About the author")

    def test_the_author_card_shows_the_name_photo_and_rendered_bio(self):
        self.link_author()
        response = self.client.get(self.course.get_absolute_url())
        self.assertContains(response, "About the author")
        self.assertContains(response, "Tanveer Haque")
        self.assertContains(response, "<strong>bass</strong>")
        self.assertNotContains(response, "alert(1)")
        self.assertContains(response, self.author.photo_url)

    def test_the_name_falls_back_to_the_site_instructor(self):
        self.assertEqual(self.course.author_name, settings.SITE["instructor"])

    def test_one_author_can_teach_several_courses(self):
        self.link_author()
        other = Course.objects.create(
            title="Harmony", slug="harmony", summary="S.", description="D.", author=self.author
        )
        self.assertEqual(set(self.author.courses.all()), {self.course, other})

    def test_an_author_who_teaches_a_course_cannot_be_deleted(self):
        self.link_author()
        with self.assertRaises(ProtectedError):
            self.author.delete()

    def test_slugs_stay_unique(self):
        twin = Author.objects.create(name="Tanveer Haque")
        self.assertEqual(twin.slug, "tanveer-haque-2")

    def test_the_photo_is_public_for_an_author_of_a_published_course(self):
        self.link_author()
        response = self.client.get(self.author.photo_url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "image/png")
        self.assertIn("public", response["Cache-Control"])

    def test_an_author_without_a_published_course_is_hidden(self):
        self.assertEqual(self.client.get(self.author.photo_url).status_code, 404)
        self.link_author()
        self.course.status = Course.Status.DRAFT
        self.course.save(update_fields=["status"])
        self.assertEqual(self.client.get(self.author.photo_url).status_code, 404)

    def test_no_photo_is_a_404(self):
        self.link_author()
        self.author.photo = ""
        self.author.save()
        url = reverse("courses:author_photo", kwargs={"slug": self.author.slug})
        self.assertEqual(self.client.get(url).status_code, 404)


@override_settings(MEDIA_ROOT=Path(tempfile.mkdtemp()))
class AuthorOnPublicPagesTests(EnglishPagesMixin, TestCase):
    """The home and About pages show the promoted course's author."""

    @classmethod
    def setUpTestData(cls):
        cls.author = Author.objects.create(
            name="Rumana Akter",
            bio="Teaches **harmony** in Chattogram, Bangladesh.",
            photo=png_upload(),
        )
        cls.course = published_course(author=cls.author)

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(settings.MEDIA_ROOT, ignore_errors=True)

    def test_home_shows_the_author_name_photo_and_bio(self):
        """The hero and "Your instructor" use the author, not the bundled photo."""
        response = self.client.get(reverse("pages:home"))
        self.assertContains(response, "Rumana Akter")
        self.assertContains(response, self.author.photo_url)
        self.assertContains(response, "<strong>harmony</strong>")
        self.assertNotContains(response, f'src="{static("img/instructor-640.jpg")}"')

    def test_about_introduces_the_author(self):
        """Heading, photo, title, meta description and Person schema all follow the author."""
        response = self.client.get(reverse("pages:about"))
        self.assertContains(response, "<h1 class=\"display-2\">Rumana Akter</h1>", html=True)
        self.assertContains(response, self.author.photo_url)
        self.assertContains(response, "<title>About Rumana Akter")
        self.assertContains(
            response, '<meta name="description" content="Teaches harmony in Chattogram'
        )
        self.assertContains(response, '"name": "Rumana Akter"')

    def test_without_an_author_the_pages_fall_back_to_the_site_instructor(self):
        """A course with no author still shows a name and a photo."""
        Course.objects.filter(pk=self.course.pk).update(author=None)
        for name in ("pages:home", "pages:about"):
            response = self.client.get(reverse(name))
            self.assertContains(response, settings.SITE["instructor"])
            self.assertContains(response, f'src="{static("img/instructor-640.jpg")}"')

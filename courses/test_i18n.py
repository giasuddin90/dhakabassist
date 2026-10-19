"""Content and media stored in Bangla and English."""

import io
import json
import shutil
import tempfile
from pathlib import Path

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.db import IntegrityError, transaction
from django.test import TestCase, override_settings
from django.utils import translation

from courses.models import Course, LibraryFile, MediaAsset, Module

User = get_user_model()


def make_module(**fields):
    course = Course.objects.create(
        title_en="Foundations of Music",
        slug="foundations-of-music",
        summary_en="Summary.",
        description_en="Description.",
        status=Course.Status.PUBLISHED,
    )
    return Module.objects.create(
        course=course,
        number="01",
        slug="sound",
        title_en="Sound",
        access=Module.Access.FREE,
        status=Module.Status.PUBLISHED,
        **fields,
    )


class TranslatedFieldTests(TestCase):
    def test_each_language_reads_its_own_column(self):
        module = make_module(title_bn="শব্দ")
        with translation.override("bn"):
            self.assertEqual(module.title, "শব্দ")
        with translation.override("en"):
            self.assertEqual(module.title, "Sound")

    def test_a_blank_translation_falls_back_to_the_other_language(self):
        module = make_module(summary_bn="শব্দ কী")
        with translation.override("bn"):
            self.assertEqual(module.title, "Sound")
        with translation.override("en"):
            self.assertEqual(module.summary, "শব্দ কী")

    def test_assigning_writes_the_active_language_only(self):
        module = make_module()
        with translation.override("bn"):
            module.title = "শব্দ"
        self.assertEqual((module.title_bn, module.title_en), ("শব্দ", "Sound"))

    def test_the_database_needs_a_required_field_in_some_language(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            Course.objects.create(slug="empty", summary_en="S.", description_en="D.")

    def test_media_settings_follow_the_video_that_plays(self):
        module = make_module(
            video_uid_en="course/en.mp4",
            video_duration_seconds_en=300,
            video_has_subtitles_en=True,
        )
        # No Bangla video: the Bangla page plays the English one, with its
        # duration and subtitles rather than the empty Bangla columns'.
        with translation.override("bn"):
            self.assertEqual(
                (module.video_uid, module.video_duration_seconds, module.video_has_subtitles),
                ("course/en.mp4", 300, True),
            )


@override_settings(MEDIA_ROOT=Path(tempfile.mkdtemp()))
class LanguageMediaTests(TestCase):
    def setUp(self):
        self.module = make_module()
        self.student = User.objects.create_user(email="rafiq@example.com", password="pw-long-1234")

    def tearDown(self):
        shutil.rmtree(settings.MEDIA_ROOT, ignore_errors=True)
        translation.activate("bn")

    def test_each_language_gets_its_own_asset_file(self):
        asset = MediaAsset.objects.create(
            module=self.module,
            kind=MediaAsset.Kind.DOWNLOAD,
            title_en="Worksheet",
            file_bn=SimpleUploadedFile("sheet-bn.pdf", b"%PDF bangla"),
            file_en=SimpleUploadedFile("sheet-en.pdf", b"%PDF english"),
        )
        self.assertIn("/bn/", asset.file_bn.name)
        self.client.force_login(self.student)
        bangla = self.client.get(f"/asset/{asset.pk}/")
        english = self.client.get(f"/en/asset/{asset.pk}/")
        self.assertEqual(b"".join(bangla.streaming_content), b"%PDF bangla")
        self.assertEqual(b"".join(english.streaming_content), b"%PDF english")

    def test_an_asset_in_one_language_serves_both(self):
        asset = MediaAsset.objects.create(
            module=self.module,
            kind=MediaAsset.Kind.DOWNLOAD,
            title_en="Worksheet",
            file_en=SimpleUploadedFile("sheet-en.pdf", b"%PDF english"),
        )
        self.client.force_login(self.student)
        response = self.client.get(f"/asset/{asset.pk}/")
        self.assertEqual(b"".join(response.streaming_content), b"%PDF english")

    def test_downloads_are_listed_for_their_language(self):
        files = {
            language: LibraryFile.objects.create(
                title_en=language,
                language=language,
                file=SimpleUploadedFile(f"{language}.pdf", b"%PDF"),
            )
            for language in LibraryFile.Language.values
        }
        self.module.downloads.set(files.values())
        for active, expected in (("bn", {"both", "bn"}), ("en", {"both", "en"})):
            with self.subTest(language=active), translation.override(active):
                module = Module.objects.prefetch_related("assets", "downloads").get(
                    pk=self.module.pk
                )
                self.assertEqual({f.language for f in module.download_files}, expected)


class ImportLanguageTests(TestCase):
    def run_import(self, data):
        path = Path(tempfile.mkdtemp()) / "content.json"
        path.write_text(json.dumps(data), encoding="utf-8")
        self.addCleanup(shutil.rmtree, path.parent)
        call_command("import_content", str(path), stdout=io.StringIO())

    def test_both_languages_import(self):
        self.run_import({"courses": [{
            "slug": "c", "title_bn": "কোর্স", "title_en": "Course",
            "summary_en": "S.", "description_en": "D.",
        }]})
        course = Course.objects.get(slug="c")
        self.assertEqual((course.title_bn, course.title_en), ("কোর্স", "Course"))

    def test_a_file_from_before_the_site_was_bilingual_imports_as_english(self):
        self.run_import({"courses": [{
            "slug": "c", "title": "Course", "summary": "S.", "description": "D.",
            "modules": [{"number": "01", "title": "Sound", "video_uid": "c/01.mp4"}],
        }]})
        module = Module.objects.get(course__slug="c")
        self.assertEqual((module.title_en, module.video_uid_en), ("Sound", "c/01.mp4"))


class MissingTranslationTests(TestCase):
    def test_a_module_written_only_in_english_needs_bangla(self):
        module = make_module(notes_markdown_en="## Notes")
        self.assertTrue(module.needs_bangla)
        module.title_bn, module.notes_markdown_bn = "শব্দ", "## নোট"
        self.assertFalse(module.needs_bangla)

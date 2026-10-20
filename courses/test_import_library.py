"""The `import_library` command: adds a folder of files to the media library."""

import shutil
import tempfile
from io import StringIO
from pathlib import Path

from django.conf import settings
from django.core.management import CommandError, call_command
from django.test import TestCase, override_settings

from courses.models import LibraryFile


def run(source, **options):
    out = StringIO()
    call_command("import_library", str(source), stdout=out, **options)
    return out.getvalue()


@override_settings(MEDIA_ROOT=Path(tempfile.mkdtemp()))
class ImportLibraryTests(TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.source = Path(folder.name)
        for name, body in (
            ("Diagram 3.2.svg", b"<svg></svg>"),
            ("Q 4.18.svg", b"<svg></svg>"),
            ("Q 4.18.mp3", b"ID3"),
            ("q 5.17c.mp3", b"ID3"),
            ("Notes.md", b"# Notes"),
        ):
            (self.source / name).write_bytes(body)

    def tearDown(self):
        shutil.rmtree(settings.MEDIA_ROOT, ignore_errors=True)

    def test_adds_each_accepted_file_with_title_purpose_and_folder(self):
        output = run(self.source)
        self.assertIn("Skipped Notes.md", output)
        self.assertEqual(LibraryFile.objects.count(), 4)
        diagram = LibraryFile.objects.get(title_en="Diagram 3.2")
        self.assertEqual(diagram.purpose, LibraryFile.Purpose.LESSON)
        self.assertEqual(diagram.folder, "Module 3")
        self.assertTrue((Path(settings.MEDIA_ROOT) / diagram.file.name).is_file())
        quiz = LibraryFile.objects.filter(title_en="Q 4.18")
        self.assertEqual(sorted(item.extension for item in quiz), ["mp3", "svg"])
        self.assertTrue(all(item.purpose == LibraryFile.Purpose.QUIZ for item in quiz))
        lower = LibraryFile.objects.get(title_en="Q 5.17c")
        self.assertEqual(lower.purpose, LibraryFile.Purpose.QUIZ)

    def test_rerunning_skips_files_already_in_the_library(self):
        run(self.source)
        output = run(self.source)
        self.assertEqual(LibraryFile.objects.count(), 4)
        self.assertIn("Added 0 file(s), skipped 5.", output)

    def test_folder_option_puts_everything_in_one_folder(self):
        run(self.source, folder="  Markup   media ")
        self.assertEqual(
            set(LibraryFile.objects.values_list("folder", flat=True)), {"Markup media"}
        )

    def test_dry_run_saves_nothing(self):
        output = run(self.source, dry_run=True)
        self.assertIn("would add 4 file(s)", output)
        self.assertFalse(LibraryFile.objects.exists())

    def test_missing_folder_is_an_error(self):
        with self.assertRaises(CommandError):
            run(self.source / "missing")

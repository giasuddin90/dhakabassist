"""The `import_content` command: loads a JSON file, or refuses it whole."""

import json
import tempfile
from io import StringIO
from pathlib import Path

from django.conf import settings
from django.core.management import CommandError, call_command
from django.test import SimpleTestCase, TestCase

from courses.models import Course, Module, Question
from pages.models import Faq, LegalPage

EXAMPLE = Path(settings.BASE_DIR) / "docs" / "seed.example.json"


def run(path, **options):
    out = StringIO()
    call_command("import_content", str(path), stdout=out, **options)
    return out.getvalue()


class ImportContentTests(TestCase):
    def write(self, data):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        path = Path(folder.name) / "content.json"
        path.write_text(json.dumps(data), encoding="utf-8")
        return path

    def example(self):
        return json.loads(EXAMPLE.read_text(encoding="utf-8"))

    def test_the_example_file_loads_everything(self):
        run(EXAMPLE)
        course = Course.objects.get(slug="sample-course")
        self.assertEqual(course.modules.count(), 2)
        module = course.modules.get(number="01")
        self.assertEqual(module.lessons.count(), 2)
        question = Question.objects.get(quiz__module=module)
        self.assertEqual(question.choices.filter(is_correct=True).count(), 1)
        self.assertEqual(question.choices.count(), 4)
        self.assertTrue(Faq.objects.exists())
        self.assertTrue(LegalPage.objects.filter(slug="terms").exists())

    def test_running_twice_updates_rather_than_duplicates(self):
        run(EXAMPLE)
        data = self.example()
        data["courses"][0]["title"] = "Renamed"
        run(self.write(data))
        self.assertEqual(Course.objects.count(), 1)
        self.assertEqual(Module.objects.count(), 2)
        self.assertEqual(Question.objects.count(), 1)
        self.assertEqual(Course.objects.get().title, "Renamed")
        self.assertEqual(Faq.objects.count(), 1)

    def test_a_dry_run_saves_nothing(self):
        output = run(EXAMPLE, dry_run=True)
        self.assertIn("Dry run", output)
        self.assertFalse(Course.objects.exists())
        self.assertFalse(Faq.objects.exists())

    def test_one_bad_entry_rolls_back_the_whole_file(self):
        data = self.example()
        data["courses"][0]["modules"][1]["access"] = "secret"
        with self.assertRaisesMessage(CommandError, "courses[0].modules[1]"):
            run(self.write(data))
        self.assertFalse(Course.objects.exists())

    def test_a_question_needs_exactly_one_correct_choice(self):
        data = self.example()
        data["courses"][0]["modules"][0]["quiz"]["questions"][0]["choices"][1]["correct"] = True
        with self.assertRaisesMessage(CommandError, "exactly one correct"):
            run(self.write(data))
        self.assertFalse(Course.objects.exists())

    def test_unknown_fields_are_refused_rather_than_ignored(self):
        data = self.example()
        data["courses"][0]["prise"] = 10
        with self.assertRaisesMessage(CommandError, "prise"):
            run(self.write(data))

    def test_a_course_can_require_one_defined_earlier_in_the_file(self):
        data = self.example()
        part_two = {
            "slug": "sample-part-2", "title": "Sample", "summary": "S.",
            "description": "D.", "requires": "sample-course",
        }
        data["courses"].append(part_two)
        run(self.write(data))
        self.assertEqual(Course.objects.get(slug="sample-part-2").requires.slug, "sample-course")


class ImportContentFileErrorTests(SimpleTestCase):
    def test_a_missing_file_is_reported(self):
        with self.assertRaisesMessage(CommandError, "Cannot read"):
            run("/nonexistent/content.json")

    def test_invalid_json_is_reported(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "bad.json"
            path.write_text("{not json", encoding="utf-8")
            with self.assertRaisesMessage(CommandError, "not valid JSON"):
                run(path)

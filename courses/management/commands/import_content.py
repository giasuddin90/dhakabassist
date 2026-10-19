"""Load courses, modules, quizzes, FAQs and legal pages from a JSON file.

    manage.py import_content docs/seed.example.json
    manage.py import_content my-content.json --dry-run

Idempotent: courses are matched by slug, modules by course and number, legal
pages by slug and FAQs by question, so re-running updates in place. A module's
lessons and quiz questions are replaced by the file's, as `seed_demo` does.

The whole file is loaded in one transaction. Any invalid entry aborts the run
and names the entry, so a half-imported course is never left behind.
"""

import json
from pathlib import Path

from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils.text import slugify

from courses.models import Choice, Course, Lesson, Module, Question, Quiz
from pages.models import Faq, LegalPage

COURSE_FIELDS = (
    "title", "subtitle", "summary", "description", "level", "price", "status",
    "trailer_url", "trailer_label", "trailer_duration", "promote_on_home", "position",
    "meta_title", "meta_description",
)
MODULE_FIELDS = (
    "title", "slug", "title_bn", "summary", "notes_markdown", "access", "status",
    "video_provider", "video_uid", "video_duration_seconds", "video_has_subtitles",
)
QUIZ_FIELDS = ("title", "require_perfect_score", "allow_unlimited_retries")
QUESTION_FIELDS = ("text", "explanation")
FAQ_FIELDS = ("answer", "position", "is_published")
LEGAL_FIELDS = ("title", "body_markdown", "meta_description", "is_published")


class DryRun(Exception):
    """Raised to roll the transaction back after a successful dry run."""


def check_keys(data, allowed, where):
    if not isinstance(data, dict):
        raise CommandError(f"{where}: expected an object.")
    unknown = sorted(set(data) - set(allowed))
    if unknown:
        raise CommandError(f"{where}: unknown field(s) {', '.join(unknown)}.")


def save(obj, data, fields, where):
    """Apply the whitelisted fields, validate like a form would, and save."""
    for field in fields:
        if field in data:
            setattr(obj, field, data[field])
    try:
        obj.full_clean()
    except ValidationError as exc:
        raise CommandError(f"{where}: {'; '.join(exc.messages)}") from exc
    obj.save()
    return obj


class Command(BaseCommand):
    help = "Load courses, modules, quizzes, FAQs and legal pages from a JSON file."

    def add_arguments(self, parser):
        parser.add_argument("path", type=Path, help="JSON file to import.")
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Validate and report what would change, then roll everything back.",
        )

    def handle(self, *args, **options):
        data = self._read(options["path"])
        check_keys(data, ("courses", "faqs", "legal_pages"), "file")
        try:
            with transaction.atomic():
                counts = {
                    "courses": self._courses(data.get("courses", [])),
                    "faqs": self._faqs(data.get("faqs", [])),
                    "legal pages": self._legal(data.get("legal_pages", [])),
                }
                if options["dry_run"]:
                    raise DryRun
        except DryRun:
            prefix = "Dry run, nothing saved: "
        else:
            prefix = "Imported "
        summary = ", ".join(f"{count} {label}" for label, count in counts.items())
        self.stdout.write(self.style.SUCCESS(prefix + summary + "."))

    @staticmethod
    def _read(path):
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except OSError as exc:
            raise CommandError(f"Cannot read {path}: {exc.strerror}.") from exc
        except json.JSONDecodeError as exc:
            raise CommandError(f"{path} is not valid JSON: {exc}.") from exc

    # -- courses -----------------------------------------------------------

    def _courses(self, rows):
        for index, row in enumerate(rows):
            where = f"courses[{index}]"
            check_keys(row, ("slug", "requires", "modules", *COURSE_FIELDS), where)
            if not row.get("slug"):
                raise CommandError(f"{where}: slug is required.")
            course = Course.objects.filter(slug=row["slug"]).first() or Course(slug=row["slug"])
            course.requires = self._prerequisite(row.get("requires"), where)
            save(course, row, COURSE_FIELDS, where)
            self._modules(course, row.get("modules", []), where)
        return len(rows)

    @staticmethod
    def _prerequisite(slug, where):
        if not slug:
            return None
        try:
            return Course.objects.get(slug=slug)
        except Course.DoesNotExist as exc:
            raise CommandError(
                f"{where}: requires “{slug}”, which is not in the database or earlier in the file."
            ) from exc

    def _modules(self, course, rows, parent):
        for index, row in enumerate(rows):
            where = f"{parent}.modules[{index}]"
            check_keys(row, ("number", "lessons", "quiz", *MODULE_FIELDS), where)
            if not row.get("number"):
                raise CommandError(f"{where}: number is required.")
            module = Module.objects.filter(course=course, number=row["number"]).first() or Module(
                course=course, number=row["number"], position=index
            )
            module.slug = module.slug or slugify(row.get("title", ""))
            save(module, row, MODULE_FIELDS, where)
            self._lessons(module, row.get("lessons", []), where)
            if "quiz" in row:
                self._quiz(module, row["quiz"], where)

    @staticmethod
    def _lessons(module, titles, where):
        module.lessons.all().delete()
        for index, title in enumerate(titles):
            save(Lesson(module=module, position=index), {"title": title}, ("title",),
                 f"{where}.lessons[{index}]")

    def _quiz(self, module, row, parent):
        where = f"{parent}.quiz"
        check_keys(row, ("questions", *QUIZ_FIELDS), where)
        quiz = Quiz.objects.filter(module=module).first() or Quiz(module=module)
        save(quiz, row, QUIZ_FIELDS, where)
        quiz.questions.all().delete()
        for index, item in enumerate(row.get("questions", [])):
            self._question(quiz, index, item, f"{where}.questions[{index}]")

    @staticmethod
    def _question(quiz, index, row, where):
        check_keys(row, ("choices", *QUESTION_FIELDS), where)
        choices = row.get("choices", [])
        for choice in choices:
            check_keys(choice, ("text", "correct"), f"{where}.choices")
        if len(choices) < 2 or sum(bool(c.get("correct")) for c in choices) != 1:
            raise CommandError(f"{where}: needs two or more choices and exactly one correct.")
        question = save(Question(quiz=quiz, position=index), row, QUESTION_FIELDS, where)
        for position, choice in enumerate(choices):
            save(
                Choice(question=question, position=position, is_correct=bool(choice.get("correct"))),
                choice, ("text",), f"{where}.choices[{position}]",
            )

    # -- site content ------------------------------------------------------

    @staticmethod
    def _faqs(rows):
        for index, row in enumerate(rows):
            where = f"faqs[{index}]"
            check_keys(row, ("question", *FAQ_FIELDS), where)
            question = row.get("question", "")
            faq = Faq.objects.filter(question=question).first() or Faq(
                question=question, position=index
            )
            save(faq, row, ("question", *FAQ_FIELDS), where)
        return len(rows)

    @staticmethod
    def _legal(rows):
        for index, row in enumerate(rows):
            where = f"legal_pages[{index}]"
            check_keys(row, ("slug", *LEGAL_FIELDS), where)
            slug = row.get("slug", "")
            page = LegalPage.objects.filter(slug=slug).first() or LegalPage(slug=slug)
            save(page, row, ("slug", *LEGAL_FIELDS), where)
        return len(rows)

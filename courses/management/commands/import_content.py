"""Load courses, modules, quizzes, FAQs and legal pages from a JSON file.

    manage.py import_content docs/seed.example.json
    manage.py import_content my-content.json --dry-run

Idempotent: courses are matched by slug, modules by course and number, legal
pages by slug and FAQs by question, so re-running updates in place.

Text comes in both languages as `<field>_bn` and `<field>_en`, e.g.
`title_bn` and `title_en`. A plain `title` (the format before the site
was bilingual) is read as English, so older files still import. A module's
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

from courses.i18n import columns
from courses.models import Choice, Course, Lesson, Module, Question, Quiz
from pages.models import Faq, LegalPage

# The translated fields of each kind of entry, then the plain ones.
COURSE_TEXT = (
    "title", "subtitle", "summary", "description", "level", "trailer_url", "trailer_label",
    "trailer_duration", "meta_title", "meta_description",
)
MODULE_TEXT = (
    "title", "summary", "notes_markdown", "video_uid", "video_duration_seconds",
    "video_has_subtitles",
)
QUIZ_TEXT = ("title",)
QUESTION_TEXT = ("text", "explanation")
CHOICE_TEXT = ("text",)
LESSON_TEXT = ("title",)
FAQ_TEXT = ("question", "answer")
LEGAL_TEXT = ("title", "body_markdown", "meta_description")


def bilingual(names):
    return tuple(column for name in names for column in columns(name))


COURSE_FIELDS = (
    *bilingual(COURSE_TEXT), "price", "status", "promote_on_home", "position",
)
MODULE_FIELDS = (
    *bilingual(MODULE_TEXT), "slug", "access", "status", "video_provider",
)
QUIZ_FIELDS = (*bilingual(QUIZ_TEXT), "require_perfect_score", "allow_unlimited_retries")
QUESTION_FIELDS = bilingual(QUESTION_TEXT)
FAQ_FIELDS = (*bilingual(FAQ_TEXT), "position", "is_published")
LEGAL_FIELDS = (*bilingual(LEGAL_TEXT), "is_published")


def english_by_default(data, names, where):
    """Read a plain `title` from an older file as `title_en`."""
    if not isinstance(data, dict):
        return data
    data = dict(data)
    for name in names:
        if name in data:
            if f"{name}_en" in data:
                raise CommandError(f"{where}: give {name} or {name}_en, not both.")
            data[f"{name}_en"] = data.pop(name)
    return data


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
            row = english_by_default(row, COURSE_TEXT, where)
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
            row = english_by_default(row, MODULE_TEXT, where)
            check_keys(row, ("number", "lessons", "quiz", *MODULE_FIELDS), where)
            if not row.get("number"):
                raise CommandError(f"{where}: number is required.")
            number = Module.pad_number(row["number"])
            module = Module.objects.filter(course=course, number=number).first() or Module(
                course=course, number=number
            )
            module.slug = module.slug or slugify(row.get("title_en") or row.get("title_bn", ""))
            save(module, row, MODULE_FIELDS, where)
            self._lessons(module, row.get("lessons", []), where)
            if "quiz" in row:
                self._quiz(module, row["quiz"], where)

    @staticmethod
    def _lessons(module, titles, where):
        module.lessons.all().delete()
        for index, title in enumerate(titles):
            here = f"{where}.lessons[{index}]"
            # A lesson is its title: a string (English) or {"title_bn", "title_en"}.
            row = {"title_en": title} if isinstance(title, str) else title
            row = english_by_default(row, LESSON_TEXT, here)
            check_keys(row, bilingual(LESSON_TEXT), here)
            save(Lesson(module=module, position=index), row, bilingual(LESSON_TEXT), here)

    def _quiz(self, module, row, parent):
        where = f"{parent}.quiz"
        row = english_by_default(row, QUIZ_TEXT, where)
        check_keys(row, ("questions", *QUIZ_FIELDS), where)
        quiz = Quiz.objects.filter(module=module).first() or Quiz(module=module)
        save(quiz, row, QUIZ_FIELDS, where)
        quiz.questions.all().delete()
        for index, item in enumerate(row.get("questions", [])):
            self._question(quiz, index, item, f"{where}.questions[{index}]")

    @staticmethod
    def _question(quiz, index, row, where):
        row = english_by_default(row, QUESTION_TEXT, where)
        check_keys(row, ("choices", *QUESTION_FIELDS), where)
        choices = [
            english_by_default(choice, CHOICE_TEXT, f"{where}.choices")
            for choice in row.get("choices", [])
        ]
        for choice in choices:
            check_keys(choice, (*bilingual(CHOICE_TEXT), "correct"), f"{where}.choices")
        if len(choices) < 2 or sum(bool(c.get("correct")) for c in choices) != 1:
            raise CommandError(f"{where}: needs two or more choices and exactly one correct.")
        question = save(Question(quiz=quiz, position=index), row, QUESTION_FIELDS, where)
        for position, choice in enumerate(choices):
            save(
                Choice(question=question, position=position, is_correct=bool(choice.get("correct"))),
                choice, bilingual(CHOICE_TEXT), f"{where}.choices[{position}]",
            )

    # -- site content ------------------------------------------------------

    @staticmethod
    def _faqs(rows):
        for index, row in enumerate(rows):
            where = f"faqs[{index}]"
            row = english_by_default(row, FAQ_TEXT, where)
            check_keys(row, FAQ_FIELDS, where)
            # Matched on whichever language the file gives the question in.
            match = {c: row[c] for c in columns("question") if row.get(c)}
            faq = (Faq.objects.filter(**match).first() if match else None) or Faq(
                position=index
            )
            save(faq, row, FAQ_FIELDS, where)
        return len(rows)

    @staticmethod
    def _legal(rows):
        for index, row in enumerate(rows):
            where = f"legal_pages[{index}]"
            row = english_by_default(row, LEGAL_TEXT, where)
            check_keys(row, ("slug", *LEGAL_FIELDS), where)
            slug = row.get("slug", "")
            page = LegalPage.objects.filter(slug=slug).first() or LegalPage(slug=slug)
            save(page, row, ("slug", *LEGAL_FIELDS), where)
        return len(rows)

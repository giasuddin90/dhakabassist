"""Load the Foundations of Music course, its author, FAQs and legal pages.

    manage.py import_library        # first: the diagrams and audio
    manage.py seed_course           # then: MEDIA_ROOT/markup_content
    manage.py seed_course path/to/markup_content --dry-run

The source folder holds one folder per language, `*_English` and `*_Bangla`,
written in Obsidian:

- `00…` is the outline: `# Module 1 — Title` headings with the lessons as a list.
- `01…` to `09…` are each module's notes; `NN.PCQ.md` is its performance
  checkpoint, then a `# Quiz` of numbered questions whose choices are a list
  with the right one marked ✓.
- Module 1's first three sections introduce the instructor and the course;
  they also become the author's bio and the course's summary and description.
- Files numbered after the last module (`10…`, the closing message) are added
  to the end of the last module's notes.

`![[Diagram 2.1.svg]]` embeds become links to the media library file with
that name, so `import_library` must have run first. Questions are paired
across the languages by number and must agree on the right answer.

The FAQs and the three legal pages (terms, privacy, refunds) are not in the
Markdown; they come in both languages from `pages/seed_content.py`.

Idempotent: the author, course and modules are matched by slug and number,
FAQs by their English question and legal pages by slug, and updated in place;
lessons and quiz questions are replaced. Everything is loaded in one
transaction, so an error leaves the database as it was.
"""

import re
from difflib import SequenceMatcher
from pathlib import Path

from django.conf import settings
from django.core.files import File
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils.text import slugify

from courses.models import (
    Author,
    Choice,
    Course,
    Lesson,
    LibraryFile,
    Module,
    Question,
    Quiz,
)
from manage_panel.forms import title_from_filename
from pages.models import Faq, LegalPage
from pages.seed_content import FAQS, LEGAL_PAGES

LANGUAGES = {"en": "English", "bn": "Bangla"}

COURSE = {
    "slug": "foundations-of-music",
    "title_en": "Foundations of Music",
    "title_bn": "সংগীতের ভিত্তি",
    "level_en": "Beginner",
    "level_bn": "প্রাথমিক",
    "price": 3500,
}

# Copied into media, so the seeded photo is served like one an editor uploads.
AUTHOR_PHOTO = Path(settings.BASE_DIR) / "static" / "img" / "instructor-640.jpg"

HEADING = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")
EMBED = re.compile(r"!\[\[([^\]|]+)(?:\|[^\]]*)?\]\]")
CALLOUT = re.compile(r"^(\s*>\s*)\[![a-z]+\][-+]?\s*", re.MULTILINE)
# "1. Which…", "**১. কোন…?**": Western or Bangla digits, bold or not.
QUESTION = re.compile(r"^\s*(?:\*\*)?\s*([0-9০-৯]+)\.\s+(.*?)\s*(?:\*\*)?\s*$")
CHOICE = re.compile(r"^\s*[-*]\s+(.*?)\s*$")
# "A.![[Q 5.18a.mp3]]": the letter is drawn by the quiz, so it is dropped.
CHOICE_LETTER = re.compile(r"^[A-H]\.\s*(?=!\[\[)")
CORRECT = "✓"
BANGLA_DIGITS = str.maketrans("০১২৩৪৫৬৭৮৯", "0123456789")


class SourceError(CommandError):
    """A course file is missing or does not follow the expected format."""


# -- reading the Markdown ----------------------------------------------------


def split_sections(text):
    """Split at level-1 headings into (title, body) pairs.

    Text before the first heading comes back with an empty title.
    """
    sections, title, lines = [], "", []
    for line in text.splitlines():
        match = HEADING.match(line)
        if match and len(match[1]) == 1:
            if title or "".join(lines).strip():
                sections.append((title, "\n".join(lines).strip()))
            title, lines = match[2], []
        else:
            lines.append(line)
    sections.append((title, "\n".join(lines).strip()))
    return sections


def shift_headings(text, levels):
    """Move every heading down `levels` levels.

    The lesson page's own <h1> is the module title, so the notes' `#`
    headings become `##`.
    """

    def shift(match):
        return f"{'#' * min(len(match[1]) + levels, 6)} {match[2]}"

    return "\n".join(HEADING.sub(shift, line) for line in text.splitlines())


def drop_title(text, title):
    """Remove a first-line heading that repeats the module title.

    The Bangla notes open with the module's name, sometimes spelt a little
    differently from the outline, so a close match counts.
    """
    first, _, rest = text.lstrip().partition("\n")
    match = HEADING.match(first)
    if match and SequenceMatcher(None, match[2], title).ratio() >= 0.8:
        return rest
    return text


def parse_outline(text, where):
    """[(number, title, [lesson, …]), …] from the `00` outline file."""
    modules = []
    for heading, body in split_sections(text):
        number, _, title = heading.partition("—")
        digits = re.sub(r"\D", "", number.translate(BANGLA_DIGITS))
        if not digits or not title.strip():
            continue  # The Bangla outline opens with a "contents" heading.
        lessons = [m[1] for m in map(CHOICE.match, body.splitlines()) if m]
        modules.append((int(digits), title.strip(), lessons))
    if not modules:
        raise SourceError(f"{where}: no “# Module N — Title” headings found.")
    return modules


def parse_checkpoint(text, where):
    """Split a `.PCQ.md` file into (checkpoint Markdown, [question, …]).

    Each question is {"text": …, "choices": [...], "correct": index}.
    """
    sections = split_sections(text)
    if len(sections) < 2:
        raise SourceError(f"{where}: no quiz heading found.")
    checkpoint = "\n\n".join(
        f"# {title}\n\n{body}" if title else body for title, body in sections[:-1]
    )
    return checkpoint.strip(), parse_quiz(sections[-1][1], where)


def parse_quiz(text, where):
    """[{"text": …, "choices": [...], "correct": index}, …] from the quiz section."""
    questions = []
    for line in text.splitlines():
        question = QUESTION.match(line)
        choice = CHOICE.match(line)
        if question:
            questions.append({"lines": [question[2]], "choices": [], "correct": []})
        elif not questions:
            continue
        elif choice:
            body = choice[1]
            current = questions[-1]
            if CORRECT in body:
                current["correct"].append(len(current["choices"]))
            body = " ".join(body.replace(CORRECT, " ").split())
            current["choices"].append(CHOICE_LETTER.sub("", body))
        elif line.strip() and not questions[-1]["choices"]:
            questions[-1]["lines"].append(line.strip())
    for number, item in enumerate(questions, start=1):
        if len(item["choices"]) < 2 or len(item["correct"]) != 1:
            raise SourceError(
                f"{where}, question {number}: needs two or more choices and exactly one ✓."
            )
        item["text"] = "\n\n".join(item.pop("lines"))
        item["correct"] = item["correct"][0]
    return questions


# -- the command -------------------------------------------------------------


class DryRun(Exception):
    """Raised to roll the transaction back after a successful dry run."""


class Command(BaseCommand):
    """Seed the course; see the module docstring for the file format."""

    help = "Load the Foundations of Music course, its author, FAQs and legal pages."

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # (title, extension) -> LibraryFile, and the embeds with no match.
        self.library = {}
        self.missing = set()

    def add_arguments(self, parser):
        parser.add_argument(
            "source",
            nargs="?",
            type=Path,
            help="Folder with the English and Bangla folders (default: MEDIA_ROOT/markup_content).",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Check the files and report what would load, then roll everything back.",
        )

    def handle(self, *args, **options):
        source = options["source"] or Path(settings.MEDIA_ROOT) / "markup_content"
        content = {lang: self._read(source, name) for lang, name in LANGUAGES.items()}
        self.library = {
            (item.title_en, item.extension): item for item in LibraryFile.objects.all()
        }
        try:
            with transaction.atomic():
                course = self._load(content)
                self._faqs()
                self._legal_pages()
                if self.missing:
                    raise CommandError(
                        "Not in the media library (run import_library first): "
                        + ", ".join(sorted(self.missing))
                    )
                # Counted here, before a dry run rolls the rows back.
                summary = (
                    f"“{course.title_en}” by {course.author.name_en}: "
                    f"{course.modules.count()} modules, "
                    f"{Lesson.objects.filter(module__course=course).count()} lessons, "
                    f"{Question.objects.filter(quiz__module__course=course).count()} "
                    f"quiz questions, {Faq.objects.count()} FAQs and "
                    f"{LegalPage.objects.count()} legal pages."
                )
                if options["dry_run"]:
                    raise DryRun
        except DryRun:
            prefix = "Dry run, nothing saved: "
        else:
            prefix = "Seeded "
        self.stdout.write(self.style.SUCCESS(prefix + summary))

    # -- files ---------------------------------------------------------------

    @staticmethod
    def _read(source, language):
        """{"outline": text, "modules": {n: text}, "quizzes": {n: text}, "closing": text}."""
        folders = sorted(source.glob(f"*{language}"))
        if not folders or not folders[0].is_dir():
            raise SourceError(f"No folder ending in “{language}” in {source}.")
        files = {"modules": {}, "quizzes": {}, "closing": ""}
        for path in sorted(folders[0].glob("*.md")):
            number = int(re.match(r"\d*", path.name)[0] or -1)
            text = path.read_text(encoding="utf-8")
            if number == 0:
                files["outline"] = text
            elif ".PCQ" in path.name:
                files["quizzes"][number] = text
            elif number > 0:
                files["modules"][number] = text
        if "outline" not in files:
            raise SourceError(f"{folders[0]}: no 00 outline file.")
        return files

    def _link(self, text):
        """Turn Obsidian embeds into media library links and callouts into quotes."""

        def library_markdown(match):
            name = match[1].strip()
            key = (title_from_filename(name), Path(name).suffix.lstrip(".").lower())
            item = self.library.get(key)
            if item is None:
                self.missing.add(name)
                return match[0]
            return item.markdown

        return CALLOUT.sub(r"\1", EMBED.sub(library_markdown, text))

    # -- loading -------------------------------------------------------------

    def _load(self, content):
        outlines = {
            lang: parse_outline(files["outline"], f"{LANGUAGES[lang]} outline")
            for lang, files in content.items()
        }
        if [m[0] for m in outlines["en"]] != [m[0] for m in outlines["bn"]]:
            raise SourceError("The English and Bangla outlines list different modules.")
        intro = {
            lang: split_sections(
                drop_title(files["modules"].get(1, ""), outlines[lang][0][1])
            )
            for lang, files in content.items()
        }
        for lang, sections in intro.items():
            if len(sections) < 3:
                raise SourceError(
                    f"{LANGUAGES[lang]} module 1: expected the instructor, the course "
                    "and what you will learn as its first three sections."
                )
        author = self._author(intro)
        course = self._course(intro, author)
        last = outlines["en"][-1][0]
        for en, bn in zip(outlines["en"], outlines["bn"]):
            self._module(course, content, {"en": en, "bn": bn}, closing=en[0] == last)
        return course

    def _author(self, intro):
        """The instructor's name (the first bold text) and bio from module 1."""
        fields = {}
        for lang, sections in intro.items():
            bio = sections[0][1]
            name = re.search(r"\*\*(.+?)\*\*", bio)
            if not name:
                raise SourceError(
                    f"{LANGUAGES[lang]} module 1: no **name** in the intro."
                )
            fields[f"name_{lang}"] = name[1]
            fields[f"bio_{lang}"] = self._link(bio)
        author, _ = Author.objects.update_or_create(
            slug=slugify(fields["name_en"]), defaults=fields
        )
        # Keep a photo an editor uploaded; only fill in a missing one.
        has_photo = author.photo and author.photo.storage.exists(author.photo.name)
        if not has_photo and AUTHOR_PHOTO.exists():
            with AUTHOR_PHOTO.open("rb") as source:
                author.photo.save(f"{author.slug}.jpg", File(source), save=True)
        return author

    def _course(self, intro, author):
        """Summary from the "About" callout; description from the rest of
        "About" and the "What you will learn" list."""
        fields = {**COURSE, "status": Course.Status.PUBLISHED, "author": author}
        for lang, sections in intro.items():
            about, learn_title, learn = sections[1][1], sections[2][0], sections[2][1]
            callout = CALLOUT.search(about)
            if not callout:
                raise SourceError(
                    f"{LANGUAGES[lang]} module 1: no [!info] line under “About”."
                )
            line_end = about.find("\n", callout.end())
            line_end = len(about) if line_end == -1 else line_end
            fields[f"summary_{lang}"] = about[callout.end() : line_end].strip()
            rest = (about[: callout.start()] + about[line_end:]).strip()
            fields[f"description_{lang}"] = self._link(
                f"{rest}\n\n## {learn_title}\n\n{learn}"
            )
        course, _ = Course.objects.update_or_create(
            slug=COURSE["slug"], defaults=fields
        )
        return course

    def _module(self, course, content, outline, closing):
        number = outline["en"][0]
        fields = {
            "slug": slugify(outline["en"][1]),
            "access": Module.Access.FREE if number == 1 else Module.Access.PAID,
            "status": Module.Status.PUBLISHED,
        }
        quizzes = {}
        for lang, (_, title, _) in outline.items():
            notes, quiz = self._notes(content[lang], number, title, closing, lang)
            fields[f"title_{lang}"] = title
            fields[f"notes_markdown_{lang}"] = notes
            if quiz is not None:
                quizzes[lang] = quiz
        module, _ = Module.objects.update_or_create(
            course=course, number=Module.pad_number(number), defaults=fields
        )
        self._lessons(module, outline)
        if quizzes:
            self._quiz(module, quizzes)
        else:
            # Without questions the student marks the module complete instead.
            Quiz.objects.filter(module=module).delete()

    def _notes(self, files, number, title, closing, lang):
        """A module's notes (lesson, checkpoint, closing) and its quiz or None."""
        notes = shift_headings(drop_title(files["modules"].get(number, ""), title), 1)
        parts, quiz = [notes.strip()], None
        if number in files["quizzes"]:
            where = f"{LANGUAGES[lang]} module {number}"
            checkpoint, quiz = parse_checkpoint(files["quizzes"][number], where)
            parts.append(checkpoint)
        if closing:
            parts += [
                text.strip()
                for n, text in sorted(files["modules"].items())
                if n > number
            ]
        return self._link("\n\n---\n\n".join(p for p in parts if p)), quiz

    @staticmethod
    def _lessons(module, outline):
        en, bn = outline["en"][2], outline["bn"][2]
        if len(en) != len(bn):
            raise SourceError(
                f"Module {module.number_plain}: the English outline lists {len(en)} "
                f"lessons and the Bangla one {len(bn)}."
            )
        module.lessons.all().delete()
        Lesson.objects.bulk_create(
            Lesson(module=module, title_en=title_en, title_bn=title_bn, position=index)
            for index, (title_en, title_bn) in enumerate(zip(en, bn))
        )

    def _quiz(self, module, quizzes):
        where = f"Module {module.number_plain} quiz"
        en, bn = quizzes.get("en", []), quizzes.get("bn", [])
        if len(en) != len(bn):
            raise SourceError(
                f"{where}: {len(en)} English questions, {len(bn)} Bangla."
            )
        quiz, _ = Quiz.objects.get_or_create(module=module)
        quiz.questions.all().delete()
        for position, (q_en, q_bn) in enumerate(zip(en, bn)):
            here = f"{where}, question {position + 1}"
            if len(q_en["choices"]) != len(q_bn["choices"]):
                raise SourceError(
                    f"{here}: the languages have different numbers of choices."
                )
            if q_en["correct"] != q_bn["correct"]:
                raise SourceError(f"{here}: the languages mark different answers ✓.")
            question = Question.objects.create(
                quiz=quiz,
                position=position,
                text_en=self._link(q_en["text"]),
                text_bn=self._link(q_bn["text"]),
            )
            Choice.objects.bulk_create(
                Choice(
                    question=question,
                    position=index,
                    text_en=self._link(text_en),
                    text_bn=self._link(text_bn),
                    is_correct=index == q_en["correct"],
                )
                for index, (text_en, text_bn) in enumerate(
                    zip(q_en["choices"], q_bn["choices"])
                )
            )

    # -- site content --------------------------------------------------------

    @staticmethod
    def _faqs():
        for position, fields in enumerate(FAQS):
            Faq.objects.update_or_create(
                question_en=fields["question_en"],
                defaults={**fields, "position": position, "is_published": True},
            )

    @staticmethod
    def _legal_pages():
        for slug, fields in LEGAL_PAGES.items():
            LegalPage.objects.update_or_create(
                slug=slug, defaults={**fields, "is_published": True}
            )

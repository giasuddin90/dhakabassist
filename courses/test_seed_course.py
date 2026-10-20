"""The `seed_course` command: loads the course from its Markdown files."""

import shutil
import tempfile
from io import StringIO
from pathlib import Path

from django.conf import settings
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import CommandError, call_command
from django.test import TestCase, override_settings

from courses.models import Author, Course, LibraryFile, Module

ENGLISH = {
    "00. Course Outline.md": """\
# Module 1 — Getting Started #
- Instructor Intro
- About This Course
- What You Will Learn
# Module 2 — Understanding Sound #
- What is Pitch?
""",
    "01. Getting Started.md": """\
# Instructor Intro

Hi. I’m **Tanveer Haque**.

---
# About This Course

> [!info] This course gives you a strong start in music.

It is hands-on.

---
# What You Will Learn

- The basics of sound
""",
    "02. Understanding Sound.md": """\
# What is Pitch?

![[Diagram 2.1.svg]]
""",
    "02.PCQ.md": """\
## Performance Checkpoint

### **Exercise 1 — Match Pitch**

- Play one note

---
# Quiz

1. Which two white keys have no black key between them?
-  A — B
-  B — C ✓

2. Which note sounds higher?
![[Q 2.17.mp3]]
- A.![[Q 2.17.mp3]]
- First
- Second ✓
""",
    "10.md": ">Thank you for taking this course.\n",
}

BANGLA = {
    "00.md": """\
# সূচিপত্র

# মডিউল ১ — শুরু করা

- প্রশিক্ষকের পরিচিতি
- এই কোর্স সম্পর্কে
- আপনি যা শিখবেন

# মডিউল ২ — শব্দ বোঝা

- পিচ কি?
""",
    "01.md": """\
# শুরু করা  #

# প্রশিক্ষকের পরিচিতি

হাই। আমি **তানভীর হক**।

# এই কোর্স সম্পর্কে

> [!info] এই কোর্স আপনাকে সঙ্গীতে একটি শক্তিশালী শুরু দেবে।

# আপনি যা শিখবেন

- শব্দের মৌলিক ধারণা
""",
    "02.md": """\
# শব্দ বোঝা

# পিচ কী?

![[Diagram 2.1.svg]]
""",
    "02.PCQ.md": """\
## পারফরম্যান্স চেকপয়েন্ট

# কুইজ

**১. কোন দুইটি সাদা কী-এর মাঝে কোনো কালো কী নেই?**

- A — B
- B — C ✓

**২. কোন নোটটি উঁচু শোনায়?**
![[Q 2.17.mp3]]
	- A.![[Q 2.17.mp3]]
	- প্রথম
	- দ্বিতীয় ✓
""",
    "10.md": ">ধন্যবাদ।\n",
}


def run(source, **options):
    out = StringIO()
    call_command("seed_course", str(source), stdout=out, **options)
    return out.getvalue()


@override_settings(MEDIA_ROOT=Path(tempfile.mkdtemp()))
class SeedCourseTests(TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.source = Path(folder.name)
        self.write("A1_FoM_English", ENGLISH)
        self.write("A2_FoM_Bangla", BANGLA)
        self.diagram = LibraryFile.objects.create(
            title_en="Diagram 2.1",
            file=SimpleUploadedFile("Diagram 2.1.svg", b"<svg></svg>"),
        )
        self.audio = LibraryFile.objects.create(
            title_en="Q 2.17", file=SimpleUploadedFile("Q 2.17.mp3", b"ID3")
        )

    def tearDown(self):
        shutil.rmtree(settings.MEDIA_ROOT, ignore_errors=True)

    def write(self, name, files):
        (self.source / name).mkdir()
        for filename, text in files.items():
            (self.source / name / filename).write_text(text, encoding="utf-8")

    def test_loads_author_course_modules_and_lessons_in_both_languages(self):
        output = run(self.source)
        self.assertIn("2 modules, 4 lessons, 2 quiz questions", output)
        author = Author.objects.get()
        self.assertEqual(
            (author.name_en, author.name_bn), ("Tanveer Haque", "তানভীর হক")
        )
        course = Course.objects.get(slug="foundations-of-music")
        self.assertEqual(course.author, author)
        self.assertEqual(course.status, Course.Status.PUBLISHED)
        self.assertEqual(
            course.summary_en, "This course gives you a strong start in music."
        )
        self.assertIn("## What You Will Learn", course.description_en)
        first, second = course.modules.all()
        self.assertEqual(first.access, Module.Access.FREE)
        self.assertEqual(second.access, Module.Access.PAID)
        self.assertEqual(
            (second.title_en, second.title_bn), ("Understanding Sound", "শব্দ বোঝা")
        )
        self.assertEqual(
            list(first.lessons.values_list("title_en", "title_bn"))[2],
            ("What You Will Learn", "আপনি যা শিখবেন"),
        )

    def test_notes_link_the_library_and_include_checkpoint_and_closing(self):
        run(self.source)
        module = Module.objects.get(number="02")
        self.assertTrue(module.notes_markdown_bn.startswith("## পিচ কী?"))
        self.assertIn(self.diagram.markdown, module.notes_markdown_en)
        self.assertIn("## Performance Checkpoint", module.notes_markdown_en)
        self.assertNotIn("[[", module.notes_markdown_en)
        self.assertTrue(
            module.notes_markdown_en.endswith(">Thank you for taking this course.")
        )
        self.assertNotIn("Quiz", module.notes_markdown_en)

    def test_quiz_pairs_languages_and_marks_the_right_answer(self):
        run(self.source)
        question = Module.objects.get(number="02").quiz.questions.get(position=1)
        self.assertEqual(
            question.text_en, f"Which note sounds higher?\n\n{self.audio.markdown}"
        )
        choices = list(question.choices.all())
        self.assertEqual(choices[0].text_en, self.audio.markdown)
        self.assertEqual((choices[2].text_en, choices[2].text_bn), ("Second", "দ্বিতীয়"))
        self.assertEqual([c.is_correct for c in choices], [False, False, True])
        self.assertFalse(hasattr(Module.objects.get(number="01"), "quiz"))

    def test_rerunning_updates_in_place(self):
        run(self.source)
        run(self.source)
        self.assertEqual(Course.objects.count(), 1)
        self.assertEqual(Module.objects.count(), 2)
        self.assertEqual(Module.objects.get(number="02").quiz.questions.count(), 2)

    def test_dry_run_saves_nothing(self):
        output = run(self.source, dry_run=True)
        self.assertIn("Dry run", output)
        self.assertFalse(Course.objects.exists())

    def test_missing_library_file_aborts(self):
        self.audio.delete()
        with self.assertRaisesMessage(CommandError, "Q 2.17.mp3"):
            run(self.source)
        self.assertFalse(Course.objects.exists())

    def test_languages_disagreeing_on_the_answer_abort(self):
        path = self.source / "A2_FoM_Bangla" / "02.PCQ.md"
        path.write_text(
            path.read_text(encoding="utf-8")
            .replace("- A — B", "- A — B ✓")
            .replace("- B — C ✓", "- B — C"),
            encoding="utf-8",
        )
        with self.assertRaisesMessage(CommandError, "different answers"):
            run(self.source)

"""Load the Foundations of Music course, FAQs and legal pages.

Idempotent: run it again after a schema change and it updates in place rather
than duplicating. Content comes from the supplied design, so the site looks
like the reference immediately.
"""

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils.text import slugify

from courses.models import Choice, Course, Lesson, Module, Question, Quiz
from pages.models import Faq, LegalPage

User = get_user_model()

MODULES = [
    (
        "01", "Sound", "",
        "What sound is, how pitch, volume and tone colour work, and the words "
        "musicians use to describe them.",
        ["What is sound?", "Pitch and frequency", "Timbre and dynamics"],
        740, Module.Access.FREE,
    ),
    (
        "02", "Notation", "স্বরলিপি",
        "The staff, clefs and note names. Read notes on the treble and bass clef with confidence.",
        ["The staff and clefs", "Note names", "Ledger lines"],
        902, Module.Access.PAID,
    ),
    (
        "03", "Rhythm", "ছন্দ",
        "Note values, rests and the beat. Count and clap rhythms from whole notes to sixteenths.",
        ["Note values", "Rests", "Dotted notes and ties"],
        851, Module.Access.PAID,
    ),
    (
        "04", "Meter and Time Signatures", "তাল ও মাত্রা",
        "How bars are organised, simple and compound meter, and how to read a time signature.",
        ["Bars and bar lines", "Reading time signatures", "Simple vs compound meter"],
        965, Module.Access.PAID,
    ),
    (
        "05", "Intervals", "স্বরান্তর",
        "The distance between two notes. Name, hear and build intervals from a unison to an octave.",
        ["Half and whole steps", "Interval numbers", "Interval quality"],
        1120, Module.Access.PAID,
    ),
    (
        "06", "Major Scales", "মেজর স্কেল",
        "The pattern of whole and half steps behind every major scale, and how to build one from any note.",
        ["The major scale pattern", "Building scales", "Scale degrees"],
        930, Module.Access.PAID,
    ),
    (
        "07", "Keys and Key Signatures", "কী ও কী সিগনেচার",
        "What a key is, how sharps and flats appear in a key signature and how to "
        "identify the key of a piece.",
        ["What is a key?", "Sharp keys", "Flat keys"],
        1032, Module.Access.PAID,
    ),
    (
        "08", "The Circle of Fifths", "পঞ্চম বৃত্ত",
        "A map of every key. Use the circle to find key signatures and related keys quickly.",
        ["Moving in fifths", "Reading the circle", "Relative keys"],
        888, Module.Access.PAID,
    ),
    (
        "09", "Minor Scales", "মাইনর স্কেল",
        "Natural, harmonic and melodic minor scales and how each relates to its major key.",
        ["Natural minor", "Harmonic minor", "Melodic minor"],
        1145, Module.Access.PAID,
    ),
]

MODULE_4_NOTES = """\
## What a time signature tells you

Music is organised into bars (also called measures). The time signature at the
start of a piece tells you how many beats are in each bar, and which note value
counts as one beat.

In **4/4**, the top number says there are four beats per bar. The bottom
number, 4, says a quarter note gets one beat.

Listen to the examples in the Audio tab and count along. Notice how the first
beat of every bar feels slightly stronger.

## Simple and compound meter

In *simple* meter each beat divides into two. In *compound* meter each beat
divides into three — 6/8 counted in two is the clearest example.

- **2/4** — two beats per bar, duple
- **3/4** — three beats per bar, the waltz
- **4/4** — four beats per bar, also written as C for common time
- **6/8** — two beats per bar, each divided into three
"""

MODULE_1_NOTES = """\
## What sound actually is

A sound is a vibration travelling through air. When a bass string moves back
and forth it pushes the air around it, and that pressure wave reaches your ear.
Everything else in music theory describes properties of that wave.

## Pitch

How fast the string vibrates decides the **pitch** — how high or low a note
sounds. Vibrations are measured in hertz (Hz), one hertz being one cycle per
second. The A above middle C is usually tuned to 440 Hz.

Double the frequency and you get the same note one octave higher: 880 Hz is
also an A.

## Volume and tone colour

**Dynamics** describe how loud a note is; **timbre** describes its character —
why a bass and a piano playing the same note still sound like different
instruments. Timbre comes from the quieter frequencies sounding above the main
one, called overtones.
"""

QUIZ_4 = [
    (
        "In 4/4 time, how many quarter-note beats are in each bar?",
        ["Two", "Three", "Four", "Eight"],
        2,
        "The top number of a time signature counts the beats in each bar — four in 4/4.",
    ),
    (
        "What does the bottom number of a time signature tell you?",
        [
            "How many bars are in the piece",
            "Which note value gets one beat",
            "How fast to play",
            "How many beats are in each bar",
        ],
        1,
        "The bottom number names the beat unit: 4 means a quarter note, 8 means an eighth note.",
    ),
    (
        "A bar divides into two beats, and each beat divides into three. Which meter is that?",
        ["2/4 — simple duple", "6/8 — compound duple", "3/4 — simple triple", "4/4 — simple quadruple"],
        1,
        "Two beats per bar makes it duple; each beat dividing into three makes it compound.",
    ),
]

QUIZ_1 = [
    (
        "What is a sound, physically?",
        [
            "A vibration travelling through air",
            "A change in air temperature",
            "A magnetic field",
            "A kind of light",
        ],
        0,
        "Sound is a pressure wave: a vibration moving through a medium such as air.",
    ),
    (
        "A note sounds at 440 Hz. What is the frequency of the same note one octave higher?",
        ["220 Hz", "444 Hz", "660 Hz", "880 Hz"],
        3,
        "An octave up doubles the frequency, so 440 Hz becomes 880 Hz.",
    ),
    (
        "Which word describes why a bass and a piano playing the same note still sound different?",
        ["Pitch", "Timbre", "Dynamics", "Tempo"],
        1,
        "Timbre is tone colour — the pattern of overtones that gives an instrument its character.",
    ),
]

FAQS = [
    (
        "Do I need to know how to read music?",
        "No. The course starts from the very beginning and assumes no prior knowledge.",
    ),
    (
        "Can I try the course before buying?",
        "Yes. Create a free account and Module 1 is yours, including its video, notes, audio "
        "and quiz. Enroll when you want to continue to Module 2.",
    ),
    (
        "How long do I have access?",
        "Lifetime access. Study at your own pace and return whenever you like.",
    ),
    (
        "How do I pay?",
        "bKash, Nagad, Visa and Mastercard. International cards are also accepted. You are "
        "enrolled automatically once payment is confirmed.",
    ),
    (
        "Can I get a refund?",
        "Yes, within 7 days of purchase if you have completed fewer than two modules. "
        "See the Refund Policy for details.",
    ),
    (
        "Will there be more courses?",
        "Part 2 of Foundations of Music is in production. Students who finish Part 1 will be "
        "offered it first.",
    ),
]

LEGAL = {
    "terms": (
        "Terms & Conditions",
        "The terms under which DhakaBassist sells and delivers its online music theory courses.",
        """\
## Who we are

DhakaBassist is operated by Tanveer Haque, Dhaka, Bangladesh. These terms apply
to every purchase made through this website.

## Your account

You are responsible for keeping your password confidential and for activity on
your account. One account is for one person; course access may not be shared,
resold or transferred.

## The course

Enrolment grants you a personal, non-transferable licence to study the course
material for as long as the course remains available on this platform. Videos,
audio, notation, written notes and worksheets remain the copyright of Tanveer
Haque. You may download the worksheets provided for your own study. You may not
redistribute, publish, resell or publicly perform any part of the course.

## Payment

Prices are in Bangladeshi Taka and include any gateway fee. Payment is handled
by our payment provider; we never receive or store your card details. Access is
granted automatically once payment is confirmed.

## Availability

We aim to keep the platform available at all times, but we do not guarantee
uninterrupted access. Course content may be corrected, improved or extended.

## Changes

We may update these terms. Material changes will be announced on this page, and
the date below always shows when the terms last changed.

## Contact

Questions about these terms: hello@dhakabassist.com
""",
    ),
    "privacy": (
        "Privacy Policy",
        "What personal data DhakaBassist collects, why, and how long it is kept.",
        """\
## What we collect

- **Your account**: name, email address and a hashed password. Passwords are
  stored as one-way hashes and cannot be read by us.
- **Your learning**: which modules you have opened and completed, your quiz
  answers and where you paused a video, so your progress is there next time.
- **Your orders**: the amount, the method you chose and the reference our
  payment provider returns. We never receive or store your card number.
- **Technical data**: server logs holding IP address and browser, kept briefly
  for security and troubleshooting.

## Why we collect it

To give you access to what you bought, to show your progress, to answer support
questions and to meet our accounting obligations. We do not sell your data and
we do not share it for advertising.

## Who else processes it

Our payment provider processes your payment. Our hosting and email providers
process data on our behalf under contract. Course videos may be delivered by a
streaming provider.

## How long we keep it

Account and progress data for as long as your account exists. Order records for
as long as tax law requires. You may ask us to delete your account at any time;
order records are retained where we are legally required to keep them.

## Your rights

You can see and correct your details in your account settings, download a copy
of your data, or ask us to delete your account. Email hello@dhakabassist.com and
we will reply within two working days.

## Cookies

We use one session cookie to keep you signed in and one cookie to protect forms
against cross-site request forgery. Neither is used for tracking or
advertising.
""",
    ),
    "refunds": (
        "Refund Policy",
        "When a DhakaBassist course purchase can be refunded, and how to ask.",
        """\
## The short version

You can have your money back within **7 days** of purchase if you have
completed **fewer than two modules**.

## Why that condition

Module 1 is free precisely so you can decide before paying. Once several modules
have been studied, the material has been delivered.

## How to request a refund

Email hello@dhakabassist.com from the address on your account, quoting your
order number. You do not need to give a reason. We reply within two working
days.

## How the money is returned

Refunds go back to the original payment method through our payment provider.
bKash and Nagad usually settle within a few working days; card refunds can take
up to ten, depending on your bank.

## Exceptions

We will consider a refund outside these conditions if the platform failed in a
way that prevented you from studying, or where a payment was made in error or
duplicated. Nothing here limits any statutory right you have.
""",
    ),
}


class Command(BaseCommand):
    help = "Load the Foundations of Music course, FAQs and legal pages."

    def add_arguments(self, parser):
        parser.add_argument(
            "--with-admin",
            action="store_true",
            help="Also create a staff account (prompts for the password).",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        course = self._course()
        self._modules(course)
        self._part_two(course)
        self._faqs()
        self._legal()
        if options["with_admin"]:
            self._admin()
        self.stdout.write(
            self.style.SUCCESS(
                f"Seeded “{course.title}” with {course.modules.count()} modules, "
                f"{Faq.objects.count()} FAQs and {LegalPage.objects.count()} legal pages."
            )
        )

    # -- course ------------------------------------------------------------

    def _course(self):
        course, _ = Course.objects.update_or_create(
            slug="foundations-of-music",
            defaults={
                "title": "Foundations of Music",
                "subtitle": "Part 1",
                "summary": (
                    "A music theory course by Tanveer Haque. Nine clear modules take you from "
                    "the basics of sound to scales, keys and the circle of fifths, at your own "
                    "pace. The first module is free."
                ),
                "description": (
                    "A complete beginner course in music theory. Start with what sound is and "
                    "finish able to read notation, count rhythms, name intervals, build major "
                    "and minor scales and find your way around the circle of fifths."
                ),
                "level": "Beginner",
                "price": 3500,
                "status": Course.Status.PUBLISHED,
                "trailer_label": "Watch the trailer",
                "trailer_duration": "2:10",
                "position": 0,
                "meta_title": "Foundations of Music — online music theory course",
                "meta_description": (
                    "Nine-module online music theory course by Tanveer Haque. Module 1 free, "
                    "lifetime access for ৳3,500. bKash, Nagad and card accepted."
                ),
            },
        )
        return course

    def _modules(self, course):
        for position, row in enumerate(MODULES):
            number, title, title_bn, summary, lessons, duration, access = row
            notes = {"01": MODULE_1_NOTES, "04": MODULE_4_NOTES}.get(number, "")
            module, _ = Module.objects.update_or_create(
                course=course,
                number=number,
                defaults={
                    "slug": slugify(title),
                    "position": position,
                    "title": title,
                    "title_bn": title_bn,
                    "summary": summary,
                    "notes_markdown": notes,
                    "access": access,
                    "status": Module.Status.PUBLISHED,
                    "video_provider": "protected_file",
                    "video_uid": f"foundations-of-music/module-{number}.mp4",
                    "video_duration_seconds": duration,
                    "video_has_subtitles": True,
                },
            )
            module.lessons.all().delete()
            Lesson.objects.bulk_create(
                Lesson(module=module, title=title_, position=index)
                for index, title_ in enumerate(lessons)
            )
            questions = {"01": QUIZ_1, "04": QUIZ_4}.get(number)
            if questions:
                self._quiz(module, questions)

    @staticmethod
    def _quiz(module, rows):
        quiz, _ = Quiz.objects.update_or_create(
            module=module,
            defaults={
                "title": f"Module {module.number.lstrip('0')} quiz",
                "require_perfect_score": True,
                "allow_unlimited_retries": True,
            },
        )
        quiz.questions.all().delete()
        for position, (text, options, answer, explanation) in enumerate(rows):
            question = Question.objects.create(
                quiz=quiz, text=text, position=position, explanation=explanation
            )
            Choice.objects.bulk_create(
                Choice(
                    question=question,
                    text=option,
                    position=index,
                    is_correct=index == answer,
                )
                for index, option in enumerate(options)
            )

    def _part_two(self, part_one):
        """A draft Part 2, so the prerequisite model is visible in the admin."""
        Course.objects.update_or_create(
            slug="foundations-of-music-part-2",
            defaults={
                "title": "Foundations of Music",
                "subtitle": "Part 2",
                "summary": (
                    "The second part of Foundations of Music: chords, harmony and how the "
                    "theory you have learned turns into music you can play."
                ),
                "description": "In production. Available to students who have completed Part 1.",
                "level": "Intermediate",
                "price": 3500,
                "status": Course.Status.DRAFT,
                "requires": part_one,
                "position": 1,
            },
        )

    # -- site content ------------------------------------------------------

    def _faqs(self):
        for position, (question, answer) in enumerate(FAQS):
            Faq.objects.update_or_create(
                question=question,
                defaults={"answer": answer, "position": position, "is_published": True},
            )

    def _legal(self):
        for slug, (title, description, body) in LEGAL.items():
            LegalPage.objects.update_or_create(
                slug=slug,
                defaults={
                    "title": title,
                    "meta_description": description,
                    "body_markdown": body,
                    "is_published": True,
                },
            )

    def _admin(self):
        email = input("Staff email: ").strip()
        if User.objects.filter(email__iexact=email).exists():
            self.stdout.write(self.style.WARNING(f"{email} already exists; skipping."))
            return
        from django.core.management import call_command

        call_command("createsuperuser", email=email, interactive=True)

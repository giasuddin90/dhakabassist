# Running the course

Everything here is done at `/manage/`, signed in as a staff account. No
developer is needed for any of it.

## The panel

| Page | What it is for |
| --- | --- |
| Overview | Paying students, free accounts, revenue, how far students get, recent orders |
| Courses | Create and edit courses; add, reorder and edit modules |
| Media library | Upload audio, diagrams and handouts once; copy their links into lesson notes |
| Quizzes | Every module's quiz, with question counts |
| Students | Search, see progress, suspend or restore access, grant access |
| Orders | Every order, filtered by status |
| Site content | FAQs, the three legal pages, and contact messages |

Deeper or one-off edits live in **Database admin** (`/django-admin/`), linked
at the bottom of the sidebar.

## Editing a module

**Courses → pick the course → Edit** on a module row.

The left column is the module itself: its number, title, Bangla title, web
address, whether it is free or paid, whether it is published, the video, and
the lesson notes. The right column holds the media panels and the quiz.

**Access** is the paywall switch. "Free preview" means any registered account
can study it; "Paid" means enrolled students only. Module 1 is the free
preview; everything after it is paid.

**Status** controls whether students see the module at all. A draft module is
invisible to students and does not count towards their progress, so you can
prepare a module in public without anyone finding it.

**Lesson notes** are Markdown. The toolbar inserts the common pieces:

| Button | Produces |
| --- | --- |
| H2 | A section heading |
| B / I | **Bold** / *italic* |
| List | A bullet point |
| Link | A link |
| Image | A notation image |
| Audio | An audio player |

Save with **Save changes**. **Preview as student** opens the real lesson page
exactly as a student sees it.

## Adding audio, notation and worksheets

Each panel on the right of the module editor takes one file at a time: give it
a title, choose the file, press Upload.

- **Audio (MP3)** — the examples students play in the Audio tab. Add the
  duration in seconds so it shows beside the player.
- **Notation and diagrams (SVG)** — figures used inside the lesson notes.
  These need **alt text**: one sentence describing the figure, for students
  using a screen reader. The form will not accept the upload without it.
- **Downloads (PDF)** — worksheets and charts, listed in the Downloads tab.

Uploaded files are stored privately. They are only ever served to a student
who has access to that module, so a worksheet link cannot be passed around.

## The media library

The library is one place for all lesson files: MP3, M4A, OGG and WAV audio;
SVG, PNG, JPG, WEBP and GIF images; and PDF handouts.

1. **Media library → Upload files.** Choose a folder (such as "Lesson
   material" or "Module 3"), or type a new name to start one, then pick as
   many files as you like.
2. Press **Copy** beside a file's Markdown.
3. Paste it into any module's lesson notes and save.

The Markdown looks like `![C major scale](/library/…/c-major-scale.mp3)`.
Audio becomes a player and images become figures. PDFs become a download
link. The words in square brackets are what a screen reader announces, so for
a diagram write what it shows.

Each file lists the modules that use it. A file only opens for a student who
can open one of those modules, so paid material stays paid. A file that no
lesson links to yet is visible only to staff. A file linked from a published
course description is public, because that page is public.

## Editing a quiz

**Quizzes**, or **Edit quiz** from the module editor.

Questions are edited one at a time; pick one from the list on the left. Each
question has four options, and you mark the correct one with the radio button
beside it. The explanation is optional and is shown once the student picks
correctly.

**Rules** control the quiz as a whole:

- *Require 100% to unlock the next module* — on by default, as the course is
  designed. Turning it off lets students move on regardless.
- *Allow unlimited retries* — lets a student retake a finished quiz.

Students may keep trying a question until they choose the right answer; the
wrong ones are struck through as they go. The platform records how many were
right first time, so the score shows real understanding without blocking
anyone.

## Reordering modules

On the Courses page, drag a row by the handle on its left, then press
**Save order**. The order you see is the order students see.

## Students

Search by name or email. Each row shows how far that student has got and when
they were last active.

**Access** suspends or restores a student. A suspended student keeps their
account and their order history but loses paid material immediately — use it
for a refund or a disputed payment rather than deleting anything.

**Grant access** enrols someone without a payment: a replacement for a failed
order, a comp, or a fix after a support conversation. Granted enrolments are
marked as such, so they are distinguishable from paid ones later.

## Orders

Filter by All, Pending, Paid, Failed or Refunded. Each row shows the payment
method and the gateway's own reference, which is what you quote when asking
the provider about a payment.

**Refunds are issued in the payment gateway, not here.** Refund there first,
then record it on the order in Database admin, and suspend the student's
access if the refund means they should lose it.

## Site content

**FAQs** appear on the home page and the FAQ page, in the order given, and are
also published as structured data so search engines can show them directly.

**Legal pages** — Terms, Privacy, Refund Policy — are Markdown and are edited
here. Each shows its own "last updated" date to students automatically.

**Contact messages** are what the website form collects. Mark one handled when
you have replied; the count beside "Site content" shows what is outstanding.

## Adding a second course

Create it under **Courses → New course**. Set **Requires** to Part 1 if
students must own Part 1 first — the checkout then refuses anyone who does
not, and points them at Part 1 instead. Leave it empty for a course anyone can
buy.

Keep a course as **Draft** until its modules are ready; draft courses are
invisible to students and absent from the sitemap.

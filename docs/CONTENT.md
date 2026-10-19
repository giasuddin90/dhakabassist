# Running the course

Everything here is done at `/manage/`, signed in as a staff account. No
developer is needed for any of it.

## The panel

| Page | What it is for |
| --- | --- |
| Overview | Paying students, free accounts, revenue, how far students get, recent orders |
| Courses | Create and edit courses; add, reorder and edit modules |
| Media library | Upload audio, diagrams and handouts once; copy their links into lesson notes and quizzes |
| Quizzes | Every module's quiz, with question counts |
| Students | Search, see progress, suspend or restore access, grant access |
| Orders | Every order, filtered by status |
| Site content | FAQs, the three legal pages, and contact messages |

Deeper or one-off edits live in **Database admin** (`/django-admin/`), linked
at the bottom of the sidebar.

## Two languages

Everything students read is stored in Bangla and English. Each editor shows
the two side by side: **Bangla** on the left (on top on a phone),
**English** on the right. Bangla is the site's main language; English pages
live under `/en/`.

- A field that is required needs **at least one** of the two. Leave the other
  blank and that language's page shows the one you filled in, so nothing is
  ever empty. Content from before the site was bilingual is in the English
  boxes; add the Bangla when you are ready.
- Media works the same way. A module can have a Bangla video and an English
  one; with only one, both languages play it. A course can have a trailer
  per language.
- Web addresses (slugs) are shared and made from the English title, because
  Bangla letters cannot go in an address. With no English title, type the
  slug yourself.
- Media library files carry a **Language**: *Both languages* (the default),
  *Bangla only* or *English only*. It decides which language's lesson page
  lists the file under Downloads. Links you paste into the notes work
  whatever it says, so put Bangla handouts in the Bangla notes.
- Emails (receipts, welcome links) go out in the student's language, which
  they choose under Account settings and which starts as the language they
  signed up in.

## Editing a module

**Courses → pick the course → Edit** on a module row.

The left column is the module itself: its number, web address, title and
summary in both languages, the lesson notes in both languages, the video (one
per language), whether it is free or paid, and whether it is published. The right column holds the media panels and the quiz.

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

The library is one place for every course file, sorted into three kinds of
material:

- **Lesson material** — audio, diagrams and figures for the lesson notes.
- **Quiz material** — clips and diagrams for quiz questions and answers.
- **Download material** — worksheets, handouts, backing tracks and tabs that
  students save. These are always a download link, even an MP3.

Accepted files: MP3, M4A, OGG and WAV audio; SVG, PNG, JPG, WEBP and GIF
images; PDF, Word, PowerPoint, Excel, OpenDocument, TXT, RTF and CSV
documents; MIDI, MusicXML, Guitar Pro and MuseScore scores; and ZIP archives.
Up to 50 MB each.

1. **Media library → Upload files.** Choose the material, then a folder
   (such as "Module 3"), or type a new name to start one, then pick as many
   files as you like.
2. Press **Copy** beside a file's Markdown.
3. Paste it into any module's lesson notes, or anywhere in a quiz (title,
   question, answer option or explanation), and save.

The tabs at the top of the library show one kind of material at a time.

The Markdown looks like `![C major scale](/library/…/c-major-scale.mp3)`.
Audio becomes a player and images become figures. Download material and
every document, score or ZIP becomes a download link. The words in square brackets are what a screen reader announces, so for
a diagram write what it shows.

Each file lists the modules that use it. A file only opens for a student who
can open one of those modules, so paid material stays paid. A link in a
quiz counts as a link from its module. A file that no lesson or quiz links to yet is visible only to staff. A file linked from a published
course description is public, because that page is public.

## Editing a quiz

A module with a quiz is complete once the student passes it. A module
without a quiz (or whose quiz has no questions yet) shows a **Mark as
complete** button at the end of the lesson instead, so the next module still
opens. Add questions and the button gives way to the quiz.

**Quizzes**, or **Edit quiz** from the module editor.

Questions are edited one at a time; pick one from the list on the left. Each
question has four options, and you mark the correct one with the radio button
beside it. The explanation is optional and is shown once the student picks
correctly.

The quiz title, questions, answer options and explanations all accept
Markdown, so audio and diagrams from the media library can go anywhere in a
quiz. Paste the file's Markdown where it should appear: in a question it shows
where you put it; in an answer option the image appears inside the option and
an audio player sits just above it (a player inside the option would choose
that answer when pressed).

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

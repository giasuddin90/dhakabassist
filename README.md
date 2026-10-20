# DhakaBassist

A learning platform for *Foundations of Music*, a nine-module music theory
course by Tanveer Haque. Students discover the course, study Module 1 free,
pay once in BDT, and work through the remaining modules; each one unlocks when
the previous module's quiz has been answered correctly, or, for a module
without a quiz, when the student marks it complete.

Built with Django, server-rendered templates, Bootstrap's grid and a small
amount of plain JavaScript. Every page works without JavaScript.

## Quick start

```bash
python3 -m venv .venv && .venv/bin/python -m pip install -r requirements.txt
```

```bash
cp .env.example .env && .venv/bin/python manage.py migrate
```

```bash
.venv/bin/python manage.py import_library && .venv/bin/python manage.py seed_course
```

```bash
.venv/bin/python manage.py createsuperuser && .venv/bin/python manage.py runserver
```

`import_library` loads the diagrams and audio from `MEDIA_ROOT/markup_media`;
`seed_course` then loads the course from the Bangla and English Markdown in
`MEDIA_ROOT/markup_content`: the nine modules, their lessons and quizzes, the
course author (bio and photo, which the home and About pages show), plus the
FAQs and the three legal pages in both languages from
[pages/seed_content.py](pages/seed_content.py). It is idempotent, so re-running
it updates rather than duplicates; it never replaces an author photo uploaded in
the panel. Add `--dry-run` to check the files without saving.

## Layout

| App | What lives there |
| --- | --- |
| `pages` | Home, about, contact, FAQ, legal pages, SEO helpers, sitemap, `robots.txt`, `llms.txt` |
| `courses` | Course, module, media, quiz, enrolment, progress — plus the access rules and course media |
| `accounts` | Email-keyed user, registration, login, password reset, account settings |
| `orders` | Checkout, payment gateways, orders, receipts |
| `manage_panel` | The staff administration panel at `/manage/` |

Three files carry most of the logic worth reading first:

- [courses/access.py](courses/access.py) — the single source of truth for what
  a student may open. Every view asks it rather than re-deriving the rule.
- [orders/gateways.py](orders/gateways.py) — the payment gateway interface, a
  local sandbox and the SSLCommerz implementation.
- [pages/seo.py](pages/seo.py) — per-page metadata and JSON-LD, rendered by
  `base.html` so no page can forget a canonical URL or an Open Graph image.

## Access rules

- Anyone can read the marketing pages and the curriculum.
- A **registered account** opens the free module (Module 1).
- **Enrolment** opens the rest — but each module still waits until the
  previous one's quiz has been passed, which is what the brief specifies.
- An administrator can suspend a student's access without touching their
  order history; a suspended student loses paid access immediately.

`CourseAccess` enforces all of this, and
[courses/tests.py](courses/tests.py) covers each rule directly.

## Course material is not public

Videos, audio, worksheets and library files are all written under
`MEDIA_ROOT` (`media/`), which is never served directly — not by Django, even
in development, and not by nginx. A file can only be reached through
`courses.views.protected_asset` (or the video and library views), which check
enrolment first. With Cloudflare Stream configured, video playback URLs
are signed per request and expire.

See [docs/SECURITY.md](docs/SECURITY.md).

## Payments

`PAYMENT_GATEWAY=sandbox` completes a purchase locally, offering both
"succeeded" and "failed" so the failure path can be exercised without an
account. Switching to `sslcommerz` needs only credentials.

No card data is stored or ever posted to this application. A payment callback
proves itself twice: the gateway's own signature, and a per-order token that
was never sent to the browser.

## Checks

```bash
.venv/bin/python manage.py test
```

127 tests cover the access rules, the quiz, payment callbacks (including
forged ones), the admin panel's permissions, SEO output and template hygiene.

Before deploying:

```bash
DJANGO_DEBUG=0 .venv/bin/python manage.py check --deploy
```

## Notes on choices

**Django 4.2, not 5.2.** The development machine only has Python 3.9, which
Django 5 does not support. The code avoids version-specific APIs, so on Python
3.12 you can change the pin in `requirements.txt` to `Django>=5.2,<6` and the
suite should pass unchanged. Production should run 3.12 + 5.2 LTS.

**Two admin interfaces.** `/manage/` is the custom panel from the design and
covers the day-to-day work the brief lists. Django's own admin stays at
`/django-admin/` for structural edits and data repair.

**SQLite by default.** Fine for development and a small launch; set
`DJANGO_DB_URL` to move to PostgreSQL without code changes.

## Documentation

- [docs/SECURITY.md](docs/SECURITY.md) — authentication, authorisation,
  payment and video access control
- [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) — hosting, nginx, backups
- [docs/CONTENT.md](docs/CONTENT.md) — how the administrator runs the course
- [docs/SEO.md](docs/SEO.md) — what is implemented and how to verify it

# CLAUDE.md

## Project

DhakaBassist: a learning platform where students study a nine-module music theory course, pay once in BDT, and unlock modules by passing quizzes.

## Stack

Python 3.12+ · Django 5.2 · Bootstrap 5.3 · vanilla JavaScript · SQLite (dev) / PostgreSQL (prod).

- Server-rendered templates. No SPA, no npm, no build step.
- Bootstrap and icons are vendored in `static/vendor/`. No CDN links.
- Don't add a library unless Django, Bootstrap or the standard library can't do the job.

## Commands

Use the virtualenv: `.venv/bin/python`, not bare `python`.

```bash
.venv/bin/python manage.py runserver
.venv/bin/python manage.py makemigrations && .venv/bin/python manage.py migrate
.venv/bin/python manage.py test
.venv/bin/ruff check .
.venv/bin/pylint --load-plugins=pylint_django --django-settings-module=core.settings <app> core
```

## Structure (Django default)

```
manage.py
core/              # settings.py, env.py, urls.py, wsgi.py, asgi.py (the Django project package)
<app>/             # accounts, courses, orders, pages, manage_panel: models, views, forms, urls, tests
templates/         # base.html, includes/ (shared partials), <app>/
static/            # css/ (modular), js/ (modules), img/, vendor/
media/             # every uploaded file (MEDIA_ROOT)
.env  .env.example
```

## Uploads (media folder)

Every uploaded file goes in the media folder (`MEDIA_ROOT`, `./media`, set in `core/settings.py`). That covers videos, audio, worksheets, library files, author photos and anything added later.

- Store uploads with a `FileField`/`ImageField` and an `upload_to` function that puts them in a subfolder of `media/` (e.g. `courses/<course>/<module>/`, `library/<folder>/`, `authors/<course>/`). Use the default storage; don't add another storage backend or write files anywhere else (`static/`, `Brand Assets/`, `/tmp`, the project root).
- Never serve `media/` directly or link to `MEDIA_URL` in templates. Every file goes out through a view: course material through `courses.views.protected_asset` after an access check (see `docs/SECURITY.md`), and public files like author photos through their own view (`courses.views.author_photo`).
- `media/` is not committed. Don't put files there that the code depends on; those belong in `static/`.

## .env

`.env.example` lists every variable and is the source of truth. Copy it to `.env`; `core/env.py` reads values from the environment (loaded with `python-dotenv`).

- `DJANGO_DEBUG` toggles debug. `DB_NAME`, `DB_USER`, `DB_PASSWORD` and `DB_HOST` switch to PostgreSQL; leave `DB_NAME` empty to use SQLite.
- Commit `.env.example`, never `.env`.

## Two languages (Bangla primary, English second)

- URLs decide the language: Bangla without a prefix, English under `/en/` (`i18n_patterns(prefix_default_language=False)` in `core/urls.py`). `/manage/`, `/django-admin/`, discovery files and `/library/…` links sit outside it; the staff panel is English only (`core/middleware.py`).
- **Content**: every translatable field is two columns, `<name>_bn` and `<name>_en`, plus `<name> = translated("<name>")` from `courses/i18n.py`, which reads the active language and falls back to the other. Media too (`video_uid_*`, `file_*`, `trailer_url_*`); pass `key=` so a duration follows its video. Query and order by the real columns (`columns("title")`), never the property. Required fields need one language, enforced by `in_some_language(...)` constraints and `BilingualFormMixin` (`manage_panel/forms.py`). Templates render a pair with `includes/bilingual_field.html`.
- **Wording**: English msgids with `{% translate %}` / `{% blocktranslate %}` and `gettext`; Bangla lives in `locale/bn/LC_MESSAGES/django.po` with the compiled `.mo` committed. Run `makemessages -l bn` / `compilemessages` (needs GNU gettext) after changing wording; see `docs/DEPLOYMENT.md`. JS gets its wording from `data-` attributes the template translates.
- Western digits in both languages. Emails render in `User.language`.

## Python and Django

- Follow PEP 8. Ruff handles lint and formatting. Keep it clean.
- After writing or changing Python code, run Pylint (with `pylint-django`) on the changed apps and fix what it reports. Don't silence a warning with `# pylint: disable` unless there is a real reason, and say why in the comment. Skip `migrations/` (set `ignore=migrations` in `.pylintrc`).
- Clear names, small functions, comments explain *why*. Use `logging`, not `print`.
- Keep views thin: validation in forms, business rules in models.
- Use `select_related` / `prefetch_related` to avoid N+1 queries.
- `ModelForm` with explicit `fields`. Every POST form has `{% csrf_token %}`.
- Every model has `__str__` and `Meta.ordering`. Money uses `DecimalField`.
- Every model change gets a migration. Use `LoginRequiredMixin` for protected views.
- Never put secrets in code. Never use `|safe` on user input.

## Database design

Follow relational database best practice. The code must work on both SQLite and PostgreSQL.

- **Normalise (3NF).** Each fact lives in one place. Don't copy a value that can be looked up through a relation or worked out from other columns. Store a copy only when it is a snapshot that must not change later, like the price on an order, and say why in a comment.
- **Relations are foreign keys.** Link rows with `ForeignKey`, `OneToOneField` or `ManyToManyField`, never an ID or name kept in a plain field. Use an explicit `through` model when the link carries its own data.
- **Pick `on_delete` on purpose.** `CASCADE` for child rows that mean nothing without their parent (a module's lessons). `PROTECT` for records that must outlive changes (orders, payments). `SET_NULL` (with `null=True`) for optional links. Give every relation a `related_name`.
- **Enforce rules in the database too**, not only in forms: `unique=True`, `UniqueConstraint` (with a `condition` when needed) and `CheckConstraint` in `Meta.constraints`, with clear `name`s.
- **Right types.** `DecimalField` for money, `DateTimeField` (timezone-aware) for times, `BooleanField` for flags, `TextChoices`/`IntegerChoices` for fixed sets of values, `PositiveIntegerField` for counts and positions. No comma-separated lists or JSON for data you need to filter or join on.
- **Nulls.** Text fields use `blank=True` with `""`, not `null=True`, so "empty" has one meaning. Use `null=True` only where "unknown" is a real state.
- **Index what you query.** Add `db_index=True` or `Meta.indexes` for columns used in filters, ordering and lookups. Foreign keys are indexed already. Don't add indexes nobody uses.
- **Keep writes consistent.** Wrap multi-step writes in `transaction.atomic()`. Use `select_for_update()` or `F()` expressions where two requests could change the same row (payments, counters).
- **Migrations are part of the design.** Keep schema and data migrations separate, make data migrations reversible where possible, and never edit a migration that has already run in production.

## Templates, CSS and JS

- Every page extends `base.html`. Use `{% static %}` for assets and `{% url %}` for links.
- All colours, spacing and radii are CSS variables in one `:root` block in `tokens.css`. No hard-coded hex values elsewhere.
- Style with classes. No inline `style=""`, no IDs, no `!important`.
- **Modular, no repeated code.** Before writing something new, check whether it already exists and reuse it. Repeated markup goes in `templates/partials/` (`{% include %}`), repeated Python in a helper or mixin, repeated CSS in one shared class.
- CSS is split by purpose under `static/css/`, one small file each, all linked from `base.html`: `tokens.css` (`:root` variables), `base.css` (reset, typography), `components.css` (buttons, cards, forms), `layout.css` (navbar, footer, grid helpers), then one file per page or app only when needed (`pages/orders.css`).
- JS is split into native ES modules under `static/js/`: `main.js` (entry, loaded with `<script type="module">`), `modules/` (one feature per file, e.g. `modal.js`, `form-validate.js`) and `utils/` (shared helpers like `api.js`, `dom.js`). Each module exports functions and imports what it needs. No copy-pasted snippets between files.
- JavaScript is for enhancement only. Forms must work without it. No jQuery, no inline `<script>` or `onclick`.

## SEO and AEO

Every public page must work for search engines (SEO) and answer engines like ChatGPT, Claude, Perplexity and Google AI Overviews (AEO). `docs/SEO.md` describes what exists. Keep it current when you change anything here.

- **Server-rendered content.** Text, headings and links are in the HTML before any JavaScript runs. Never load public content with JS.
- **Metadata through `pages/seo.py`.** Every view passes an `SEO` object, and `base.html` renders the title, meta description, canonical URL (from `SITE_BASE_URL`, never the request host), Open Graph and Twitter tags. Each page gets a unique title (about 60 characters) and description (about 155). Don't hand-write meta tags in templates.
- **Structured data (JSON-LD).** One `@graph` per page, built with the helpers in `pages/seo.py` (`organization`, `course_schema`, `faq_schema`, `article_schema`, `breadcrumb_list`). Add a new type there as a helper, not inline in a template. It must match the visible page, including price, currency and FAQs.
- **Answer-first content.** Put a short, direct answer at the top of each section (1–2 sentences), then the detail. Write headings as the questions people ask ("How much does the course cost?"). Use real lists, tables and `<details>` FAQs, and state facts plainly: price in BDT, number of modules, what's free and the refund terms.
- **Semantic HTML.** Exactly one `<h1>` per page, headings in order, landmarks (`<header>`, `<nav>`, `<main>`, `<article>`, `<footer>`), and descriptive link text (no "click here"). Images have real `alt` text, a `width` and `height`, and `loading="lazy"` below the fold.
- **Clean URLs.** Lowercase slugs, readable and stable (`/courses/<slug>/`). If a public URL has to change, add a 301 redirect.
- **Internal links.** Every public page is linked from somewhere and no more than two clicks from home. Breadcrumbs come from the same data as the `BreadcrumbList`.
- **Discovery files stay generated.** `sitemap.xml` (`pages/sitemaps.py`), `robots.txt` and `llms.txt` (`pages/views.py`) are built from the database. Add new public pages to the sitemap and to `llms.txt` if they matter to answer engines. Never hard-code their contents.
- **Private stays private.** Dashboards, lessons, quizzes, checkout, receipts and `/manage/` use `seo.noindex(...)`, are blocked in `robots.txt` and are left out of the sitemap. Media responses send `X-Robots-Tag: noindex`. `llms.txt` must never describe lesson content.
- **Fast pages.** No render-blocking scripts, preloaded self-hosted fonts, sized images and `fetchpriority="high"` on the hero image. Use `select_related` / `prefetch_related` so public pages run only a handful of queries.
- **Test it.** When you add or change a public page, add a test for its title, canonical URL, JSON-LD types and robots directive, and check that private pages stay out of the sitemap.

## Brand

Source: `Brand Assets/Brand Guideline.pdf` (originals, Fraunces font files). The web-ready copies live in `static/img/` and `static/fonts/`. Don't link to `Brand Assets/` from templates.

**Colours** (tokens in the `:root` block):

| Role | Hex | Token | Use |
|---|---|---|---|
| Primary: Parchment | `#F1E9D2` | `--parchment` | Page background, text on dark |
| Secondary: Gray | `#211F1D` | `--ink` / `--text` | Text, logo, buttons, strong lines |

- Everything else (`--cream`, `--panel`, `--line*`, `--highlight*`) is a tint between these two. Keep new colours warm and in this range. Don't add saturated brand colours.
- The only other hues are for feedback: `--ok` (green) and `--err` (red).
- Contrast on parchment: `--text` 13.5:1, `--text-muted` 5.7:1, `--ok`/`--err` above 5:1, `--text-faint` **2.3:1**. Use `--text-faint` only for placeholders, dividers and decoration, never for text people need to read.
- The guideline says "black" for body text. In this project that means `--text` (`#211F1D`), not `#000`.

**Typography**

- Display and headings: **Fraunces** (`--font-display`), self-hosted variable font `static/fonts/fraunces-var.woff2` (axes: wght, opsz, SOFT, WONK). The logo uses Fraunces Bold.
- Body: **Atkinson Hyperlegible** (`--font-body`), 400/700 and 400 italic, latin and latin-ext subsets.
- Bangla: **Noto Serif Bengali** (headings) and **Noto Sans Bengali** (body), Bengali-only variable subsets in `static/fonts/` (OFL, see the NOTICE there), next in the `--font-display` / `--font-body` stacks. Their `unicode-range` means Latin keeps the brand fonts. `:lang(bn)` gets taller line-height and no negative tracking.
- Only the upright Fraunces is shipped. Before using italic display text, add `Fraunces-Italic[...].woff2` from `Brand Assets/` to `static/fonts/` with its own `@font-face`. Otherwise the browser fakes the slant.

**Logos** (`static/img/`, all SVG, from `Brand Assets/`)

| File | Guideline name | When to use |
|---|---|---|
| `logo-text.svg` | Typography logo | The default. Use it in most places. |
| `logo-text-light.svg` | (derived) | The same, parchment fill, for dark (`--ink`) backgrounds, e.g. the footer |
| `logo-mark.svg` | Small logo | Tight spaces: favicon, small headers, avatars, the admin panel |
| `logo-full.svg` | Full logo | Only where there's a lot of space (hero, splash, social images). It has its own parchment box with a border. |

- The mark is an ink circle with a parchment bass clef. Show it on parchment or light backgrounds only.
- Don't recolour, stretch, outline or re-typeset the logo. Scale it with `width`/`height` and keep the aspect ratio.
- Give logo `<img>` a real `alt` (`{{ site.name }}`). Use `alt=""` only when the name sits right next to it, as in the masthead.
- When you replace a logo file, export it from `Brand Assets/`, strip the Inkscape metadata (`sodipodi:`, `inkscape:`), and keep the file name so templates don't change.

## Mobile-first (required)

- Design for 360px first, then add `@media (min-width: …)` using Bootstrap breakpoints (576, 768, 992, 1200).
- Use the Bootstrap grid: stack on mobile, columns from `md` up.
- No horizontal scrolling. Tables go in `.table-responsive`. Images are `img-fluid`.
- Tap targets at least 44px. Body text at least 16px.
- Check UI changes at 360px, 768px and 1280px before calling them done.

## Done means

`manage.py test` passes, `ruff check .` and Pylint are clean, no missing migrations, and UI checked at mobile and desktop widths.

## Working rules

- Match the style of the surrounding code. Make the smallest change that works.
- Ask before deleting data or doing anything hard to undo. Don't commit unless asked.

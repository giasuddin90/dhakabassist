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
media/             # uploads
.env  .env.example
```

## .env

`.env.example` lists every variable and is the source of truth. Copy it to `.env`; `core/env.py` reads values from the environment (loaded with `python-dotenv`).

- `DJANGO_DEBUG` toggles debug. `DJANGO_DB_URL` (`postgres://user:pass@host:port/name`) switches to PostgreSQL; leave it unset to use SQLite.
- Commit `.env.example`, never `.env`.

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

## Templates, CSS and JS

- Every page extends `base.html`. Use `{% static %}` for assets and `{% url %}` for links.
- All colours, spacing and radii are CSS variables in one `:root` block in `tokens.css`. No hard-coded hex values elsewhere.
- Style with classes. No inline `style=""`, no IDs, no `!important`.
- **Modular, no repeated code.** Before writing something new, check whether it already exists and reuse it. Repeated markup goes in `templates/partials/` (`{% include %}`), repeated Python in a helper or mixin, repeated CSS in one shared class.
- CSS is split by purpose under `static/css/`, one small file each, all linked from `base.html`: `tokens.css` (`:root` variables), `base.css` (reset, typography), `components.css` (buttons, cards, forms), `layout.css` (navbar, footer, grid helpers), then one file per page or app only when needed (`pages/orders.css`).
- JS is split into native ES modules under `static/js/`: `main.js` (entry, loaded with `<script type="module">`), `modules/` (one feature per file, e.g. `modal.js`, `form-validate.js`) and `utils/` (shared helpers like `api.js`, `dom.js`). Each module exports functions and imports what it needs. No copy-pasted snippets between files.
- JavaScript is for enhancement only. Forms must work without it. No jQuery, no inline `<script>` or `onclick`.

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

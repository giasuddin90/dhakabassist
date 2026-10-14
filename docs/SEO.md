# Search, answer engines and AI crawlers

What is implemented, where it lives, and how to check it.

## Rendering

Every public page is rendered on the server. The content, the headings and the
links are all in the HTML before any JavaScript runs, so a crawler that does
not execute scripts sees the whole page. JavaScript only smooths things that
already work: the accordions are `<details>`, the lesson tabs are server-
rendered panels, and the quiz is a set of forms.

Verify with `curl https://your-domain/ | grep "Nine modules"` — the curriculum
is in the response body.

## Per-page metadata

Views build a small `SEO` object (`pages/seo.py`) and `base.html` renders it.
Because it is one object in one template, no page can ship without a title, a
description, a canonical URL or an Open Graph image.

Each page carries a unique `<title>` and meta description, a canonical URL
built from `SITE_BASE_URL` (not the request's `Host`, which can be spoofed),
Open Graph and Twitter card tags, and a robots directive.

Course titles and descriptions are editable in the admin under "Search
appearance", falling back to the course title and summary.

## Structured data

One `@graph` per page, so the entities reference each other properly rather
than sitting in unconnected blocks:

| Page | Types |
| --- | --- |
| Home | `EducationalOrganization`, `Course` (with `Offer` and `CourseInstance`), `FAQPage` |
| Course | `EducationalOrganization`, `Course`, `BreadcrumbList` |
| About | `EducationalOrganization`, `Person`, `BreadcrumbList` |
| FAQ | `EducationalOrganization`, `FAQPage`, `BreadcrumbList` |
| Legal | `EducationalOrganization`, `Article`, `BreadcrumbList` |

The `Course` entity carries the price, the currency, what the course teaches
(every module title), the level, the languages and the fact that a free part
exists — which is what both search engines and answer engines need to describe
the course accurately without guessing.

Validate at [validator.schema.org](https://validator.schema.org/) and in
Google Search Console's Rich Results Test. A test asserts the JSON parses and
contains the expected types, so a template edit cannot silently break it.

## URLs, headings and links

URLs are readable and stable: `/courses/foundations-of-music/`,
`/legal/refunds/`, `/learn/<course>/<module>/`.

Each page has exactly one `<h1>` and a sensible heading order beneath it.
Pages are linked to each other on purpose — the home page points at the
curriculum, the curriculum at pricing and the free module, the FAQ at contact,
and the footer carries the legal pages — so nothing sits more than two clicks
from the home page.

Breadcrumbs are both visible and in the structured data, from the same source,
so they cannot disagree.

Images carry real alt text. Notation images uploaded by the administrator are
*required* to, since they are part of the lesson's meaning.

## Discovery files

- `/sitemap.xml` — public pages only, generated from the database, with
  `lastmod` from each record. Draft courses and unpublished legal pages are
  absent automatically.
- `/robots.txt` — allows the public site, blocks every signed-in and payment
  path, and names the sitemap. It also gives `GPTBot`, `ClaudeBot` and
  `PerplexityBot` explicit allow-lists covering the public pages and
  `llms.txt`.
- `/llms.txt` — a plain-text brief for answer engines: what the course is, its
  price in BDT, module list, payment methods, refund terms, the FAQs, and an
  explicit note that lesson content is private and must not be represented.

All three are generated from the same database as the site, so they cannot go
stale when the course changes.

## Keeping private pages private

Dashboards, lessons, quizzes, checkout, receipts and `/manage/` all send
`noindex, nofollow`, are listed in `robots.txt`, and require a session.
Protected files additionally send `X-Robots-Tag: noindex, nofollow`.

Tests assert that the sitemap excludes them and that lesson pages carry the
noindex directive.

## Performance, as it affects ranking

- Two self-hosted font families, subset by `unicode-range` and preloaded, so
  text paints once.
- One stylesheet, one deferred script, no framework, no render-blocking
  JavaScript.
- Images are sized, `loading="lazy"` below the fold, and `fetchpriority="high"`
  on the hero so the largest paint is not delayed.
- Static files are hashed and gzipped at deploy time and served with a
  one-year cache.
- Database queries are prefetched in `courses/access.py`, so a nine-module
  curriculum is a handful of queries rather than one per module.

## After launch

1. Set `SITE_BASE_URL` to the live origin — canonical URLs come from it.
2. Submit `https://your-domain/sitemap.xml` in Google Search Console and Bing
   Webmaster Tools.
3. Check the Rich Results Test on the home page and the course page.
4. Run Lighthouse on the home page and a lesson page.
5. Confirm `https://your-domain/llms.txt` resolves and reads correctly.

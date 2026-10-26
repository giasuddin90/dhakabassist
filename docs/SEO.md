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

## Two languages

Every public page exists in Bangla, the primary language, at the plain
address (`/courses/foundations-of-music/`), and in English under `/en/`
(`/en/courses/foundations-of-music/`). The URL alone decides the language, so
crawlers see and index both.

- `<html lang>` and `og:locale` (`bn_BD` / `en_BD`, with the other as
  `og:locale:alternate`) follow the page's language.
- The canonical URL points at the page in its own language. Indexable pages
  also list `<link rel="alternate" hreflang="bn|en|x-default">`; x-default is
  the Bangla page. `noindex` pages carry none.
- Text the site has not been given in Bangla falls back to English, so a
  Bangla page is never empty, only partly English until it is translated.
- The masthead's language switch is a plain link to the same page in the
  other language.

## Per-page metadata

Views build a small `SEO` object (`pages/seo.py`) and `base.html` renders it.
Because it is one object in one template, no page can ship without a title, a
description, a canonical URL or an Open Graph image.
A course page shares its banner (uploaded under Course settings) as that image;
without one it falls back to the site default.

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
| Downloads | `EducationalOrganization`, `ItemList` (each item a `DigitalDocument` or `AudioObject` with an `Offer`), `BreadcrumbList` |
| Contact | `EducationalOrganization`, `BreadcrumbList` |
| FAQ | `EducationalOrganization`, `FAQPage`, `BreadcrumbList` |
| Legal | `EducationalOrganization`, `Article`, `BreadcrumbList` |

The `Course` entity carries the price, the currency, what the course teaches
(every module title), the level, the page's language (`inLanguage`, with
names and descriptions in that language) and the fact that a free part
exists — which is what both search engines and answer engines need to describe
the course accurately without guessing.

Validate at [validator.schema.org](https://validator.schema.org/) and in
Google Search Console's Rich Results Test. A test asserts the JSON parses and
contains the expected types, so a template edit cannot silently break it.

## URLs, headings and links

URLs are readable and stable: `/courses/foundations-of-music/`,
`/legal/refunds/`, `/learn/<course>/<module>/`, `/downloads/`.

The downloads list is paginated (`?page=2`) and filterable by type
(`?type=worksheet`). Each of those pages is its own canonical URL with its own
title, so page 2 is not reported as a duplicate of page 1. Items have no page
of their own; each card carries an `id` (`#download-<slug>`) that its
`ItemList` entry points at.

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
  `lastmod` from each record. Every page is listed in both languages, each
  entry naming the other as an `hreflang` alternate (plus x-default). Draft
  courses and unpublished legal pages are absent automatically.
- `/robots.txt` — allows the public site, blocks every signed-in and payment
  path in both languages (`/learn/` and `/en/learn/`), and names the sitemap. It also gives `GPTBot`, `ClaudeBot` and
  `PerplexityBot` explicit allow-lists covering the public pages and
  `llms.txt`.
- `/llms.txt` — a plain-text brief for answer engines: what the course is, its
  price in BDT, module list, payment methods, refund terms, the FAQs, and an
  explicit note that lesson content and download files are private and must
  not be represented. It links the downloads list.
  Always written in English (it ignores `Accept-Language`); it links the
  English pages and explains that the Bangla page is the same address
  without `/en/`.

All three are generated from the same database as the site, so they cannot go
stale when the course changes.

## Keeping private pages private

Dashboards, lessons, quizzes, checkout, receipts, My downloads
(`/my-downloads/`) and `/manage/` all send `noindex, nofollow`, are listed in
`robots.txt`, and require a session. Course media and download files
additionally send `X-Robots-Tag: noindex, nofollow`; `robots.txt` blocks
everything below `/downloads/` (`/downloads/*/`: the files and the download
checkout) while the list itself stays open.

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

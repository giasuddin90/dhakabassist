# Security

Written for a non-developer reader as well as the next developer, as the
brief asks. Each section says what the risk is, then what the platform does.

## Authentication

Students sign in with an email address and password. Passwords are never
stored — Django keeps a one-way PBKDF2 hash, so a stolen database does not
hand over anyone's password, and nobody at DhakaBassist can read one.

Django's standard validators reject passwords that are too short, too common,
entirely numeric, or too similar to the user's own name or email.

Sign-in is deliberately indistinguishable between "no such account" and
"wrong password": `accounts/backends.py` still runs a password hash when the
email is unknown, so an attacker cannot learn which addresses are registered
by timing the response.

"Keep me logged in" is a real choice. Unticked, the session ends when the
browser closes; ticked, it lasts two weeks.

Password reset emails a single-use, time-limited link. Requesting a reset for
an address that has no account produces the same page and sends nothing, so
the form cannot be used to enumerate customers.

## Authorisation

One module decides who may study what: `courses/access.py`. Every view, the
protected media stream and the quiz all ask it, so they cannot disagree.

| Who | Gets |
| --- | --- |
| Anonymous | Marketing pages and the curriculum |
| Registered | The free module |
| Enrolled | Every module, each unlocking after the previous quiz is passed |
| Suspended | Free module only, regardless of orders |
| Staff | Everything, plus `/manage/` |

`/manage/` refuses anyone who is not active staff, and does so on every view,
not just the navigation. A signed-in student receives 403, never a redirect
loop. Tests assert this for every page in the panel.

## Student data

Collected: name, email, a password hash, which modules have been opened and
completed, quiz answers, video position, and order records.

Not collected: card numbers, dates of birth, addresses, phone numbers.

Signed-in pages send `noindex, nofollow` and are listed in `robots.txt`, so
student dashboards and lesson pages stay out of search results.

Contact form submissions are stored for reply and can be marked handled. The
form uses a hidden honeypot field instead of a third-party captcha, so no
visitor data leaves the site to fight spam.

## Payment security

**No card data ever reaches this application.** The student is sent to the
payment provider's own page; the provider tells us the outcome. An order
record holds the amount, the method chosen, the provider's reference and the
status — nothing more. A test asserts that no field named like a card field
exists on the model.

A payment callback is the one request that turns into free course access, so
it must prove itself twice:

1. **The provider's signature.** SSLCommerz signs its callback; the signature
   is recomputed from the store password and compared.
2. **A per-order token.** Generated when the order is created, sent to the
   gateway, and never rendered in any page. A callback quoting the wrong
   token is refused.

The amount is checked too: a callback reporting less than the order total
does not mark it paid.

Callback endpoints are CSRF-exempt because the POST comes from the gateway,
not from a page of ours — the two checks above replace the CSRF token. Every
other form on the site carries one.

`IPN` (the server-to-server notification) is the authoritative signal, so a
student who closes the browser mid-redirect is still enrolled. Marking an
order paid is idempotent: a duplicate callback cannot create a second
enrolment or send a second receipt.

## Video and file access control

Course videos are the paid product. They are never exposed as a public file.

Material is written under `PROTECTED_MEDIA_ROOT`, outside `MEDIA_ROOT`, so the
web server has no route to it. `courses/storage.py` refuses to produce a
public URL at all — asking raises `SuspiciousOperation` — which means a
template cannot leak one by accident.

The only route to the bytes is `courses.views.protected_asset`, which checks
enrolment first and then streams the file with `Cache-Control: no-store` and
`X-Robots-Tag: noindex`. Paths come from the database, never from the request,
and are still resolved and bounds-checked before opening, so a crafted path
cannot escape the directory.

With Cloudflare Stream configured, playback uses a token signed per request
that expires (two hours by default), so a copied URL stops working. If signing
is not configured the code deliberately falls back to the protected stream
rather than serving an unsigned public URL.

The goal, as the brief states, is to prevent unauthorised access and casual
redistribution — not to make screen recording impossible, which no platform
can do.

## Transport and headers

In production (`DJANGO_DEBUG=0`) the settings turn on HTTPS redirection,
HSTS with preload, and secure, HTTP-only session and CSRF cookies.
`X-Frame-Options: DENY` prevents clickjacking, `X-Content-Type-Options:
nosniff` prevents MIME confusion, and the referrer policy is
`strict-origin-when-cross-origin`.

`manage.py check --deploy` passes with no warnings.

## Input handling

Django's ORM parameterises every query, so SQL injection is not reachable
through normal use. Templates escape output by default.

Lesson notes and legal pages are Markdown written by administrators, and are
still sanitised with `bleach` before rendering: an administrator account
compromise should not become stored XSS for every student. Script, style and
frame elements are dropped whole; `javascript:` URLs and event handlers are
stripped. Tests cover each case.

Uploads are restricted to staff. Notation images require alt text, which is
enforced in the form.

## Secrets

Secrets come from the environment and are read in `core/settings.py` only.
`.env` is gitignored and `.env.example` documents every variable without
holding a value. Nothing in the repository contains a credential.

The canonical origin comes from `SITE_BASE_URL`, not the request's `Host`
header, so a spoofed header cannot redirect a payment callback or poison a
canonical link.

## Rate limiting

Not implemented in the application. Login and password-reset throttling should
be configured at the edge — Cloudflare rate-limiting rules on `/login/`,
`/register/` and `/password/reset/` are the simplest reliable option and cost
nothing to run. This is a deliberate choice: putting it at the edge keeps the
application simple and stops abusive traffic before it reaches the server.

## What is not covered

- Two-factor authentication for the administrator. Worth adding before the
  student list grows; `django-otp` is the usual choice.
- Automated dependency scanning. Enable Dependabot or `pip-audit` in CI.
- Backups are an infrastructure concern; see `docs/DEPLOYMENT.md`.

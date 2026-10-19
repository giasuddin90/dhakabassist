# Deployment

A single modest server runs this comfortably. The shape below is nginx +
gunicorn + PostgreSQL behind Cloudflare; adapt freely, but keep the media
arrangement intact: nothing under `/media/` is served directly.

## Recommended stack

| Piece | Choice | Why |
| --- | --- | --- |
| Python | 3.12 | Supported, and allows Django 5.2 LTS |
| Django | 5.2 LTS | Security support into 2028 |
| Database | PostgreSQL 16 | Real backups, concurrent writes |
| App server | gunicorn, 3 workers | Simple and dependable |
| Web server | nginx | TLS, static files, course media |
| CDN / DNS | Cloudflare | TLS, caching, rate limiting, DDoS |
| Video | Cloudflare Stream | Signed playback, no server bandwidth |
| Payments | SSLCommerz | bKash, Nagad, local and international cards |
| Email | Resend (HTTP API, `core/mail.py`), or any SMTP provider | Signup confirmation, password resets, receipts |

On Python 3.12, change the pin in `requirements.txt` to `Django>=5.2,<6` and
run the test suite before deploying. The code targets both lines.

## Environment

Copy `.env.example` and fill it in. The ones that must be right:

```
DJANGO_SECRET_KEY=<50+ random characters, never reused>
DJANGO_DEBUG=0
DJANGO_ALLOWED_HOSTS=dhakabassist.com,www.dhakabassist.com
DJANGO_CSRF_TRUSTED_ORIGINS=https://dhakabassist.com,https://www.dhakabassist.com
SITE_BASE_URL=https://dhakabassist.com
DJANGO_DB_URL=postgres://user:password@localhost:5432/dhakabassist
DJANGO_MEDIA_ROOT=/srv/dhakabassist/media
DJANGO_MEDIA_INTERNAL_URL=/_media/
PAYMENT_GATEWAY=sslcommerz
```

`DJANGO_DEBUG=0` is what turns on HTTPS redirection, HSTS and secure cookies.
Confirm with `manage.py check --deploy`, which must report no issues.

## Deploying

```bash
.venv/bin/python -m pip install -r requirements.txt && .venv/bin/python manage.py migrate && .venv/bin/python manage.py collectstatic --noinput
```

`collectstatic` hashes and gzips every static file; with `DJANGO_DEBUG=0` it
writes the manifest WhiteNoise needs, so skipping it breaks the site.

Then restart gunicorn.

### Translations

The interface wording lives in `locale/bn/LC_MESSAGES/django.po` (Bangla),
with the compiled `django.mo` committed beside it, so a deploy needs no
extra step. After changing wording in a template or in Python, refresh and
recompile it on a machine with GNU gettext (`sudo apt install gettext`):

```bash
.venv/bin/python manage.py makemessages -l bn -i ".venv/*" -i "manage_panel/*" -i "templates/manage_panel/*"
```

Translate the new entries in `django.po`, then:

```bash
.venv/bin/python manage.py compilemessages -l bn
```

Untranslated entries show in English. The staff panel is English only.

## Cloudflare Stream

Lesson videos play in Cloudflare's player through a token the application
signs per page view, after the enrolment check. The token replaces the video
ID in the iframe URL and expires (`CLOUDFLARE_STREAM_TOKEN_TTL`, two hours by
default, at most 24). One-time setup, with an API token that has Stream edit
permission:

1. Create a signing key and keep the response; it is shown once.

   ```bash
   curl -X POST "https://api.cloudflare.com/client/v4/accounts/<ACCOUNT_ID>/stream/keys" -H "Authorization: Bearer <API_TOKEN>"
   ```

   Put `result.id` in `CLOUDFLARE_STREAM_KEY_ID` and `result.pem` (still
   base64) in `CLOUDFLARE_STREAM_KEY_PEM`.
2. Set `CLOUDFLARE_STREAM_CUSTOMER_CODE` to the `<CODE>` in the
   `customer-<CODE>.cloudflarestream.com` address shown in the Stream
   dashboard.
3. For every lesson video, turn on **Require signed URLs** (video settings
   in the dashboard, or `"requireSignedURLs": true` via the API). This is the
   switch that makes the video private: without it the bare video ID plays
   for anyone, token or not.
4. Under Stream settings, set **Allowed origins** to the site's domain so the
   player cannot be embedded elsewhere.
5. In `/manage/`, pick "Cloudflare Stream" as the module's video provider and
   paste the 32-character video ID.

If the key is missing or invalid the lesson falls back to the access-checked
file stream and logs a warning (`courses.video`), so watch for that after a
deploy. Revoking the key (`DELETE .../stream/keys/<KEY_ID>`) invalidates
every token signed with it.

## nginx

Static files are served directly. Uploaded media is handed back to nginx
after Django has checked access — Django never streams the bytes itself, so a
large video does not occupy a worker.

```nginx
server {
    listen 443 ssl http2;
    server_name dhakabassist.com www.dhakabassist.com;

    client_max_body_size 512M;   # course video uploads

    location /static/ {
        alias /srv/dhakabassist/staticfiles/;
        expires 1y;
        add_header Cache-Control "public, immutable";
    }

    # Reachable only via Django's X-Accel-Redirect, never from outside.
    # There is deliberately no `location /media/`: every upload is course
    # material, so a direct /media/ request falls through to Django and 404s.
    location /_media/ {
        internal;
        alias /srv/dhakabassist/media/;
    }

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    }
}
```

The `internal` directive is what makes this safe: nginx will only serve that
location in response to Django's own header, never to a direct request. Test
it — `curl https://your-domain/_media/anything` and
`curl https://your-domain/media/anything` must both return 404.

## Rate limiting

Configure in Cloudflare rather than in the application: limit `/login/`,
`/register/`, `/password/reset/` and `/account/confirm/resend/` (and their
`/en/` twins) to roughly 10 requests per minute per IP. Each of the last three
sends an email, so an unlimited form is a way to spam an inbox.

## Backups

Three things must be backed up, and one of them is not the database:

1. **PostgreSQL** — nightly `pg_dump`, kept off the server, retained 30 days.
2. **`MEDIA_ROOT`** — the course material. If videos are on
   Cloudflare Stream this is small; if not, it is the largest item.
3. **`.env`** — kept in a password manager, not in the backup set.

Static files and the virtualenv do not need backing up; they are rebuilt.

**Test the restore.** A backup nobody has restored is not a backup. Restore
into a scratch database once a quarter and check a student can sign in.

## Monitoring

- Uptime: point a checker at `/healthz`, which returns `ok` without touching
  the database.
- Errors: set `ADMINS` in settings, or add Sentry.
- Logs: gunicorn and nginx, rotated, kept two weeks.

## What the owner must hold

Per the brief, the course owner — not the developer — must own the domain,
the Cloudflare account, the payment gateway account, the hosting account, the
database, the video library and the source code. Developers are given access
to these accounts; they do not register them in their own name.

## Going live

1. `manage.py check --deploy` reports no issues.
2. `manage.py test` passes.
3. Real SSLCommerz credentials in place; one live payment made and refunded.
4. Video playback confirmed for an enrolled student, and confirmed to fail
   for a signed-out visitor and an unenrolled one.
5. `curl https://your-domain/_media/anything` and `/media/anything` return 404.
6. Signup confirmation and password reset emails received at a real address
   (new students cannot log in without the first one).
7. Sitemap submitted; `robots.txt` and `llms.txt` resolve.
8. A backup taken and restored once.

"""Django settings for the DhakaBassist learning platform."""

import sys
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured
from dotenv import load_dotenv

from .env import env_bool, env_list, env_str

BASE_DIR = Path(__file__).resolve().parent.parent

load_dotenv(BASE_DIR / ".env")

# -- Core -------------------------------------------------------------------

# Off unless asked for, so a server with a missing `.env` fails safe.
DEBUG = env_bool("DJANGO_DEBUG", False)
# Tests run over plain HTTP without `collectstatic`, so they skip the
# production-only settings below whatever DJANGO_DEBUG says.
PRODUCTION = not DEBUG and sys.argv[1:2] != ["test"]

SECRET_KEY = env_str("DJANGO_SECRET_KEY")
if not SECRET_KEY:
    if PRODUCTION:
        raise ImproperlyConfigured("Set DJANGO_SECRET_KEY, or DJANGO_DEBUG=1.")
    SECRET_KEY = "dev-only-insecure-key"

ALLOWED_HOSTS = env_list("DJANGO_ALLOWED_HOSTS", ["localhost", "127.0.0.1"])

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.sitemaps",
    "django.contrib.staticfiles",
    "accounts",
    "courses",
    "downloads",
    "orders",
    "pages",
    "manage_panel",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    # The URL prefix picks the language: none for Bangla, /en/ for English.
    "django.middleware.locale.LocaleMiddleware",
    "core.middleware.staff_language_middleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "core.urls"
WSGI_APPLICATION = "core.wsgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.template.context_processors.i18n",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "pages.context_processors.site",
            ],
        },
    },
]

# -- Database ---------------------------------------------------------------

# SQLite until DB_NAME is set, then PostgreSQL (the port is the default 5432).

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": env_str("DB_NAME"),
        "USER": env_str("DB_USER"),
        "PASSWORD": env_str("DB_PASSWORD"),
        "HOST": env_str("DB_HOST", "localhost"),
        "CONN_MAX_AGE": 600,
    }
}


# DATABASES = {
#     "default": {
#         "ENGINE": "django.db.backends.sqlite3",
#         "NAME": BASE_DIR / "db.sqlite3",
#     }
# }

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# -- Authentication ---------------------------------------------------------

AUTH_USER_MODEL = "accounts.User"
AUTHENTICATION_BACKENDS = ["accounts.backends.EmailBackend"]
LOGIN_URL = "accounts:login"
LOGIN_REDIRECT_URL = "courses:dashboard"
LOGOUT_REDIRECT_URL = "pages:home"

PASSWORD_MIN_LENGTH = 6

AUTH_PASSWORD_VALIDATORS = [
    # Django's defaults look for `first_name`/`last_name`; this user model has
    # one `full_name`.
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
        "OPTIONS": {"user_attributes": ("full_name", "email")},
    },
    # Six, not Django's eight. The registration form reads the same number
    # for its hint and `minlength`; the common and numeric checks below still
    # turn away the weakest choices.
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
        "OPTIONS": {"min_length": PASSWORD_MIN_LENGTH},
    },
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# -- Internationalisation ---------------------------------------------------

# Bangla is the primary language and is served without a URL prefix;
# English lives under /en/. Content is stored in both (`<field>_bn` and
# `<field>_en`), and `courses.i18n.translated` picks the active one.
LANGUAGE_CODE = "bn"
LANGUAGES = [("bn", "বাংলা"), ("en", "English")]
LOCALE_PATHS = [BASE_DIR / "locale"]
TIME_ZONE = "Asia/Dhaka"
USE_I18N = True
USE_TZ = True

# -- Static and media -------------------------------------------------------

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "static"]
# Hashed filenames let static files be cached for a year, but they need a
# manifest from `collectstatic`. Development and tests serve files as-is,
# with the modification time in the URL so an edit is never served stale.
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {
        "BACKEND": (
            "whitenoise.storage.CompressedManifestStaticFilesStorage"
            if PRODUCTION
            else "core.storage.VersionedStaticFilesStorage"
        )
    },
}
# Hashed files are cached forever whatever this says; it covers the
# unhashed ones, which must be rechecked or a change never reaches browsers.
WHITENOISE_MAX_AGE = 60 if PRODUCTION else 0

# Every upload is course material, so nothing under MEDIA_ROOT is served
# directly: `courses.views.protected_asset` streams it after an enrolment
# check. See docs/SECURITY.md.
MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / "media"
# Empty: Django streams the files itself. Set to "/_media/" to hand streaming
# to nginx via X-Accel-Redirect (see docs/DEPLOYMENT.md).
MEDIA_INTERNAL_URL = ""

# -- Email ------------------------------------------------------------------

# Mail is handed to a background thread (`core/mail.py`), which delivers it
# through Resend's HTTP API with a Resend API key, or prints it to the
# console without one. Tests always use Django's in-memory backend whatever
# this says, so they stay synchronous.
RESEND_API_KEY = env_str("RESEND_API_KEY")
EMAIL_BACKEND = "core.mail.ThreadedEmailBackend"
EMAIL_DELIVERY_BACKEND = (
    "core.mail.ResendEmailBackend"
    if RESEND_API_KEY
    else "django.core.mail.backends.console.EmailBackend"
)
# A stalled mail service must not hold a mail thread indefinitely.
EMAIL_TIMEOUT = 10
# How long a student waits before asking for another confirmation or
# password-reset email.
EMAIL_RESEND_SECONDS = 60
DEFAULT_FROM_EMAIL = env_str(
    "DJANGO_DEFAULT_FROM_EMAIL", "DhakaBassist <hello@dhakabassist.com>"
)

# -- Messages ---------------------------------------------------------------

MESSAGE_STORAGE = "django.contrib.messages.storage.session.SessionStorage"

# -- Security ---------------------------------------------------------------

X_FRAME_OPTIONS = "DENY"
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "strict-origin-when-cross-origin"
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SAMESITE = "Lax"
SESSION_COOKIE_AGE = 60 * 60 * 24 * 14

if PRODUCTION:
    SECURE_SSL_REDIRECT = True
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    SECURE_HSTS_SECONDS = 31536000
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True

# -- Site / branding -------------------------------------------------------

SITE_BASE_URL = env_str("SITE_BASE_URL", "http://127.0.0.1:8000").rstrip("/")
# Forms posted from the canonical origin pass the CSRF origin check even when
# a proxy rewrites the scheme or port.
CSRF_TRUSTED_ORIGINS = [SITE_BASE_URL]

SITE = {
    "name": "DhakaBassist",
    "tagline": "Music theory courses by Tanveer Haque.",
    "instructor": "Tanveer Haque",
    "email": "hello@dhakabassist.com",
    "location": "Dhaka, Bangladesh",
    "base_url": SITE_BASE_URL,
    # Open Graph locale per language code; see pages.context_processors.
    "locales": {"bn": "bn_BD", "en": "en_BD"},
    "currency": "BDT",
    "currency_symbol": "৳",
    # Shown on a course page until staff upload a banner (a static path).
    "course_banner_placeholder": "img/course-banner-placeholder.svg",
}

# -- Payments ---------------------------------------------------------------

# "sandbox" simulates a gateway round-trip locally. Swap to "sslcommerz"
# once live credentials exist; see orders/gateways.py.
PAYMENT_GATEWAY = env_str("PAYMENT_GATEWAY", "sandbox")
SSLCOMMERZ = {
    "store_id": env_str("SSLCOMMERZ_STORE_ID"),
    "store_password": env_str("SSLCOMMERZ_STORE_PASSWORD"),
    "sandbox": env_bool("SSLCOMMERZ_SANDBOX", True),
}

# -- Video ------------------------------------------------------------------

# Cloudflare Stream signed playback. Empty key falls back to the access-checked
# file stream, so local development needs no third-party account.
CLOUDFLARE_STREAM = {
    "account_id": env_str("CLOUDFLARE_ACCOUNT_ID"),
    "signing_key_id": env_str("CLOUDFLARE_STREAM_KEY_ID"),
    "signing_key_pem": env_str("CLOUDFLARE_STREAM_KEY_PEM"),
    # The "<CODE>" in customer-<CODE>.cloudflarestream.com (Stream dashboard).
    "customer_code": env_str("CLOUDFLARE_STREAM_CUSTOMER_CODE"),
    # Two hours; Cloudflare rejects tokens that live longer than 24.
    "token_ttl_seconds": 7200,
}

# -- Logging ----------------------------------------------------------------

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {"simple": {"format": "{levelname} {name} {message}", "style": "{"}},
    "handlers": {
        "console": {"class": "logging.StreamHandler", "formatter": "simple"},
    },
    "root": {"handlers": ["console"], "level": "INFO"},
    "loggers": {
        "django.request": {"level": "ERROR", "propagate": True},
    },
}

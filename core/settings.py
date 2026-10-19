"""Django settings for the DhakaBassist learning platform."""

from pathlib import Path

from dotenv import load_dotenv

from .env import env_bool, env_int, env_list, env_str

BASE_DIR = Path(__file__).resolve().parent.parent

load_dotenv(BASE_DIR / ".env")

# -- Core -------------------------------------------------------------------

SECRET_KEY = env_str("DJANGO_SECRET_KEY", "dev-only-insecure-key-change-me")
DEBUG = env_bool("DJANGO_DEBUG", True)
ALLOWED_HOSTS = ['*']
CSRF_TRUSTED_ORIGINS = env_list("DJANGO_CSRF_TRUSTED_ORIGINS", [])

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

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / env_str("DJANGO_DB_NAME", "db.sqlite3"),
    }
}
if env_str("DJANGO_DB_URL", ""):  # postgres://user:pass@host:port/name
    import urllib.parse as _urlparse

    _url = _urlparse.urlparse(env_str("DJANGO_DB_URL", ""))
    DATABASES["default"] = {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": _url.path.lstrip("/"),
        "USER": _url.username or "",
        "PASSWORD": _url.password or "",
        "HOST": _url.hostname or "",
        "PORT": str(_url.port or ""),
        "CONN_MAX_AGE": 600,
    }

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# -- Authentication ---------------------------------------------------------

AUTH_USER_MODEL = "accounts.User"
AUTHENTICATION_BACKENDS = ["accounts.backends.EmailBackend"]
LOGIN_URL = "accounts:login"
LOGIN_REDIRECT_URL = "courses:dashboard"
LOGOUT_REDIRECT_URL = "pages:home"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
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
# manifest from `collectstatic`, so development and tests serve files as-is.
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {
        "BACKEND": (
            "django.contrib.staticfiles.storage.StaticFilesStorage"
            if DEBUG
            else "whitenoise.storage.CompressedManifestStaticFilesStorage"
        )
    },
}
WHITENOISE_MAX_AGE = 31536000

# Every upload is course material, so nothing under MEDIA_ROOT is served
# directly: `courses.views.protected_asset` streams it after an enrolment
# check. See docs/SECURITY.md.
MEDIA_URL = "media/"
MEDIA_ROOT = Path(env_str("DJANGO_MEDIA_ROOT", str(BASE_DIR / "media")))
# Set to "/_media/" to hand streaming to nginx via X-Accel-Redirect.
MEDIA_INTERNAL_URL = env_str("DJANGO_MEDIA_INTERNAL_URL", "")

# -- Email ------------------------------------------------------------------

# With a Resend API key, mail goes out through Resend's HTTP API
# (`core/mail.py`); without one it prints to the console. Tests always use
# Django's in-memory backend whatever this says.
RESEND_API_KEY = env_str("RESEND_API_KEY", "")
EMAIL_BACKEND = env_str(
    "DJANGO_EMAIL_BACKEND",
    "core.mail.ResendEmailBackend"
    if RESEND_API_KEY
    else "django.core.mail.backends.console.EmailBackend",
)
EMAIL_HOST = env_str("DJANGO_EMAIL_HOST", "")
EMAIL_PORT = env_int("DJANGO_EMAIL_PORT", 587)
EMAIL_HOST_USER = env_str("DJANGO_EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = env_str("DJANGO_EMAIL_HOST_PASSWORD", "")
EMAIL_USE_TLS = env_bool("DJANGO_EMAIL_USE_TLS", True)
# Signup waits on the confirmation email, so a stalled SMTP server must not
# hold the request open indefinitely.
EMAIL_TIMEOUT = env_int("DJANGO_EMAIL_TIMEOUT", 10)
DEFAULT_FROM_EMAIL = env_str("DJANGO_DEFAULT_FROM_EMAIL", "hello@dhakabassist.com")

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

if not DEBUG:
    SECURE_SSL_REDIRECT = env_bool("DJANGO_SECURE_SSL_REDIRECT", True)
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    SECURE_HSTS_SECONDS = env_int("DJANGO_SECURE_HSTS_SECONDS", 31536000)
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True

# -- Site / branding -------------------------------------------------------

SITE = {
    "name": "DhakaBassist",
    "tagline": "Music theory courses by Tanveer Haque.",
    "instructor": "Tanveer Haque",
    "email": "hello@dhakabassist.com",
    "location": "Dhaka, Bangladesh",
    "base_url": env_str("SITE_BASE_URL", "http://127.0.0.1:8000").rstrip("/"),
    # Open Graph locale per language code; see pages.context_processors.
    "locales": {"bn": "bn_BD", "en": "en_BD"},
    "currency": "BDT",
    "currency_symbol": "৳",
}

# -- Payments ---------------------------------------------------------------

# "sandbox" simulates a gateway round-trip locally. Swap to "sslcommerz"
# once live credentials exist; see orders/gateways.py.
PAYMENT_GATEWAY = env_str("PAYMENT_GATEWAY", "sandbox")
SSLCOMMERZ = {
    "store_id": env_str("SSLCOMMERZ_STORE_ID", ""),
    "store_password": env_str("SSLCOMMERZ_STORE_PASSWORD", ""),
    "sandbox": env_bool("SSLCOMMERZ_SANDBOX", True),
}

# -- Video ------------------------------------------------------------------

# Cloudflare Stream signed playback. Empty key falls back to the access-checked
# file stream, so local development needs no third-party account.
CLOUDFLARE_STREAM = {
    "account_id": env_str("CLOUDFLARE_ACCOUNT_ID", ""),
    "signing_key_id": env_str("CLOUDFLARE_STREAM_KEY_ID", ""),
    "signing_key_pem": env_str("CLOUDFLARE_STREAM_KEY_PEM", ""),
    # The "<CODE>" in customer-<CODE>.cloudflarestream.com (Stream dashboard).
    "customer_code": env_str("CLOUDFLARE_STREAM_CUSTOMER_CODE", ""),
    # Cloudflare rejects tokens that expire more than 24 hours after signing.
    "token_ttl_seconds": min(env_int("CLOUDFLARE_STREAM_TOKEN_TTL", 7200), 86400),
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

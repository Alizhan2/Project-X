"""Doedu settings: ONE module, environment-driven, validated at startup.

DOEDU_ENV         development | test | staging | production   (what kind of environment is this?)
DOEDU_LAUNCH_MODE development | demo | commercial             (what is the product allowed to do?)

* development/test: convenient defaults, ephemeral secret key, demo tools allowed.
* staging/production: everything security-relevant must be configured explicitly; a bad configuration refuses to
  start (ImproperlyConfigured listing every problem) instead of running insecurely.
* demo launch mode: simulated payments/transport, clearly labelled. commercial: requires real, authorised
  integrations that do not exist yet, so it refuses to start (see docs/commercial-readiness.md).
Nothing secret is committed; see ../.env.example and docs/configuration.md.
"""

import os
import sys
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured
from django.utils.crypto import get_random_string

BASE_DIR = Path(__file__).resolve().parent.parent


def env(name, default=None):
    return os.environ.get(name, default)


def env_bool(name, default=False):
    return str(env(name, str(default))).lower() in ("1", "true", "yes", "on")


def env_list(name, default=""):
    return [v.strip() for v in env(name, default).split(",") if v.strip()]


def env_int(name, default):
    return int(env(name, str(default)))


ENVIRONMENT = env("DOEDU_ENV", "test" if "test" in sys.argv else "development")
LAUNCH_MODE = env("DOEDU_LAUNCH_MODE", "development" if ENVIRONMENT in ("development", "test") else "demo")
IS_DEPLOYED = ENVIRONMENT in ("staging", "production")
RELEASE = env("DOEDU_RELEASE", "dev")          # set at image build time (git tag/sha); shown by /api/config/
DEBUG = env_bool("DJANGO_DEBUG", False)

_problems = []
if ENVIRONMENT not in ("development", "test", "staging", "production"):
    _problems.append("DOEDU_ENV must be development, test, staging or production.")
if LAUNCH_MODE not in ("development", "demo", "commercial"):
    _problems.append("DOEDU_LAUNCH_MODE must be development, demo or commercial.")

SECRET_KEY = env("DJANGO_SECRET_KEY")
if not SECRET_KEY:
    if IS_DEPLOYED:
        _problems.append("DJANGO_SECRET_KEY is required in staging/production.")
    SECRET_KEY = get_random_string(64)  # development/test only: ephemeral, sessions reset on restart
elif IS_DEPLOYED and (len(SECRET_KEY) < 50 or "insecure" in SECRET_KEY.lower() or SECRET_KEY == "change-me"):
    _problems.append("DJANGO_SECRET_KEY must be at least 50 random characters in staging/production.")

ALLOWED_HOSTS = env_list("DJANGO_ALLOWED_HOSTS", "" if IS_DEPLOYED else "localhost,127.0.0.1")
CSRF_TRUSTED_ORIGINS = env_list(
    "DJANGO_CSRF_TRUSTED_ORIGINS", "" if IS_DEPLOYED else "http://localhost:5173,http://127.0.0.1:5173")

# Demo tooling (seed/reset) exists only where it cannot wipe real data.
ALLOW_DEMO_TOOLS = ENVIRONMENT in ("development", "test") or (ENVIRONMENT == "staging" and env_bool("DOEDU_ALLOW_DEMO_TOOLS", False))
SIMULATION_ENABLED = LAUNCH_MODE in ("development", "demo")   # simulated payments/transport allowed
REGISTRATION_ENABLED = env_bool("REGISTRATION_ENABLED", True)
ENABLE_API_DOCS = env_bool("ENABLE_API_DOCS", ENVIRONMENT != "production")
FRONTEND_DIST = Path(env("FRONTEND_DIST", str(BASE_DIR.parent / "frontend" / "dist")))

SECURE_SSL = env_bool("DJANGO_SECURE_SSL", False)

if IS_DEPLOYED:
    if DEBUG:
        _problems.append("DJANGO_DEBUG must be off in staging/production.")
    if not ALLOWED_HOSTS or "*" in ALLOWED_HOSTS:
        _problems.append("DJANGO_ALLOWED_HOSTS must list explicit host names (no '*', no empty list).")
    if ENVIRONMENT == "production":
        if not SECURE_SSL:
            _problems.append("DJANGO_SECURE_SSL=true is required in production (HTTPS only; see docs/deployment.md).")
        if not CSRF_TRUSTED_ORIGINS or any(not o.startswith("https://") for o in CSRF_TRUSTED_ORIGINS):
            _problems.append("DJANGO_CSRF_TRUSTED_ORIGINS must be https:// origins in production.")
        if env_bool("DOEDU_ALLOW_DEMO_TOOLS", False):
            _problems.append("Demo tools must not be enabled in production (unset DOEDU_ALLOW_DEMO_TOOLS).")
    if not env("POSTGRES_PASSWORD") or env("POSTGRES_PASSWORD") in ("change-me-dev-only", "change-me"):
        _problems.append("POSTGRES_PASSWORD must be set to a real secret in staging/production.")
if LAUNCH_MODE == "commercial":
    _problems.append("DOEDU_LAUNCH_MODE=commercial needs authorised transport and payment integrations, which are not "
                     "implemented. Refusing to start (docs/commercial-readiness.md).")
if _problems:
    raise ImproperlyConfigured("Invalid configuration:\n  - " + "\n  - ".join(_problems))

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "drf_spectacular",
    "apps.core",
    "apps.accounts",
    "apps.transport",
    "apps.planning",
    "apps.bookings",
    "apps.payments",
    "apps.disruptions",
    "apps.notifications",
]

AUTH_USER_MODEL = "accounts.User"

MIDDLEWARE = [
    "apps.core.i18n.LanguageMiddleware",
    "apps.core.middleware.RequestIdMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "apps.core.middleware.SecurityHeadersMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

# Bounded database behaviour: connect timeout, statement/lock/idle-in-transaction timeouts (ms), persistent
# connections with health checks. Override per environment; see docs/configuration.md.
_pg_options = " ".join([
    f"-c statement_timeout={env_int('DB_STATEMENT_TIMEOUT_MS', 20000)}",
    f"-c lock_timeout={env_int('DB_LOCK_TIMEOUT_MS', 8000)}",
    f"-c idle_in_transaction_session_timeout={env_int('DB_IDLE_TX_TIMEOUT_MS', 30000)}",
])
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": env("POSTGRES_DB", "doedu"),
        "USER": env("POSTGRES_USER", "doedu"),
        "PASSWORD": env("POSTGRES_PASSWORD", ""),
        "HOST": env("POSTGRES_HOST", "127.0.0.1"),
        "PORT": env("POSTGRES_PORT", "5432"),
        "CONN_MAX_AGE": env_int("DB_CONN_MAX_AGE", 60 if IS_DEPLOYED else 0),
        "CONN_HEALTH_CHECKS": True,
        "OPTIONS": {"connect_timeout": env_int("DB_CONNECT_TIMEOUT", 5), "options": _pg_options},
    }
}

# Shared cache in PostgreSQL (used for rate-limit counters so all worker processes agree). Create the table with
# `manage.py createcachetable` (done by the migrate step; see docs/deployment.md).
CACHES = {
    "default": {"BACKEND": "django.core.cache.backends.db.DatabaseCache", "LOCATION": "doedu_cache"}
    if IS_DEPLOYED else {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}   # dev/test: per-process is fine
}

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": f"django.contrib.auth.password_validation.{n}"}
    for n in (
        "UserAttributeSimilarityValidator",
        "MinimumLengthValidator",
        "CommonPasswordValidator",
        "NumericPasswordValidator",
    )
]

# Demonstration region: one timezone, one currency. Stored datetimes are UTC.
LANGUAGE_CODE = "en-gb"
TIME_ZONE = "Europe/Berlin"
USE_I18N = False
USE_TZ = True
DEMO_CURRENCY = "EUR"

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"
                    if IS_DEPLOYED else "django.contrib.staticfiles.storage.StaticFilesStorage"},
}
# The built SPA is served from the app server too (no separate web server needed for the demo). Vite emits
# content-hashed files under /assets/, which are safe to cache "forever".
WHITENOISE_ROOT = FRONTEND_DIST if FRONTEND_DIST.exists() and IS_DEPLOYED else None
WHITENOISE_IMMUTABLE_FILE_TEST = lambda path, url: url.startswith("/assets/")  # noqa: E731
WHITENOISE_MIMETYPES = {".webmanifest": "application/manifest+json"}
WHITENOISE_AUTOREFRESH = DEBUG
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
# No user uploads exist in this application (no MEDIA_ROOT, no FileField). Adding any needs a storage review.

# Session auth + CSRF. Frontend is same-origin (Vite proxy in dev, the app server itself in production),
# so NO CORS headers are sent. Do not add django-cors-headers unless a cross-origin client really appears.
SESSION_COOKIE_AGE = env_int("SESSION_COOKIE_AGE_SECONDS", 7 * 24 * 3600)
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SAMESITE = "Lax"
SESSION_COOKIE_SECURE = env_bool("DJANGO_SECURE_COOKIES", IS_DEPLOYED)
CSRF_COOKIE_SECURE = SESSION_COOKIE_SECURE
# The SPA reads the csrftoken cookie and echoes it in X-CSRFToken.
CSRF_COOKIE_HTTPONLY = False

# Proxy awareness: only trust X-Forwarded-* when running behind a proxy you control.
NUM_PROXIES = env_int("DOEDU_TRUSTED_PROXIES", 0)   # used by DRF throttling to find the real client IP
if SECURE_SSL:
    SECURE_SSL_REDIRECT = True
    SECURE_REDIRECT_EXEMPT = [r"^api/health/(live|ready)/?$"]   # orchestrator probes may use plain HTTP internally
    SECURE_HSTS_SECONDS = env_int("DOEDU_HSTS_SECONDS", 3600)   # start small; raise per docs/deployment.md rollout plan
    SECURE_HSTS_INCLUDE_SUBDOMAINS = env_bool("DOEDU_HSTS_SUBDOMAINS", False)
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    USE_X_FORWARDED_HOST = False

# Abuse resistance (application level only; ingress-level limits are still required, see docs/security.md).
_LENIENT = "test" in sys.argv or not IS_DEPLOYED   # strict limits apply when deployed (staging/production); THROTTLE_* overrides
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": ["rest_framework.authentication.SessionAuthentication"],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"],
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "EXCEPTION_HANDLER": "apps.core.errors.exception_handler",
    "NUM_PROXIES": NUM_PROXIES,
    "DEFAULT_THROTTLE_RATES": {
        "account_email": env("THROTTLE_ACCOUNT_EMAIL", "5/hour"),
        "account_token": env("THROTTLE_ACCOUNT_TOKEN", "20/min"),
        "login": "100000/min" if _LENIENT else env("THROTTLE_LOGIN", "10/min"),
        "register": "100000/min" if _LENIENT else env("THROTTLE_REGISTER", "5/hour"),
        "search": "100000/min" if _LENIENT else env("THROTTLE_SEARCH", "120/min"),
        "booking": "100000/min" if _LENIENT else env("THROTTLE_BOOKING", "30/min"),
    },
}
LOGIN_FAILURE_LIMIT = env_int("LOGIN_FAILURE_LIMIT", 5)          # failed attempts per account...
LOGIN_FAILURE_WINDOW_SECONDS = env_int("LOGIN_FAILURE_WINDOW_SECONDS", 15 * 60)   # ...within this window

SPECTACULAR_SETTINGS = {
    "TITLE": "Doedu API",
    "DESCRIPTION": "Multimodal transport booking MVP. All data, payments and confirmations are SIMULATED.",
    "VERSION": RELEASE,
    "SERVE_INCLUDE_SCHEMA": False,
    "ENUM_NAME_OVERRIDES": {"KazakhstanCityEnum": "apps.transport.kazakhstan.catalog.CITY_IDS"},
}

# Booking / background work
RESERVATION_MINUTES = env_int("RESERVATION_MINUTES", 10)
JOB_LOCK_TIMEOUT_SECONDS = env_int("JOB_LOCK_TIMEOUT_SECONDS", 60)
WORKER_STALE_SECONDS = env_int("WORKER_STALE_SECONDS", 60)       # readiness: no worker heartbeat for this long = degraded
DEMO_SCHEDULE_DAYS = env_int("DEMO_SCHEDULE_DAYS", 0)           # >0: the worker keeps a hosted demo's synthetic timetable this many days ahead
METRICS_TOKEN = env("METRICS_TOKEN", "")                          # bearer token for /api/ops/metrics (empty = endpoint off)

# Journey planning
MIN_SAME_STOP_TRANSFER_MIN = 5     # minimum time to change vehicles at the same stop
MAX_TRANSFER_WAIT_MIN = 180        # connections waiting longer than this are not offered
MAX_JOURNEY_HOURS = 14
REPLACEMENT_WINDOW_HOURS = 6        # how long after the disruption we look for replacements
REPLACEMENT_MAX_LATER_ARRIVAL_HOURS = 6  # a replacement may arrive at most this much later than planned
REPLACEMENT_OFFER_MINUTES = env_int("REPLACEMENT_OFFER_MINUTES", 30)

# Logging: JSON lines to stdout when deployed (collected by the platform); readable text locally. Request bodies,
# headers, cookies, passwords and tokens are never logged (see apps/core/logging.py).
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "filters": {"request_id": {"()": "apps.core.logging.RequestIdFilter"}},
    "formatters": {
        "json": {"()": "apps.core.logging.JsonFormatter"},
        "text": {"format": "%(asctime)s %(levelname)s %(name)s [%(request_id)s] %(message)s"},
    },
    "handlers": {"console": {"class": "logging.StreamHandler", "filters": ["request_id"],
                             "formatter": "json" if IS_DEPLOYED else "text"}},
    "root": {"handlers": ["console"], "level": env("LOG_LEVEL", "INFO")},
    "loggers": {
        "django.server": {"level": "WARNING" if IS_DEPLOYED else "INFO"},
        "django.security.DisallowedHost": {"level": "WARNING"},
        "doedu.access": {"level": "INFO"},
    },
}

# Tests only: a fast password hasher (never used outside `manage.py test`).
if "test" in sys.argv:
    PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
    LOGGING["root"]["level"] = "WARNING"

# Account links use a configured origin, never the untrusted request Host.
PUBLIC_APP_URL = env("PUBLIC_APP_URL", "http://127.0.0.1:5173").rstrip("/")
PASSWORD_RESET_TIMEOUT = 3600
EMAIL_BACKEND = env("EMAIL_BACKEND", "django.core.mail.backends.smtp.EmailBackend" if IS_DEPLOYED else "apps.accounts.mail_backend.EmailBackend")
EMAIL_FILE_PATH = BASE_DIR.parent / ".local-mail"
EMAIL_HOST = env("EMAIL_HOST", "localhost")
EMAIL_PORT = env_int("EMAIL_PORT", 587)
EMAIL_HOST_USER = env("EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = env("EMAIL_HOST_PASSWORD", "")
EMAIL_USE_TLS = env_bool("EMAIL_USE_TLS", True)
EMAIL_USE_SSL = env_bool("EMAIL_USE_SSL", False)
EMAIL_TIMEOUT = 10
DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL", "Doedu <noreply@doedu.test>")
if IS_DEPLOYED and env("PUBLIC_APP_URL"):
    from urllib.parse import urlsplit
    _mail_origin = urlsplit(PUBLIC_APP_URL)
    if (_mail_origin.scheme != "https" or not _mail_origin.hostname or _mail_origin.username
            or _mail_origin.password or _mail_origin.query or _mail_origin.fragment or _mail_origin.path):
        raise ImproperlyConfigured("PUBLIC_APP_URL must be an HTTPS origin without credentials or a path.")

ACCOUNT_EMAIL_CONFIGURED = bool(env("PUBLIC_APP_URL") and env("EMAIL_HOST") and env("DEFAULT_FROM_EMAIL"))

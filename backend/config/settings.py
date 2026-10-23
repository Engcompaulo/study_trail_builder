"""Django settings for the Study Trail Builder backend.

The backend is deliberately minimal: a single app (``trail``) exposing one
plain ``JsonResponse`` view at ``POST /api/trail``. No Django ORM or database
is used; trails are computed per request from plain dataclasses and are never
persisted (design: "pure core, thin edges"). Configuration is env-driven so the
same image runs locally (``ng serve`` cross-origin) and inside the Docker stack
(nginx reverse proxy, same-origin). All user-facing text is English (Req 7.7).
"""

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent


def _env_bool(name, default):
    """Read a boolean environment variable (``1/true/yes/on`` are truthy)."""
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _env_list(name, default):
    """Read a comma-separated environment variable into a list of strings."""
    value = os.environ.get(name)
    if value is None:
        return list(default)
    return [item.strip() for item in value.split(",") if item.strip()]


# --- Core config (env-driven) ------------------------------------------------

# In production provide DJANGO_SECRET_KEY via the environment. The fallback
# keeps local development frictionless; this app stores no user data or
# sessions, so the key is not security-critical here.
SECRET_KEY = os.environ.get(
    "DJANGO_SECRET_KEY", "dev-insecure-study-trail-builder-key"
)

DEBUG = _env_bool("DJANGO_DEBUG", False)

ALLOWED_HOSTS = _env_list(
    "DJANGO_ALLOWED_HOSTS", ["localhost", "127.0.0.1", "backend"]
)


# --- Applications and middleware --------------------------------------------

INSTALLED_APPS = [
    "corsheaders",
    "trail",
]

MIDDLEWARE = [
    # CORS middleware must come first so it can set headers on every response.
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.common.CommonMiddleware",
]

ROOT_URLCONF = "config.urls"

WSGI_APPLICATION = "config.wsgi.application"


# --- CORS (django-cors-headers) ---------------------------------------------
#
# In the Docker stack nginx proxies /api/* to the backend, so requests are
# same-origin and no CORS is needed. For local cross-origin development
# (Angular ``ng serve`` on :4200 calling Django on :8000) the frontend origin
# is allowlisted here. Only POST with a JSON content type on /api/trail is
# used by the frontend (design: CORS / proxy section).
CORS_ALLOWED_ORIGINS = _env_list(
    "CORS_ALLOWED_ORIGINS", ["http://localhost:4200", "http://127.0.0.1:4200"]
)

# Restrict CORS to the single endpoint the frontend calls.
CORS_URLS_REGEX = r"^/api/trail$"

# The frontend only issues POST (plus the OPTIONS preflight) with JSON.
CORS_ALLOW_METHODS = ["OPTIONS", "POST"]
CORS_ALLOW_HEADERS = ["content-type"]


# --- Database ----------------------------------------------------------------
#
# No Django ORM or models are used; trails are computed per request from plain
# dataclasses and never persisted. Django still requires a DATABASES setting to
# initialize, so the default sqlite3 backend is configured minimally. No
# migrations are run and the database file is never created in normal operation.
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
    }
}


# --- Internationalization ----------------------------------------------------

# All user-facing text is English, en-US (Req 7.7).
LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = False
USE_TZ = True

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

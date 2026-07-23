"""Shared base settings for the LiveCanvas backend.

Flavor-specific modules (``dev``, ``prod``) import from this file and override the
minimum necessary. Exactly two flavors exist — no ``staging`` (Constitution VIII).

All configuration is read from the environment via ``django-environ``. Secrets have
NO hardcoded values here; flavors decide whether a sane local default is acceptable
(dev) or whether a missing value must fail fast (prod).
"""

import os
from pathlib import Path

import environ

# ---------------------------------------------------------------------------
# Paths & environment
# ---------------------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent.parent.parent

env = environ.Env()

# Load the flavor-specific env file (.env.dev / .env.prod) if present. The flavor is
# derived from DJANGO_SETTINGS_MODULE. read_env uses setdefault semantics, so real
# environment variables (e.g. those injected by CI or the shell) always win over the
# file. A missing file is fine — values then come solely from the environment.
_flavor = os.environ.get("DJANGO_SETTINGS_MODULE", "config.settings.dev").rsplit(".", 1)[-1]
_env_file = BASE_DIR / f".env.{_flavor}"
if _env_file.exists():
    env.read_env(str(_env_file))

# Environment value catalog (see specs/BE-001-project-bootstrap/data-model.md):
#   SECRET_KEY, DATABASE_URL, ALLOWED_HOSTS, X_APP_KEY (reserved, not enforced),
#   DJANGO_LOG_LEVEL. Flavor modules read these; base only declares shared defaults.

# X-App-Key is declared here for BE-002 (app-tier auth) but is NOT enforced yet.
X_APP_KEY = env("X_APP_KEY", default="")

# ---------------------------------------------------------------------------
# Applications
# ---------------------------------------------------------------------------
INSTALLED_APPS = [
    # Django built-in admin retained as an internal-staff tool (spec FR-019).
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # Third-party
    "rest_framework",
    # Local
    "core",
    "apps.wallpapers",
    "apps.uploads",
    "apps.iap",
]

# ---------------------------------------------------------------------------
# Django REST Framework (Constitution IV, VI)
# ---------------------------------------------------------------------------
# App-tier auth is OPT-IN PER TIER via core.api.AppTierAPIView — NEVER a global
# default — so the admin tier (BE-004) stays strictly isolated (Constitution II).
# The pagination default (cursor envelope) is wired once list endpoints exist; the
# class is added to this block in BE-002 US3.
REST_FRAMEWORK = {
    "EXCEPTION_HANDLER": "core.exception_handler.structured_exception_handler",
    "DEFAULT_AUTHENTICATION_CLASSES": [],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.AllowAny"],
    "DEFAULT_PAGINATION_CLASS": "core.pagination.EnvelopeCursorPagination",
    "PAGE_SIZE": 20,
}

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
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
ASGI_APPLICATION = "config.asgi.application"

# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------
# DATABASES is defined per flavor: dev supplies a local docker-compose default,
# prod requires DATABASE_URL with NO default (fail-fast). See dev.py / prod.py.

# ---------------------------------------------------------------------------
# Password validation (for internal-staff admin accounts)
# ---------------------------------------------------------------------------
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# ---------------------------------------------------------------------------
# I18N / TZ
# ---------------------------------------------------------------------------
LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

# ---------------------------------------------------------------------------
# Static files (Django admin only in this spec)
# ---------------------------------------------------------------------------
STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# ---------------------------------------------------------------------------
# Object storage & CDN (BE-002 — configuration only; no upload logic until BE-004)
# ---------------------------------------------------------------------------
# S3-compatible object storage via django-storages. Provider-agnostic: AWS S3 /
# Cloudflare R2 / DO Spaces differ only by endpoint/region. base declares the env
# catalog with declared-not-required defaults; the STORAGES backend is chosen per
# flavor (dev → local FileSystemStorage fallback; prod → S3Storage, fail-fast).
AWS_STORAGE_BUCKET_NAME = env("AWS_STORAGE_BUCKET_NAME", default="")
AWS_S3_ENDPOINT_URL = env("AWS_S3_ENDPOINT_URL", default="")
AWS_S3_REGION_NAME = env("AWS_S3_REGION_NAME", default="")
AWS_ACCESS_KEY_ID = env("AWS_ACCESS_KEY_ID", default="")
AWS_SECRET_ACCESS_KEY = env("AWS_SECRET_ACCESS_KEY", default="")
# Public base URL a CDN serves objects from (used by later specs to build media URLs).
CDN_BASE_URL = env("CDN_BASE_URL", default="")

# ---------------------------------------------------------------------------
# Logging level (flavors override handlers/formatters)
# ---------------------------------------------------------------------------
DJANGO_LOG_LEVEL = env("DJANGO_LOG_LEVEL", default="INFO")

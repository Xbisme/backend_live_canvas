"""Prod flavor settings.

Hardened for production: debug off, strict hosts, transport/security headers,
whitenoise-served admin static, and structured JSON logging. Required secrets are
read with NO default so a missing value fails fast at startup (spec FR-011).
"""

from config.settings.base import *  # noqa: F401,F403
from config.settings.base import DJANGO_LOG_LEVEL, MIDDLEWARE, env

DEBUG = False

# Required — no defaults. Missing values raise ImproperlyConfigured at import.
SECRET_KEY = env("SECRET_KEY")
ALLOWED_HOSTS = env.list("ALLOWED_HOSTS")

DATABASES = {
    "default": env.db("DATABASE_URL"),
}

# App-tier key MUST be configured in prod — fail-closed, never a silent open door
# (spec FR-021). Read with no default so a missing/empty value fails fast at startup.
X_APP_KEY = env("X_APP_KEY")
if not X_APP_KEY:
    from django.core.exceptions import ImproperlyConfigured

    raise ImproperlyConfigured("X_APP_KEY must be set (non-empty) in the prod flavor.")

# ---------------------------------------------------------------------------
# Security hardening
# ---------------------------------------------------------------------------
# TLS is terminated by an upstream proxy/load balancer.
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_SSL_REDIRECT = True
SECURE_HSTS_SECONDS = 31_536_000  # 1 year
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
SECURE_CONTENT_TYPE_NOSNIFF = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True

# ---------------------------------------------------------------------------
# Static files — whitenoise serves the built-in admin's assets in prod.
# ---------------------------------------------------------------------------
# Insert whitenoise directly after SecurityMiddleware.
MIDDLEWARE = [
    MIDDLEWARE[0],
    "whitenoise.middleware.WhiteNoiseMiddleware",
    *MIDDLEWARE[1:],
]

# ---------------------------------------------------------------------------
# Object storage & CDN — real S3-compatible backend; required config fails fast.
# ---------------------------------------------------------------------------
# Read the required storage/CDN values with NO default (spec FR-011). Provider-agnostic:
# region/endpoint are optional (AWS uses region; R2/Spaces use an endpoint).
AWS_STORAGE_BUCKET_NAME = env("AWS_STORAGE_BUCKET_NAME")  # private zone (staging + masters)
AWS_PUBLIC_BUCKET_NAME = env("AWS_PUBLIC_BUCKET_NAME")  # public zone (thumbs/previews/covers)
AWS_ACCESS_KEY_ID = env("AWS_ACCESS_KEY_ID")
AWS_SECRET_ACCESS_KEY = env("AWS_SECRET_ACCESS_KEY")
CDN_BASE_URL = env("CDN_BASE_URL")

# Async media pipeline broker (BE-004) — required, no default (fail-fast).
CELERY_BROKER_URL = env("CELERY_BROKER_URL")

STORAGES = {
    "default": {
        "BACKEND": "storages.backends.s3.S3Storage",
    },
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
    },
}

# ---------------------------------------------------------------------------
# Structured JSON logging to stdout.
# ---------------------------------------------------------------------------
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "json": {
            "()": "pythonjsonlogger.json.JsonFormatter",
            "format": "%(asctime)s %(levelname)s %(name)s %(message)s",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "json",
        },
    },
    "root": {
        "handlers": ["console"],
        "level": DJANGO_LOG_LEVEL,
    },
}

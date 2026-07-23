"""Dev flavor settings.

Optimized for local ergonomics: debug on, permissive hosts, verbose console logging,
and a local docker-compose Postgres default. NOT reachable in production.
"""

from config.settings.base import *  # noqa: F401,F403
from config.settings.base import (
    AWS_S3_ENDPOINT_URL,
    AWS_STORAGE_BUCKET_NAME,
    BASE_DIR,
    CDN_BASE_URL,
    DJANGO_LOG_LEVEL,
    env,
)

DEBUG = True

SECRET_KEY = env("SECRET_KEY", default="dev-insecure-change-me")

ALLOWED_HOSTS = env.list("ALLOWED_HOSTS", default=["localhost", "127.0.0.1", "*"])

# Local Postgres from docker-compose.yml (parity with prod engine).
DATABASES = {
    "default": env.db(
        "DATABASE_URL",
        default="postgres://livecanvas:livecanvas@localhost:5432/livecanvas",
    ),
}

# ---------------------------------------------------------------------------
# Object storage — local fallback by default; optional MinIO/S3 when configured.
# ---------------------------------------------------------------------------
# Boots with no external credentials (spec FR-010): store to the local filesystem
# unless BOTH an S3 endpoint and a bucket are provided (e.g. a local MinIO).
if AWS_S3_ENDPOINT_URL and AWS_STORAGE_BUCKET_NAME:
    STORAGES = {
        "default": {"BACKEND": "storages.backends.s3.S3Storage"},
        "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
    }
else:
    STORAGES = {
        "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
        "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
    }

MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / "media"
# Fall back to the local media URL when no CDN is configured (dev ergonomics).
CDN_BASE_URL = CDN_BASE_URL or MEDIA_URL

# Verbose human-readable console logging.
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {
            "format": "[{asctime}] {levelname} {name}: {message}",
            "style": "{",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "verbose",
        },
    },
    "root": {
        "handlers": ["console"],
        "level": DJANGO_LOG_LEVEL,
    },
}

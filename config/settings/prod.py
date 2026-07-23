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

STORAGES = {
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
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

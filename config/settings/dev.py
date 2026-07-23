"""Dev flavor settings.

Optimized for local ergonomics: debug on, permissive hosts, verbose console logging,
and a local docker-compose Postgres default. NOT reachable in production.
"""

from config.settings.base import *  # noqa: F401,F403
from config.settings.base import DJANGO_LOG_LEVEL, env

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

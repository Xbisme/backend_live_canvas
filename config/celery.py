"""Celery application for the async media pipeline (BE-004, Constitution VII).

The worker runs the same codebase as the API (``celery -A config worker``). Task
outcome is reflected in ``Wallpaper.status`` — deliberately no result backend
(research D2). Broker URL comes from the flavor env (``CELERY_BROKER_URL``).
"""

import os

from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.dev")

app = Celery("config")
# All Celery settings live in Django settings under the CELERY_ prefix.
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()

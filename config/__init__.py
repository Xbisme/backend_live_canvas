"""LiveCanvas backend project package.

Importing the Celery app here makes ``@shared_task`` bind to it for both the web
process and the worker (``celery -A config worker``) — standard Django+Celery wiring
(BE-004).
"""

from config.celery import app as celery_app

__all__ = ["celery_app"]

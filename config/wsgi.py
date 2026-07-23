"""WSGI config for the LiveCanvas backend.

Exposes the WSGI callable as a module-level variable named ``application``.
Defaults to the dev flavor; production overrides ``DJANGO_SETTINGS_MODULE`` in the
environment (e.g. ``config.settings.prod``) before launching gunicorn.
"""

import os

from django.core.wsgi import get_wsgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.dev")

application = get_wsgi_application()

"""ASGI config for the LiveCanvas backend.

Exposes the ASGI callable as a module-level variable named ``application``.
Defaults to the dev flavor; production overrides ``DJANGO_SETTINGS_MODULE`` in the
environment before launching an ASGI server.
"""

import os

from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.dev")

application = get_asgi_application()

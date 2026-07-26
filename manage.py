#!/usr/bin/env python
"""Django's command-line utility for administrative tasks."""

import os
import sys


def _is_addr(token: str) -> bool:
    """A runserver positional address is a bare port (`8000`) or `host:port`."""
    return token.isdigit() or (":" in token and token.rsplit(":", 1)[-1].isdigit())


def _with_default_addr(argv: list[str]) -> list[str]:
    """Bind the dev server to all interfaces by default.

    `python manage.py runserver` normally listens on 127.0.0.1, unreachable
    from other machines. Binding 0.0.0.0:8000 lets both the Android emulator
    (via its 10.0.2.2 host alias) and a real device on the same Wi-Fi (via the
    machine's LAN IP) reach it. An explicit address still wins, e.g.
    `runserver 127.0.0.1:9000`.
    """
    if "runserver" not in argv:
        return argv
    rest = argv[argv.index("runserver") + 1 :]
    if any(_is_addr(token) for token in rest):
        return argv
    return argv + ["0.0.0.0:8000"]


def main() -> None:
    """Run administrative tasks (defaults to the dev flavor)."""
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.dev")
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:  # pragma: no cover
        raise ImportError(
            "Couldn't import Django. Are you sure it's installed and "
            "available on your PYTHONPATH environment variable? Did you "
            "forget to activate a virtual environment?"
        ) from exc
    execute_from_command_line(_with_default_addr(sys.argv))


if __name__ == "__main__":
    main()

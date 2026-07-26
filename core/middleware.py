"""Dev-only middleware.

`DevMediaHostRewriteMiddleware` exists because thumbnail/preview/cover URLs are
persisted in the DB with whatever ``CDN_BASE_URL`` was set at upload time — in
local dev that is ``http://localhost:9000`` (MinIO). ``localhost`` is
unreachable from anything but the dev machine itself, so a phone or emulator
loading the app gets metadata but no media.

Rather than rewrite stored rows (which break again on the next IP/Wi-Fi change),
this rewrites loopback media hosts in JSON responses to the exact host the
client used to reach the API. A real device that called ``192.168.1.243:8000``
gets media at ``192.168.1.243:9000``; the Android emulator that called
``10.0.2.2:8000`` gets ``10.0.2.2:9000``. Zero per-IP config, dev-only.
"""

from __future__ import annotations

from collections.abc import Callable

from django.http import HttpRequest, HttpResponse

# Loopback authorities (host[:port]) as they appear in stored media URLs. Only
# the ``:9000`` MinIO port is rewritten — the API host itself is never touched.
_LOOPBACK_HOSTS = (b"localhost", b"127.0.0.1", b"0.0.0.0")
_MEDIA_PORT = b"9000"


class DevMediaHostRewriteMiddleware:
    """Rewrite ``http://<loopback>:9000`` media URLs to the request's own host."""

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        response = self.get_response(request)

        content_type = response.get("Content-Type", "")
        if "application/json" not in content_type or not hasattr(response, "content"):
            return response

        host = request.get_host().split(":")[0]
        # No-op when the caller already used a loopback host, and for the Django
        # test client's default host (keeps API tests asserting stored URLs green).
        if not host or host in ("localhost", "127.0.0.1", "0.0.0.0", "testserver"):
            return response

        body = response.content
        target = f"://{host}:".encode() + _MEDIA_PORT
        for loopback in _LOOPBACK_HOSTS:
            body = body.replace(b"://" + loopback + b":" + _MEDIA_PORT, target)

        if body != response.content:
            response.content = body  # HttpResponse recomputes Content-Length

        return response

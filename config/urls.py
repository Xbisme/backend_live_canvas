"""Root URL configuration.

- ``admin/``  → Django's built-in admin (internal-staff tool, spec FR-019)
- ``/``       → core app routes (operational health endpoints)

Note: the product API (public / IAP / custom admin) is added in later specs and is
governed by ``contracts/openapi.yaml``. The health endpoints under core are
operational and intentionally not part of that contract.
"""

from django.contrib import admin
from django.http import JsonResponse
from django.urls import include, path

from core.errors import ErrorCode

urlpatterns = [
    # Product API (contract v0.4.0). ORDER MATTERS: the custom /admin/* API routes must
    # come BEFORE the Django-admin mount — django.contrib.admin ships a catch-all view
    # under "admin/" that would otherwise swallow /admin/auth/*, /admin/wallpapers, …
    path("", include("core.urls")),  # health + /admin/auth/*
    path("", include("apps.wallpapers.urls")),  # public content endpoints
    path("", include("apps.wallpapers.urls_admin")),  # /admin/wallpapers|tags|collections
    path("", include("apps.uploads.urls")),  # /admin/uploads/presign
    # Django's built-in admin (internal-staff tool, spec FR-019) — keep LAST.
    path("admin/", admin.site.urls),
]


def _envelope(code: str, message: str, status: int) -> JsonResponse:
    return JsonResponse({"error": {"code": code, "message": message}}, status=status)


def handler404(request, exception):  # noqa: ARG001 — Django handler signature
    """Envelope for unmatched URLs (used when DEBUG=False). API 404s raised inside a
    DRF view are handled by core.exception_handler in every flavor."""
    return _envelope(ErrorCode.NOT_FOUND, "Resource not found.", 404)


def handler500(request):  # noqa: ARG001 — Django handler signature
    """Envelope for non-DRF server errors (used when DEBUG=False)."""
    return _envelope(ErrorCode.SERVER_ERROR, "An unexpected error occurred.", 500)

"""Cursor pagination for GET /wallpapers.

Extends the BE-002 envelope pagination with a stable keyset ordering ``(-created_at, -id)`` so
pages never duplicate or skip when rows are inserted (research R1, SC-002), and maps a bad/expired
cursor to ``400 VALIDATION_ERROR`` instead of DRF's default ``NotFound`` → 404
(Constitution VI, spec FR-008, research R1 / analyze U1).
"""

from rest_framework.exceptions import NotFound

from core.errors import ValidationFailed
from core.pagination import EnvelopeCursorPagination


class WallpaperCursorPagination(EnvelopeCursorPagination):
    ordering = ("-created_at", "-id")

    def decode_cursor(self, request):
        try:
            return super().decode_cursor(request)
        except NotFound as exc:
            raise ValidationFailed("Invalid or expired cursor.") from exc

    def get_page_size(self, request) -> int:
        """Reject a malformed or too-large ``limit`` with 400 instead of DRF's silent clamp
        (contract: ``limit`` > 100 → VALIDATION_ERROR, spec FR-008)."""
        raw = request.query_params.get(self.page_size_query_param)
        if raw is not None:
            try:
                value = int(raw)
            except (TypeError, ValueError) as exc:
                raise ValidationFailed(f"Invalid limit: {raw!r}.") from exc
            if value < 1 or value > self.max_page_size:
                raise ValidationFailed(f"limit must be between 1 and {self.max_page_size}.")
            return value
        return self.page_size

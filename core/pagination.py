"""Cursor pagination emitting the contract envelope.

The product contract (``.claude/api-context.md`` §Cursor Pagination) specifies
``{ "items": [...], "next_cursor": <str|null>, "has_more": <bool> }`` with an opaque
keyset cursor — not DRF's default ``{next, previous, results}`` (which also leaks the
host in absolute URLs). This subclass keeps DRF's proven cursor encode/decode and only
overrides the response body (Constitution VI). Offset pagination is never used.
"""

from urllib.parse import parse_qs, urlparse

from rest_framework.pagination import CursorPagination
from rest_framework.response import Response


class EnvelopeCursorPagination(CursorPagination):
    """Keyset pagination with the LiveCanvas response envelope."""

    page_size = 20
    max_page_size = 100
    page_size_query_param = "limit"
    cursor_query_param = "cursor"
    ordering = "-created_at"  # overridable per-view; models with this field arrive in BE-003

    def _cursor_from_link(self, link: str | None) -> str | None:
        """Extract just the opaque cursor token from a DRF next/previous link."""
        if not link:
            return None
        values = parse_qs(urlparse(link).query).get(self.cursor_query_param)
        return values[0] if values else None

    def get_paginated_response(self, data) -> Response:
        next_cursor = self._cursor_from_link(self.get_next_link())
        return Response(
            {
                "items": data,
                "next_cursor": next_cursor,
                "has_more": next_cursor is not None,
            }
        )

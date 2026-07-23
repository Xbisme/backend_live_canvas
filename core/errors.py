"""Error-code catalog and custom API exceptions.

Single in-code mirror of the Error-Code Catalog in ``.claude/api-context.md`` — the
one source the centralized exception handler (``core.exception_handler``) reads to map
failures onto the structured envelope ``{ "error": { "code", "message" } }``
(Constitution IV). Adding/removing a code here is a contract change (Constitution I).

BE-002 raises only a small subset (``INVALID_APP_KEY``, ``VALIDATION_ERROR``,
``NOT_FOUND``, ``METHOD_NOT_ALLOWED``, ``SERVER_ERROR``); the rest are declared for
completeness and consumed by later specs.
"""

from rest_framework import status
from rest_framework.exceptions import APIException


class ErrorCode:
    """Stable, machine-consumable error codes. Values are part of the API contract.

    Mirrors ``.claude/api-context.md`` §Error Code Catalog (contract v0.3.1).
    """

    # --- Auth ---
    INVALID_APP_KEY = "INVALID_APP_KEY"
    UNAUTHORIZED_ADMIN = "UNAUTHORIZED_ADMIN"
    FORBIDDEN_ADMIN_ROLE = "FORBIDDEN_ADMIN_ROLE"

    # --- Generic request/handling ---
    VALIDATION_ERROR = "VALIDATION_ERROR"
    NOT_FOUND = "NOT_FOUND"
    METHOD_NOT_ALLOWED = "METHOD_NOT_ALLOWED"  # new in v0.3.1
    SERVER_ERROR = "SERVER_ERROR"  # new in v0.3.1

    # --- Entitlement / IAP (BE-005) ---
    ENTITLEMENT_REQUIRED = "ENTITLEMENT_REQUIRED"
    RECEIPT_INVALID = "RECEIPT_INVALID"
    RECEIPT_CONFLICT = "RECEIPT_CONFLICT"
    STORE_API_UNAVAILABLE = "STORE_API_UNAVAILABLE"
    WEBHOOK_SIGNATURE_INVALID = "WEBHOOK_SIGNATURE_INVALID"

    # --- Uploads / curated integrity (BE-004) ---
    FILE_REJECTED = "FILE_REJECTED"
    TAG_NOT_FOUND = "TAG_NOT_FOUND"
    TAG_SLUG_CONFLICT = "TAG_SLUG_CONFLICT"
    TAG_IN_USE = "TAG_IN_USE"
    WALLPAPER_NOT_FOUND = "WALLPAPER_NOT_FOUND"
    COLLECTION_SLUG_CONFLICT = "COLLECTION_SLUG_CONFLICT"


class AppError(APIException):
    """Base for application errors rendered into the structured envelope.

    Subclasses set ``error_code``, ``status_code``, and ``default_detail``. The
    exception handler reads ``error_code`` for the envelope ``code`` and ``detail``
    for the ``message``.
    """

    error_code = ErrorCode.SERVER_ERROR
    status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
    default_detail = "An unexpected error occurred."


class InvalidAppKey(AppError):
    """Missing, wrong, or (server-side) unconfigured ``X-App-Key`` — app tier."""

    error_code = ErrorCode.INVALID_APP_KEY
    status_code = status.HTTP_401_UNAUTHORIZED
    default_detail = "Missing or invalid application key."

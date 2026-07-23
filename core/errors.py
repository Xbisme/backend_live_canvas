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


class ValidationFailed(AppError):
    """Malformed request (bad query/body). Also used for invalid/expired cursors so the
    contract's 400 ``VALIDATION_ERROR`` is honored instead of DRF's default 404 for a bad
    cursor (Constitution VI, spec FR-008)."""

    error_code = ErrorCode.VALIDATION_ERROR
    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = "Request could not be validated."


class UnauthorizedAdmin(AppError):
    """Missing/malformed/expired/blacklisted admin JWT, or wrong login credentials —
    admin tier (BE-004, Constitution II). Deliberately indistinguishable causes."""

    error_code = ErrorCode.UNAUTHORIZED_ADMIN
    status_code = status.HTTP_401_UNAUTHORIZED
    default_detail = "Missing or invalid admin credentials."


class ForbiddenAdminRole(AppError):
    """Valid credentials but the account is not staff (or is disabled) — admin tier."""

    error_code = ErrorCode.FORBIDDEN_ADMIN_ROLE
    status_code = status.HTTP_403_FORBIDDEN
    default_detail = "This account is not permitted to use the admin API."


class FileRejected(AppError):
    """Uploaded file fails validation — synchronous cases only (size ceiling at register;
    content sniffing happens async and surfaces as ``status=failed``, spec FR-011)."""

    error_code = ErrorCode.FILE_REJECTED
    status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
    default_detail = "The uploaded file was rejected."


class TagNotFound(AppError):
    """``tag_ids`` references a tag that does not exist (curated integrity, Constitution IX)."""

    error_code = ErrorCode.TAG_NOT_FOUND
    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = "One or more tags do not exist."


class TagSlugConflict(AppError):
    """Creating a tag whose slug already exists."""

    error_code = ErrorCode.TAG_SLUG_CONFLICT
    status_code = status.HTTP_409_CONFLICT
    default_detail = "A tag with this slug already exists."


class TagInUse(AppError):
    """Deleting a tag still attached to wallpapers (curated integrity, Constitution IX)."""

    error_code = ErrorCode.TAG_IN_USE
    status_code = status.HTTP_409_CONFLICT
    default_detail = "This tag is still attached to wallpapers."


class WallpaperNotFound(AppError):
    """``wallpaper_ids`` references a wallpaper that does not exist (collections admin)."""

    error_code = ErrorCode.WALLPAPER_NOT_FOUND
    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = "One or more wallpapers do not exist."


class CollectionSlugConflict(AppError):
    """Creating/renaming a collection to a slug that already exists."""

    error_code = ErrorCode.COLLECTION_SLUG_CONFLICT
    status_code = status.HTTP_409_CONFLICT
    default_detail = "A collection with this slug already exists."


class EntitlementRequired(AppError):
    """Premium content requested without an active entitlement — gated at the download edge
    (Constitution III). In BE-003 premium always returns this until IAP verification lands in
    BE-005; the code is part of the frozen catalog (contract v0.3.2)."""

    error_code = ErrorCode.ENTITLEMENT_REQUIRED
    status_code = status.HTTP_402_PAYMENT_REQUIRED
    default_detail = "This wallpaper requires an active premium entitlement."

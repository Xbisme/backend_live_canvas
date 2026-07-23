"""Centralized DRF exception handler → the structured error envelope.

Every API error is rendered as ``{ "error": { "code": <CODE>, "message": "..." } }``
with ``code`` from ``core.errors.ErrorCode`` (Constitution IV). This is the single
place errors are shaped — views MUST NOT build ad-hoc error bodies. Raw exceptions and
tracebacks never reach the client; unhandled failures are logged server-side only.

Note: this hook runs for exceptions raised inside DRF views. Unmatched-URL 404s and
non-DRF 500s are covered by ``config.urls`` ``handler404`` / ``handler500`` (used when
``DEBUG=False``); API 404s should be raised as ``Http404`` inside a DRF view so they
route through here in every flavor.
"""

import logging

from django.http import Http404
from rest_framework import exceptions as drf_exceptions
from rest_framework.response import Response
from rest_framework.views import exception_handler as drf_exception_handler

from core.errors import AppError, ErrorCode

logger = logging.getLogger("core.errors")

_GENERIC_SERVER_MESSAGE = "An unexpected error occurred."

# Fallback map for DRF-handled responses whose exception type we do not special-case.
_STATUS_TO_CODE = {
    400: ErrorCode.VALIDATION_ERROR,
    401: ErrorCode.INVALID_APP_KEY,
    404: ErrorCode.NOT_FOUND,
    405: ErrorCode.METHOD_NOT_ALLOWED,
}


def _code_for(exc, response) -> str:
    """Resolve the catalog code for an exception (falls back by HTTP status)."""
    if isinstance(exc, AppError):
        return exc.error_code
    if isinstance(exc, (Http404, drf_exceptions.NotFound)):
        return ErrorCode.NOT_FOUND
    if isinstance(exc, drf_exceptions.MethodNotAllowed):
        return ErrorCode.METHOD_NOT_ALLOWED
    if isinstance(exc, (drf_exceptions.NotAuthenticated, drf_exceptions.AuthenticationFailed)):
        # BE-002 has only the app tier on DRF views; the admin tier (BE-004) will need
        # per-tier resolution when it lands.
        return ErrorCode.INVALID_APP_KEY
    if isinstance(exc, (drf_exceptions.ValidationError, drf_exceptions.ParseError)):
        return ErrorCode.VALIDATION_ERROR
    if response is not None:
        return _STATUS_TO_CODE.get(response.status_code, ErrorCode.SERVER_ERROR)
    return ErrorCode.SERVER_ERROR


def _flatten_detail(detail) -> str:
    """Reduce a DRF error detail (str / list / dict) to a single readable message."""
    if isinstance(detail, dict):
        for key, value in detail.items():
            msg = _flatten_detail(value)
            if msg:
                return msg if key == "non_field_errors" else f"{key}: {msg}"
    elif isinstance(detail, (list, tuple)):
        for item in detail:
            msg = _flatten_detail(item)
            if msg:
                return msg
    elif detail is not None:
        return str(detail)
    return ""


def _message_for(exc, code: str) -> str:
    """Client-safe message. Server errors never expose internal detail."""
    if code == ErrorCode.SERVER_ERROR:
        return _GENERIC_SERVER_MESSAGE
    message = _flatten_detail(getattr(exc, "detail", None))
    return message or "Request could not be processed."


def structured_exception_handler(exc, context):
    """DRF ``EXCEPTION_HANDLER`` — normalize every error to the envelope."""
    response = drf_exception_handler(exc, context)

    if response is None:
        # Non-DRF / unexpected exception: log the full trace server-side, return a
        # generic 500 envelope with no internal detail.
        request = context.get("request") if context else None
        logger.exception("Unhandled exception at %s", getattr(request, "path", "<unknown>"))
        return Response(
            {"error": {"code": ErrorCode.SERVER_ERROR, "message": _GENERIC_SERVER_MESSAGE}},
            status=500,
        )

    code = _code_for(exc, response)
    response.data = {"error": {"code": code, "message": _message_for(exc, code)}}
    return response

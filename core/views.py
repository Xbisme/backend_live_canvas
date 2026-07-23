"""Operational health endpoints.

These are ops signals for developers and orchestration — intentionally NOT part of
the product API contract (contracts/openapi.yaml). See
specs/BE-001-project-bootstrap/contracts/health-endpoints.md.
"""

from django.db import connection
from django.http import Http404
from rest_framework import status
from rest_framework.exceptions import ValidationError
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from core.api import AppTierAPIView


class LivenessView(APIView):
    """Liveness: the process is up and serving. Touches no dependencies."""

    authentication_classes: list = []
    permission_classes: list = []

    def get(self, request: Request) -> Response:
        return Response({"status": "ok"}, status=status.HTTP_200_OK)


class ReadinessView(APIView):
    """Readiness: the database dependency is reachable.

    Runs a trivial ``SELECT 1``. Returns 200 when the DB answers, 503 otherwise.
    """

    authentication_classes: list = []
    permission_classes: list = []

    def get(self, request: Request) -> Response:
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
                cursor.fetchone()
        except Exception:  # noqa: BLE001 — any DB error means "not ready"
            return Response(
                {"status": "unavailable"},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        return Response({"status": "ready"}, status=status.HTTP_200_OK)


# ---------------------------------------------------------------------------
# Temporary foundation probes (BE-002 validation only — NOT part of the product
# contract). These exercise the app-tier X-App-Key gate and the structured error
# envelope end-to-end before any business endpoint exists; remove in BE-003 once real
# app-tier endpoints are available. See specs/BE-002-backend-foundation/research.md R6.
# ---------------------------------------------------------------------------


class AppTierProbeView(AppTierAPIView):
    """Succeeds (200) only when a valid ``X-App-Key`` is presented — US1 probe."""

    def get(self, request: Request) -> Response:
        return Response({"ok": True}, status=status.HTTP_200_OK)


class ProbeValidationView(AppTierAPIView):
    """Raises a DRF ``ValidationError`` → 400 ``VALIDATION_ERROR`` — US2 probe."""

    def get(self, request: Request) -> Response:
        raise ValidationError("Invalid probe input.")


class ProbeNotFoundView(AppTierAPIView):
    """Raises ``Http404`` → 404 ``NOT_FOUND`` (routes through the DRF handler in every
    flavor, unlike an unmatched URL) — US2 probe."""

    def get(self, request: Request) -> Response:
        raise Http404("Probe resource does not exist.")


class ProbeBoomView(AppTierAPIView):
    """Raises an unhandled exception → 500 ``SERVER_ERROR``, no traceback — US2 probe."""

    def get(self, request: Request) -> Response:
        raise RuntimeError("Intentional probe failure — should never leak to the client.")

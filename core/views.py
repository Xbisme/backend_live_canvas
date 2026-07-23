"""Operational health endpoints.

These are ops signals for developers and orchestration — intentionally NOT part of
the product API contract (contracts/openapi.yaml). See
specs/BE-001-project-bootstrap/contracts/health-endpoints.md.
"""

from django.db import connection
from rest_framework import status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView


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

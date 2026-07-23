"""Health endpoint tests (spec FR-018).

Covers liveness (always up), readiness when the DB is reachable, and readiness when
the DB check fails — the failure path is simulated by patching the cursor to raise,
so no real database outage is required (deterministic, Constitution X).
"""

from unittest import mock

import pytest
from rest_framework import status
from rest_framework.test import APIClient


@pytest.fixture
def client() -> APIClient:
    return APIClient()


def test_liveness_returns_ok(client: APIClient) -> None:
    response = client.get("/health")
    assert response.status_code == status.HTTP_200_OK
    assert response.json() == {"status": "ok"}


@pytest.mark.django_db
def test_readiness_ok_when_db_reachable(client: APIClient) -> None:
    response = client.get("/health/ready")
    assert response.status_code == status.HTTP_200_OK
    assert response.json() == {"status": "ready"}


def test_readiness_503_when_db_unavailable(client: APIClient) -> None:
    # Force the DB check to raise, simulating an unreachable database.
    with mock.patch("core.views.connection.cursor", side_effect=Exception("db down")):
        response = client.get("/health/ready")
    assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
    assert response.json() == {"status": "unavailable"}


def test_liveness_unaffected_by_db(client: APIClient) -> None:
    # Even if the DB were down, liveness must still report ok.
    with mock.patch("core.views.connection.cursor", side_effect=Exception("db down")):
        response = client.get("/health")
    assert response.status_code == status.HTTP_200_OK
    assert response.json() == {"status": "ok"}

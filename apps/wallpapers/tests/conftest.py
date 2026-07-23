"""Shared fixtures for content API tests."""

import pytest
from rest_framework.test import APIClient

APP_KEY = "test-app-key"


@pytest.fixture
def api(settings) -> APIClient:
    """APIClient pre-authenticated for the app tier (valid ``X-App-Key``)."""
    settings.X_APP_KEY = APP_KEY
    client = APIClient()
    client.credentials(HTTP_X_APP_KEY=APP_KEY)
    return client


@pytest.fixture
def anon(settings) -> APIClient:
    """APIClient with no app key — for asserting 401 on the app tier."""
    settings.X_APP_KEY = APP_KEY
    return APIClient()

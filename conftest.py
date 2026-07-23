"""Project-wide test fixtures (BE-004): admin-tier principals and clients.

Content-domain fixtures stay in ``apps/wallpapers/tests/conftest.py``; these are the
cross-app admin-auth building blocks used by core, uploads, wallpapers, and audit tests.
"""

import pytest
from django.contrib.auth.models import User
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

ADMIN_PASSWORD = "s3cure-admin-pass"  # noqa: S105 — test-only credential
APP_KEY = "test-app-key"


@pytest.fixture
def api(settings) -> APIClient:
    """App-tier client (valid ``X-App-Key``) — project-wide twin of the wallpapers fixture."""
    settings.X_APP_KEY = APP_KEY
    client = APIClient()
    client.credentials(HTTP_X_APP_KEY=APP_KEY)
    return client


@pytest.fixture
def admin_user(db) -> User:
    """An active staff user — the only principal the admin tier accepts."""
    return User.objects.create_user(
        username="admin", password=ADMIN_PASSWORD, is_staff=True, is_active=True
    )


@pytest.fixture
def non_staff_user(db) -> User:
    return User.objects.create_user(
        username="mortal", password=ADMIN_PASSWORD, is_staff=False, is_active=True
    )


@pytest.fixture
def admin_access_token(admin_user) -> str:
    return str(RefreshToken.for_user(admin_user).access_token)


@pytest.fixture
def admin_client(admin_access_token) -> APIClient:
    """APIClient authenticated for the admin tier (Bearer JWT of a staff user)."""
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {admin_access_token}")
    return client

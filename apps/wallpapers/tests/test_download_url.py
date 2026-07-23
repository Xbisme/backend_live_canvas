"""US5 — GET /wallpapers/{id}/download-url (temporary edge). Spec FR-012, Constitution III."""

from datetime import datetime, timedelta

import pytest
from django.utils import timezone

from apps.wallpapers.tests.factories import WallpaperFactory

pytestmark = pytest.mark.django_db


def test_non_premium_returns_200_with_expiry(api):
    wp = WallpaperFactory(is_premium=False)
    resp = api.get(f"/wallpapers/{wp.id}/download-url")
    assert resp.status_code == 200
    body = resp.json()
    assert body["download_url"]
    expires = datetime.fromisoformat(body["expires_at"].replace("Z", "+00:00"))
    # Presigned URLs must be short-lived (≤ 5 minutes, Constitution III).
    assert expires <= timezone.now() + timedelta(minutes=5, seconds=5)


def test_premium_returns_402(api):
    wp = WallpaperFactory(is_premium=True)
    resp = api.get(f"/wallpapers/{wp.id}/download-url")
    assert resp.status_code == 402
    assert resp.json()["error"]["code"] == "ENTITLEMENT_REQUIRED"


def test_missing_returns_404(api):
    resp = api.get("/wallpapers/999999/download-url")
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "NOT_FOUND"


def test_requires_app_key(anon):
    wp = WallpaperFactory()
    assert anon.get(f"/wallpapers/{wp.id}/download-url").status_code == 401

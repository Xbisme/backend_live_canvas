"""US3 — POST /wallpapers/batch. Spec FR-011/013, SC-005."""

import pytest
from django.utils import timezone

from apps.wallpapers.models import WallpaperStatus
from apps.wallpapers.tests.factories import WallpaperFactory

pytestmark = pytest.mark.django_db


def test_batch_skips_missing_ids(api):
    wp = WallpaperFactory()
    resp = api.post("/wallpapers/batch", {"ids": [wp.id, 999999]}, format="json")
    assert resp.status_code == 200
    assert [w["id"] for w in resp.json()] == [wp.id]


def test_batch_excludes_hidden(api):
    published = WallpaperFactory()
    hidden = WallpaperFactory(status=WallpaperStatus.PROCESSING)
    deleted = WallpaperFactory(deleted_at=timezone.now())
    resp = api.post(
        "/wallpapers/batch",
        {"ids": [published.id, hidden.id, deleted.id]},
        format="json",
    )
    assert [w["id"] for w in resp.json()] == [published.id]


def test_batch_empty_is_400(api):
    resp = api.post("/wallpapers/batch", {"ids": []}, format="json")
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "VALIDATION_ERROR"


def test_batch_over_100_is_400(api):
    resp = api.post("/wallpapers/batch", {"ids": list(range(1, 102))}, format="json")
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "VALIDATION_ERROR"


def test_batch_requires_app_key(anon):
    assert anon.post("/wallpapers/batch", {"ids": [1]}, format="json").status_code == 401

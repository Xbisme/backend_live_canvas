"""US2 — GET /wallpapers/{id} detail with populated collections. Spec FR-010/013, SC-005."""

import pytest
from django.utils import timezone

from apps.wallpapers.models import WallpaperStatus
from apps.wallpapers.tests.factories import (
    CollectionItemFactory,
    WallpaperFactory,
)

pytestmark = pytest.mark.django_db


def test_detail_populates_collections(api):
    wp = WallpaperFactory()
    CollectionItemFactory(wallpaper=wp, position=0)

    resp = api.get(f"/wallpapers/{wp.id}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["id"] == wp.id
    assert len(body["collections"]) == 1
    assert set(body["collections"][0].keys()) == {"id", "slug", "title", "cover_url", "is_premium"}


def test_detail_404_for_missing(api):
    resp = api.get("/wallpapers/999999")
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "NOT_FOUND"


@pytest.mark.parametrize(
    "kwargs",
    [{"status": WallpaperStatus.PROCESSING}, {"deleted_at": timezone.now()}],
)
def test_detail_404_for_hidden(api, kwargs):
    wp = WallpaperFactory(**kwargs)
    assert api.get(f"/wallpapers/{wp.id}").status_code == 404


def test_detail_requires_app_key(anon):
    wp = WallpaperFactory()
    assert anon.get(f"/wallpapers/{wp.id}").status_code == 401


# --- Description (US3, contract v0.7.0) --------------------------------------


def test_detail_returns_description(api):
    wp = WallpaperFactory(description="Đèn neon phản chiếu trên mặt đường sau mưa.")
    assert api.get(f"/wallpapers/{wp.id}").json()["description"] == (
        "Đèn neon phản chiếu trên mặt đường sau mưa."
    )


def test_detail_description_is_null_not_empty_string(api):
    """The client hides the block on a null check alone — `""` would render an empty block."""
    wp = WallpaperFactory()
    body = api.get(f"/wallpapers/{wp.id}").json()
    assert "description" in body
    assert body["description"] is None


def test_batch_returns_description(api):
    described = WallpaperFactory(description="có mô tả")
    plain = WallpaperFactory()

    rows = api.post("/wallpapers/batch", {"ids": [described.id, plain.id]}, format="json").json()
    by_id = {row["id"]: row["description"] for row in rows}
    assert by_id[described.id] == "có mô tả"
    assert by_id[plain.id] is None

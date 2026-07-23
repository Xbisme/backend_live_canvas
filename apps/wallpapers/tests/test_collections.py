"""US4 — GET /collections, GET /collections/{id}. Spec FR-006/007, SC-006."""

import pytest
from django.utils import timezone

from apps.wallpapers.models import WallpaperStatus
from apps.wallpapers.tests.factories import (
    CollectionFactory,
    CollectionItemFactory,
    WallpaperFactory,
)

pytestmark = pytest.mark.django_db


def test_collection_list_meta_only(api):
    col = CollectionFactory(slug="neon-nights")
    CollectionItemFactory.create_batch(2, collection=col)

    resp = api.get("/collections")
    assert resp.status_code == 200
    row = next(c for c in resp.json() if c["slug"] == "neon-nights")
    assert row["wallpaper_count"] == 2
    assert "items" not in row


def test_collection_detail_items_in_curated_order(api):
    col = CollectionFactory()
    w1, w2, w3 = WallpaperFactory(), WallpaperFactory(), WallpaperFactory()
    # Insert out of order; positions define display order [w2, w3, w1].
    CollectionItemFactory(collection=col, wallpaper=w1, position=2)
    CollectionItemFactory(collection=col, wallpaper=w2, position=0)
    CollectionItemFactory(collection=col, wallpaper=w3, position=1)

    body = api.get(f"/collections/{col.id}").json()
    assert [w["id"] for w in body["items"]] == [w2.id, w3.id, w1.id]


def test_collection_detail_excludes_hidden_members(api):
    col = CollectionFactory()
    visible = WallpaperFactory()
    hidden = WallpaperFactory(status=WallpaperStatus.PROCESSING)
    deleted = WallpaperFactory(deleted_at=timezone.now())
    CollectionItemFactory(collection=col, wallpaper=visible, position=0)
    CollectionItemFactory(collection=col, wallpaper=hidden, position=1)
    CollectionItemFactory(collection=col, wallpaper=deleted, position=2)

    body = api.get(f"/collections/{col.id}").json()
    assert [w["id"] for w in body["items"]] == [visible.id]


def test_premium_collection_still_returned_in_full(api):
    col = CollectionFactory(is_premium=True)
    CollectionItemFactory(collection=col, position=0)
    body = api.get(f"/collections/{col.id}").json()
    assert body["is_premium"] is True
    assert len(body["items"]) == 1  # gate is at download-url, not here


def test_collection_detail_404(api):
    assert api.get("/collections/999999").status_code == 404


def test_collections_require_app_key(anon):
    assert anon.get("/collections").status_code == 401

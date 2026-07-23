"""US1 — GET /categories, GET /tags (incl. virtual "All"). Spec FR-005/006/006a/014/015."""

import pytest
from django.core.exceptions import ValidationError
from django.utils import timezone

from apps.wallpapers.models import Tag, WallpaperStatus
from apps.wallpapers.tests.factories import (
    CategoryFactory,
    TagFactory,
    WallpaperFactory,
)

pytestmark = pytest.mark.django_db


def test_categories_list_counts_only_published(api):
    cat = CategoryFactory(slug="urban", name="Đô thị")
    WallpaperFactory.create_batch(2, category=cat)  # published
    WallpaperFactory(category=cat, status=WallpaperStatus.PROCESSING)  # hidden
    WallpaperFactory(category=cat, deleted_at=timezone.now())  # soft-deleted

    resp = api.get("/categories")
    assert resp.status_code == 200
    row = next(c for c in resp.json() if c["slug"] == "urban")
    assert row["wallpaper_count"] == 2
    assert set(row.keys()) == {"id", "slug", "name", "icon_url", "wallpaper_count"}


def test_categories_requires_app_key(anon):
    resp = anon.get("/categories")
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "INVALID_APP_KEY"


def test_method_not_allowed(api):
    resp = api.post("/categories", {})
    assert resp.status_code == 405
    assert resp.json()["error"]["code"] == "METHOD_NOT_ALLOWED"


def test_tags_first_element_is_virtual_all(api):
    tag = TagFactory(slug="neon", name="Neon")
    WallpaperFactory(tags=[tag])
    WallpaperFactory()  # published, untagged → counts toward "All" total, not toward "neon"

    resp = api.get("/tags")
    assert resp.status_code == 200
    body = resp.json()

    assert body[0]["id"] == 0
    assert body[0]["slug"] == "all"
    assert body[0]["name"] == "Tất cả"
    assert body[0]["wallpaper_count"] == 2  # total published

    neon = next(t for t in body if t["slug"] == "neon")
    assert neon["wallpaper_count"] == 1
    # No real tag ever carries the reserved slug.
    assert sum(1 for t in body[1:] if t["slug"] == "all") == 0


def test_reserved_slug_rejected_at_model_layer():
    with pytest.raises(ValidationError):
        Tag(slug="all", name="Should fail").full_clean()

"""US1 — GET /wallpapers cursor pagination + filters. Spec FR-008/009/013, SC-002/003."""

import pytest
from django.utils import timezone

from apps.wallpapers.models import WallpaperStatus
from apps.wallpapers.tests.factories import (
    CategoryFactory,
    TagFactory,
    WallpaperFactory,
)

pytestmark = pytest.mark.django_db


def _ids(payload) -> list:
    return [w["id"] for w in payload["items"]]


def test_envelope_and_cursor_paging(api):
    WallpaperFactory.create_batch(5)
    first = api.get("/wallpapers?limit=2").json()
    assert set(first.keys()) == {"items", "next_cursor", "has_more"}
    assert len(first["items"]) == 2
    assert first["has_more"] is True and first["next_cursor"]

    second = api.get(f"/wallpapers?limit=2&cursor={first['next_cursor']}").json()
    # No overlap between consecutive pages.
    assert set(_ids(first)).isdisjoint(_ids(second))


def test_ordering_newest_first(api):
    a = WallpaperFactory(title="old")
    b = WallpaperFactory(title="new")
    ids = _ids(api.get("/wallpapers").json())
    assert ids.index(b.id) < ids.index(a.id)


def test_pagination_stable_when_row_inserted(api):
    WallpaperFactory.create_batch(4)
    page1 = api.get("/wallpapers?limit=2").json()
    WallpaperFactory.create_batch(2)  # insert newer rows mid-iteration
    page2 = api.get(f"/wallpapers?limit=2&cursor={page1['next_cursor']}").json()
    assert set(_ids(page1)).isdisjoint(_ids(page2))


def test_invalid_cursor_is_400(api):
    resp = api.get("/wallpapers?cursor=@@notacursor@@")
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "VALIDATION_ERROR"


def test_limit_over_max_is_400(api):
    resp = api.get("/wallpapers?limit=999")
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "VALIDATION_ERROR"


def test_tags_filter_is_and(api):
    neon, city = TagFactory(slug="neon"), TagFactory(slug="city")
    both = WallpaperFactory(tags=[neon, city])
    WallpaperFactory(tags=[neon])  # only neon → excluded by AND

    ids = _ids(api.get("/wallpapers?tags=neon,city").json())
    assert ids == [both.id]


def test_reserved_all_slug_returns_everything(api):
    WallpaperFactory.create_batch(3)
    assert len(api.get("/wallpapers?tags=all").json()["items"]) == 3


def test_combined_filters(api):
    cat = CategoryFactory(slug="urban")
    match = WallpaperFactory(category=cat, orientation="portrait", is_premium=False)
    WallpaperFactory(category=cat, orientation="landscape", is_premium=False)
    WallpaperFactory(category=cat, orientation="portrait", is_premium=True)

    ids = _ids(api.get("/wallpapers?category=urban&orientation=portrait&is_premium=false").json())
    assert ids == [match.id]


def test_invalid_orientation_is_400(api):
    resp = api.get("/wallpapers?orientation=diagonal")
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "VALIDATION_ERROR"


def test_search_matches_title(api):
    hit = WallpaperFactory(title="Neon City Loop")
    WallpaperFactory(title="Calm Forest")
    ids = _ids(api.get("/wallpapers?search=neon").json())
    assert ids == [hit.id]


def test_hidden_content_never_leaks(api):
    WallpaperFactory(status=WallpaperStatus.PROCESSING)
    WallpaperFactory(deleted_at=timezone.now())
    published = WallpaperFactory()
    assert _ids(api.get("/wallpapers").json()) == [published.id]

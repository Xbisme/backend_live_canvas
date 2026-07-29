"""US1 — GET /home, the curated Browse screen (contract v0.7.0).

Covers spec FR-002..FR-012 and SC-004/006/007/008. The caps live in ``services`` as module
constants; tests import them instead of hardcoding 10 so a future change fails loudly in one
place rather than silently skewing every assertion.
"""

import pytest
from django.utils import timezone

from apps.wallpapers.models import WallpaperStatus
from apps.wallpapers.services import HOME_MAX_ITEMS_PER_SECTION, HOME_MAX_SECTIONS
from apps.wallpapers.tests.factories import (
    CollectionFactory,
    CollectionItemFactory,
    TagFactory,
    WallpaperFactory,
)

pytestmark = pytest.mark.django_db

SECTION_KEYS = {
    "key",
    "title",
    "collection_id",
    "cover_url",
    "accent_color",
    "is_premium",
    "items",
}


def _section(slug: str, *, position: int, items: int = 1, **kwargs):
    """A home-flagged collection carrying ``items`` published wallpapers in position order."""
    collection = CollectionFactory(slug=slug, show_on_home=True, home_position=position, **kwargs)
    for index in range(items):
        CollectionItemFactory(collection=collection, position=index)
    return collection


# --------------------------------------------------------------------------------------
# Ordering (FR-002, FR-012 · SC-007)
# --------------------------------------------------------------------------------------


def test_sections_ordered_by_home_position(api):
    _section("second", position=5)
    _section("first", position=1)
    _section("third", position=9)

    body = api.get("/home").json()
    assert [s["key"] for s in body["sections"]] == ["first", "second", "third"]


def test_colliding_positions_are_stable_across_requests(api):
    # Same position on purpose: the tie must break on id, not on physical row order.
    first = _section("alpha", position=3)
    second = _section("beta", position=3)
    third = _section("gamma", position=3)

    orders = [[s["collection_id"] for s in api.get("/home").json()["sections"]] for _ in range(5)]
    assert orders == [[first.id, second.id, third.id]] * 5


def test_ordering_does_not_fall_back_to_model_default(api):
    """``Collection.Meta.ordering`` is ``-created_at`` — inheriting it would invert the stack."""
    oldest_but_first = _section("front", position=0)
    newest_but_last = _section("back", position=1)

    keys = [s["key"] for s in api.get("/home").json()["sections"]]
    assert keys == ["front", "back"]
    # Guard the premise: the newest row really would come first under the model default.
    assert newest_but_last.created_at >= oldest_but_first.created_at


# --------------------------------------------------------------------------------------
# Caps (FR-006, FR-007 · SC-006)
# --------------------------------------------------------------------------------------


def test_section_count_is_capped_in_operator_order(api):
    over = HOME_MAX_SECTIONS + 3
    for position in range(over):
        _section(f"section-{position:02d}", position=position)

    sections = api.get("/home").json()["sections"]
    assert len(sections) == HOME_MAX_SECTIONS
    assert [s["key"] for s in sections] == [f"section-{i:02d}" for i in range(HOME_MAX_SECTIONS)]


def test_items_capped_per_section_keeping_curated_order(api):
    collection = _section("big", position=0, items=0)
    wallpapers = [WallpaperFactory() for _ in range(HOME_MAX_ITEMS_PER_SECTION + 4)]
    for index, wallpaper in enumerate(wallpapers):
        CollectionItemFactory(collection=collection, wallpaper=wallpaper, position=index)

    section = api.get("/home").json()["sections"][0]
    assert [w["id"] for w in section["items"]] == [
        w.id for w in wallpapers[:HOME_MAX_ITEMS_PER_SECTION]
    ]
    # "See all" still reaches the full set through the existing collection page.
    assert section["collection_id"] == collection.id


def test_flagging_beyond_the_cap_is_never_rejected_on_write(admin_client):
    """The cap is a read-time trim, not a validation rule (FR-007)."""
    for position in range(HOME_MAX_SECTIONS):
        _section(f"taken-{position:02d}", position=position)
    overflow = CollectionFactory(slug="overflow")

    resp = admin_client.patch(
        f"/admin/collections/{overflow.id}",
        {"show_on_home": True, "home_position": HOME_MAX_SECTIONS},
        format="json",
    )
    assert resp.status_code == 200
    overflow.refresh_from_db()
    assert overflow.show_on_home is True


# --------------------------------------------------------------------------------------
# Visibility + empty-section skipping (FR-008 · SC-008)
# --------------------------------------------------------------------------------------


def test_hidden_wallpapers_are_excluded_from_sections(api):
    collection = _section("mixed", position=0, items=0)
    visible = WallpaperFactory()
    CollectionItemFactory(collection=collection, wallpaper=visible, position=0)
    for index, hidden in enumerate(
        [
            WallpaperFactory(status=WallpaperStatus.PROCESSING),
            WallpaperFactory(status=WallpaperStatus.FAILED),
            WallpaperFactory(deleted_at=timezone.now()),
        ],
        start=1,
    ):
        CollectionItemFactory(collection=collection, wallpaper=hidden, position=index)

    section = api.get("/home").json()["sections"][0]
    assert [w["id"] for w in section["items"]] == [visible.id]


@pytest.mark.parametrize("make_empty", ["no-members", "all-hidden"])
def test_empty_section_is_dropped(api, make_empty):
    empty = _section("empty", position=0, items=0)
    if make_empty == "all-hidden":
        CollectionItemFactory(
            collection=empty,
            wallpaper=WallpaperFactory(status=WallpaperStatus.PROCESSING),
            position=0,
        )
    _section("populated", position=1)

    keys = [s["key"] for s in api.get("/home").json()["sections"]]
    assert keys == ["populated"]


def test_dropped_section_does_not_consume_a_slot(api):
    """An empty section must not eat one of the available slots (FR-008)."""
    _section("empty", position=0, items=0)
    for position in range(1, HOME_MAX_SECTIONS + 1):
        _section(f"real-{position:02d}", position=position)

    sections = api.get("/home").json()["sections"]
    assert len(sections) == HOME_MAX_SECTIONS
    # The last real section still made it in — the empty one gave up its place.
    assert sections[-1]["key"] == f"real-{HOME_MAX_SECTIONS:02d}"


# --------------------------------------------------------------------------------------
# Contract shape, premium, auth, empty state (FR-004, FR-005, FR-009, FR-010, FR-011)
# --------------------------------------------------------------------------------------


def test_section_payload_shape(api):
    collection = _section("neon", position=0)

    section = api.get("/home").json()["sections"][0]
    assert set(section) == SECTION_KEYS
    assert section["key"] == collection.slug
    assert section["title"] == collection.title
    assert section["collection_id"] == collection.id
    assert section["cover_url"] == collection.cover_url
    assert section["accent_color"] == collection.accent_color
    assert section["is_premium"] is False


def test_section_items_use_the_same_wallpaper_shape_as_the_list_endpoint(api):
    wallpaper = WallpaperFactory()
    collection = _section("shape", position=0, items=0)
    CollectionItemFactory(collection=collection, wallpaper=wallpaper, position=0)

    home_item = api.get("/home").json()["sections"][0]["items"][0]
    list_item = next(w for w in api.get("/wallpapers").json()["items"] if w["id"] == wallpaper.id)
    assert home_item.keys() == list_item.keys()
    assert home_item == list_item


def test_premium_section_is_browsable_without_entitlement(api):
    _section("locked", position=0, is_premium=True)

    body = api.get("/home").json()
    section = body["sections"][0]
    assert section["is_premium"] is True
    assert section["items"], "premium sections stay fully browsable — the gate is download-url"
    assert "download_url" not in str(body)


def test_transaction_id_is_ignored(api):
    """/home is not an entitlement surface: a purchase id must change nothing (FR-009)."""
    _section("neon", position=0)

    plain = api.get("/home").json()
    with_txn = api.get("/home?transaction_id=1000000123456789").json()
    assert plain == with_txn


def test_requires_app_key(anon):
    resp = anon.get("/home")
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "INVALID_APP_KEY"


def test_admin_token_alone_is_not_accepted(admin_client):
    """Admin JWT must not open an app-tier endpoint (Constitution II)."""
    assert admin_client.get("/home").status_code == 401


def test_empty_home_is_a_success(api):
    CollectionFactory(slug="not-on-home")  # exists but never flagged

    resp = api.get("/home")
    assert resp.status_code == 200
    assert resp.json() == {"sections": []}


# --------------------------------------------------------------------------------------
# Query shape (SC-004)
# --------------------------------------------------------------------------------------


def test_query_count_does_not_grow_with_the_screen(api, django_assert_num_queries):
    """SC-004 — four queries whether the screen holds 1 wallpaper or 100.

    Distinct categories and tags per wallpaper on purpose: the nested count serializers fall
    back to a per-object ``COUNT(*)`` unless the prefetch carries the annotation, which is how
    an N+1 sneaks into the app's first screen.
    """
    solo = _section("solo", position=0, items=0)
    CollectionItemFactory(
        collection=solo, wallpaper=WallpaperFactory(tags=[TagFactory()]), position=0
    )
    with django_assert_num_queries(4):
        api.get("/home")

    for position in range(1, HOME_MAX_SECTIONS):
        collection = _section(f"more-{position:02d}", position=position, items=0)
        for index in range(HOME_MAX_ITEMS_PER_SECTION):
            CollectionItemFactory(
                collection=collection,
                wallpaper=WallpaperFactory(tags=[TagFactory(), TagFactory()]),
                position=index,
            )

    with django_assert_num_queries(4):
        body = api.get("/home").json()
    assert len(body["sections"]) == HOME_MAX_SECTIONS
    assert sum(len(s["items"]) for s in body["sections"]) == 1 + (HOME_MAX_SECTIONS - 1) * (
        HOME_MAX_ITEMS_PER_SECTION
    )

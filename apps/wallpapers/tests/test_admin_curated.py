"""US4 — admin tags & collections CRUD (spec FR-013/014; Constitution IX)."""

from unittest import mock

import pytest

from apps.uploads.models import UploadPurpose, UploadSlot
from apps.wallpapers.models import Collection, Tag
from apps.wallpapers.tests.factories import (
    CollectionFactory,
    CollectionItemFactory,
    TagFactory,
    WallpaperFactory,
)

pytestmark = pytest.mark.django_db


# --- Tags -------------------------------------------------------------------


def test_create_tag(admin_client):
    res = admin_client.post("/admin/tags", {"slug": "vapor", "name": "Vapor"}, format="json")
    assert res.status_code == 201
    assert Tag.objects.filter(slug="vapor").exists()
    assert res.json()["wallpaper_count"] == 0


def test_create_tag_reserved_all_slug_rejected(admin_client):
    res = admin_client.post("/admin/tags", {"slug": "all", "name": "All"}, format="json")
    assert res.status_code == 400
    assert res.json()["error"]["code"] == "VALIDATION_ERROR"
    assert not Tag.objects.filter(slug="all").exists()


def test_create_tag_duplicate_slug_conflicts(admin_client):
    TagFactory(slug="dup")
    res = admin_client.post("/admin/tags", {"slug": "dup", "name": "Dup"}, format="json")
    assert res.status_code == 409
    assert res.json()["error"]["code"] == "TAG_SLUG_CONFLICT"


def test_tag_list_reports_usage_counts(admin_client):
    tag = TagFactory()
    WallpaperFactory(tags=[tag])
    items = admin_client.get("/admin/tags").json()
    assert [t for t in items if t["id"] == tag.pk][0]["wallpaper_count"] == 1


def test_delete_tag_in_use_is_409(admin_client):
    tag = TagFactory()
    WallpaperFactory(tags=[tag])
    res = admin_client.delete(f"/admin/tags/{tag.pk}")
    assert res.status_code == 409
    assert res.json()["error"]["code"] == "TAG_IN_USE"
    assert Tag.objects.filter(pk=tag.pk).exists()


def test_delete_unused_tag(admin_client):
    tag = TagFactory()
    assert admin_client.delete(f"/admin/tags/{tag.pk}").status_code == 204
    assert not Tag.objects.filter(pk=tag.pk).exists()
    assert admin_client.delete(f"/admin/tags/{tag.pk}").status_code == 404


# --- Collections ------------------------------------------------------------


def _collection_body(wallpapers, **over):
    body = {
        "slug": "night-set",
        "title": "Night Set",
        "author": "curator",
        "description": "curated",
        "accent_color": "#112233",
        "is_premium": False,
        "wallpaper_ids": [w.pk for w in wallpapers],
    }
    body.update(over)
    return body


def test_create_collection_ordered(admin_client, api):
    w1, w2, w3 = WallpaperFactory(), WallpaperFactory(), WallpaperFactory()
    res = admin_client.post("/admin/collections", _collection_body([w3, w1, w2]), format="json")
    assert res.status_code == 201
    col = Collection.objects.get(slug="night-set")
    # Public detail returns curated order (Constitution IX).
    items = api.get(f"/collections/{col.pk}").json()["items"]
    assert [i["id"] for i in items] == [w3.pk, w1.pk, w2.pk]


def test_create_collection_unknown_wallpaper_is_wallpaper_not_found(admin_client):
    res = admin_client.post(
        "/admin/collections", _collection_body([], wallpaper_ids=[123456]), format="json"
    )
    assert res.status_code == 400
    assert res.json()["error"]["code"] == "WALLPAPER_NOT_FOUND"
    assert not Collection.objects.filter(slug="night-set").exists()


def test_create_collection_duplicate_slug_conflicts(admin_client):
    CollectionFactory(slug="night-set")
    res = admin_client.post("/admin/collections", _collection_body([]), format="json")
    assert res.status_code == 409
    assert res.json()["error"]["code"] == "COLLECTION_SLUG_CONFLICT"


def test_patch_reorders_atomically(admin_client, api):
    col = CollectionFactory()
    w1, w2 = WallpaperFactory(), WallpaperFactory()
    CollectionItemFactory(collection=col, wallpaper=w1, position=0)
    CollectionItemFactory(collection=col, wallpaper=w2, position=1)

    res = admin_client.patch(
        f"/admin/collections/{col.pk}", {"wallpaper_ids": [w2.pk, w1.pk]}, format="json"
    )
    assert res.status_code == 200
    items = api.get(f"/collections/{col.pk}").json()["items"]
    assert [i["id"] for i in items] == [w2.pk, w1.pk]  # replaced, not appended


def test_patch_slug_conflict_is_409(admin_client):
    CollectionFactory(slug="taken")
    col = CollectionFactory(slug="mine")
    res = admin_client.patch(f"/admin/collections/{col.pk}", {"slug": "taken"}, format="json")
    assert res.status_code == 409
    assert res.json()["error"]["code"] == "COLLECTION_SLUG_CONFLICT"


def test_delete_collection(admin_client, api):
    col = CollectionFactory()
    assert admin_client.delete(f"/admin/collections/{col.pk}").status_code == 204
    assert api.get(f"/collections/{col.pk}").status_code == 404


def test_collection_cover_via_image_slot(admin_client, admin_user, monkeypatch):
    slot = UploadSlot.objects.create(
        key="staging/coverimg.jpg",
        purpose=UploadPurpose.IMAGE,
        content_type="image/jpeg",
        created_by=admin_user,
    )
    from apps.uploads import services as upload_services

    monkeypatch.setattr(
        upload_services,
        "ingest_cover_image",
        mock.Mock(return_value="http://cdn.test/covers/abc.jpg"),
    )
    res = admin_client.post(
        "/admin/collections",
        _collection_body([], cover_upload_key=slot.key),
        format="json",
    )
    assert res.status_code == 201
    assert res.json()["cover_url"] == "http://cdn.test/covers/abc.jpg"
    slot.refresh_from_db()
    assert slot.consumed_at is not None


def test_video_slot_cannot_be_used_as_cover(admin_client, admin_user):
    slot = UploadSlot.objects.create(
        key="staging/notimage.mp4",
        purpose=UploadPurpose.VIDEO,
        content_type="video/mp4",
        created_by=admin_user,
    )
    res = admin_client.post(
        "/admin/collections", _collection_body([], cover_upload_key=slot.key), format="json"
    )
    assert res.status_code == 400
    assert res.json()["error"]["code"] == "VALIDATION_ERROR"

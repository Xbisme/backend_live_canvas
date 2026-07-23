"""US1 — admin wallpaper register/list/delete (spec FR-008/011/012; remediation A1)."""

from unittest import mock

import pytest

from apps.uploads.models import UploadPurpose, UploadSlot
from apps.wallpapers.models import Wallpaper, WallpaperStatus
from apps.wallpapers.tests.factories import CategoryFactory, TagFactory, WallpaperFactory

pytestmark = pytest.mark.django_db


@pytest.fixture
def video_slot(admin_user) -> UploadSlot:
    return UploadSlot.objects.create(
        key="staging/cafebabe.mp4",
        purpose=UploadPurpose.VIDEO,
        content_type="video/mp4",
        created_by=admin_user,
    )


@pytest.fixture
def head_ok(monkeypatch):
    """Staged object exists and is comfortably under the ceiling."""
    from apps.uploads import services

    monkeypatch.setattr(services.storage, "head_size", mock.Mock(return_value=1_000_000))


def _body(slot, category, tags, **over):
    body = {
        "title": "New Clip",
        "category_id": category.pk,
        "tag_ids": [t.pk for t in tags],
        "orientation": "portrait",
        "is_premium": False,
        "source_url": "https://example.com/source",
        "license_type": "Test License",
        "upload_key": slot.key,
    }
    body.update(over)
    return body


def test_register_creates_processing_wallpaper(admin_client, video_slot, head_ok):
    cat, tag = CategoryFactory(), TagFactory()
    res = admin_client.post("/admin/wallpapers", _body(video_slot, cat, [tag]), format="json")
    assert res.status_code == 201
    body = res.json()
    assert body["status"] == "processing"
    for field in ("thumbnail_url", "preview_video_url", "resolution", "duration_seconds"):
        assert body[field] is None
    w = Wallpaper.objects.get(pk=body["id"])
    assert w.staging_key == video_slot.key
    video_slot.refresh_from_db()
    assert video_slot.consumed_at is not None
    # Not visible on the public tier while processing.
    assert not Wallpaper.objects.published().filter(pk=w.pk).exists()


def test_register_unknown_tag_is_tag_not_found(admin_client, video_slot, head_ok):
    cat = CategoryFactory()
    res = admin_client.post(
        "/admin/wallpapers", _body(video_slot, cat, [], tag_ids=[999]), format="json"
    )
    assert res.status_code == 400
    assert res.json()["error"]["code"] == "TAG_NOT_FOUND"


def test_register_unknown_category_is_validation_error(admin_client, video_slot, head_ok):
    res = admin_client.post(
        "/admin/wallpapers",
        _body(video_slot, CategoryFactory(), [], category_id=99_999),
        format="json",
    )
    assert res.status_code == 400
    assert res.json()["error"]["code"] == "VALIDATION_ERROR"


def test_register_missing_object_is_validation_error(admin_client, video_slot, monkeypatch):
    from apps.uploads import services

    monkeypatch.setattr(services.storage, "head_size", mock.Mock(return_value=None))
    res = admin_client.post(
        "/admin/wallpapers", _body(video_slot, CategoryFactory(), []), format="json"
    )
    assert res.status_code == 400
    assert res.json()["error"]["code"] == "VALIDATION_ERROR"
    video_slot.refresh_from_db()
    assert video_slot.consumed_at is None  # gate fails BEFORE the slot is spent


def test_register_oversized_object_is_422_file_rejected(
    admin_client, video_slot, monkeypatch, settings
):
    from apps.uploads import services

    monkeypatch.setattr(
        services.storage, "head_size", mock.Mock(return_value=settings.UPLOAD_MAX_BYTES + 1)
    )
    res = admin_client.post(
        "/admin/wallpapers", _body(video_slot, CategoryFactory(), []), format="json"
    )
    assert res.status_code == 422
    assert res.json()["error"]["code"] == "FILE_REJECTED"


def test_double_register_same_upload_key_fails(admin_client, video_slot, head_ok):
    cat = CategoryFactory()
    first = admin_client.post("/admin/wallpapers", _body(video_slot, cat, []), format="json")
    assert first.status_code == 201
    second = admin_client.post("/admin/wallpapers", _body(video_slot, cat, []), format="json")
    assert second.status_code == 400
    assert second.json()["error"]["code"] == "VALIDATION_ERROR"
    assert Wallpaper.objects.count() == 1


def test_admin_list_shows_all_states_with_filter_and_reason(admin_client):
    WallpaperFactory(status=WallpaperStatus.PUBLISHED)
    WallpaperFactory(status=WallpaperStatus.PROCESSING)
    failed = WallpaperFactory(status=WallpaperStatus.FAILED, failure_reason="sniff: text/plain")

    everything = admin_client.get("/admin/wallpapers").json()
    assert set(everything) == {"items", "next_cursor", "has_more"}  # cursor envelope
    assert len(everything["items"]) == 3

    only_failed = admin_client.get("/admin/wallpapers?status=failed").json()["items"]
    assert [i["id"] for i in only_failed] == [failed.pk]
    assert only_failed[0]["failure_reason"] == "sniff: text/plain"

    bad = admin_client.get("/admin/wallpapers?status=nope")
    assert bad.status_code == 400
    assert bad.json()["error"]["code"] == "VALIDATION_ERROR"


def test_failure_reason_never_reaches_public_tier(api):
    WallpaperFactory(status=WallpaperStatus.PUBLISHED, failure_reason="internal detail")
    item = api.get("/wallpapers").json()["items"][0]
    assert "failure_reason" not in item and "status" not in item


def test_soft_delete_hides_from_public(admin_client, api):
    w = WallpaperFactory(status=WallpaperStatus.PUBLISHED)
    res = admin_client.delete(f"/admin/wallpapers/{w.pk}")
    assert res.status_code == 204
    w.refresh_from_db()
    assert w.deleted_at is not None  # soft, not gone
    assert api.get(f"/wallpapers/{w.pk}").status_code == 404
    # Deleting again → 404 (already deleted).
    assert admin_client.delete(f"/admin/wallpapers/{w.pk}").status_code == 404


def test_register_responds_fast_without_touching_bytes(admin_client, video_slot, head_ok):
    """SC-001 proxy: registration does no media work — only a HEAD-check plus DB writes."""
    import time

    cat = CategoryFactory()
    start = time.monotonic()
    res = admin_client.post("/admin/wallpapers", _body(video_slot, cat, []), format="json")
    elapsed = time.monotonic() - start
    assert res.status_code == 201
    assert elapsed < 2.0

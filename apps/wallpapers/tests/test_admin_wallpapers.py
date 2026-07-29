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


# --- Description (US3, contract v0.7.0) --------------------------------------


def test_register_with_description(admin_client, video_slot, head_ok):
    cat, tag = CategoryFactory(), TagFactory()
    body = _body(video_slot, cat, [tag], description="Neon phản chiếu sau mưa.")
    res = admin_client.post("/admin/wallpapers", body, format="json")

    assert res.status_code == 201
    assert res.json()["description"] == "Neon phản chiếu sau mưa."
    assert Wallpaper.objects.get(pk=res.json()["id"]).description == "Neon phản chiếu sau mưa."


def test_register_without_description_stores_null(admin_client, video_slot, head_ok):
    cat, tag = CategoryFactory(), TagFactory()
    res = admin_client.post("/admin/wallpapers", _body(video_slot, cat, [tag]), format="json")

    assert res.status_code == 201
    assert res.json()["description"] is None
    assert Wallpaper.objects.get(pk=res.json()["id"]).description is None


def test_register_blank_description_normalized_to_null(admin_client, video_slot, head_ok):
    cat, tag = CategoryFactory(), TagFactory()
    body = _body(video_slot, cat, [tag], description="   \n  ")
    res = admin_client.post("/admin/wallpapers", body, format="json")

    assert res.status_code == 201
    assert Wallpaper.objects.get(pk=res.json()["id"]).description is None


def test_patch_sets_description_on_a_pre_existing_wallpaper(admin_client, api):
    """The catalogue predates the field — this path is the only way it ever gets one (SC-010)."""
    wallpaper = WallpaperFactory()  # created without ever passing through the register path
    assert wallpaper.description is None

    res = admin_client.patch(
        f"/admin/wallpapers/{wallpaper.pk}", {"description": "Mô tả bổ sung sau."}, format="json"
    )
    assert res.status_code == 200
    assert res.json()["description"] == "Mô tả bổ sung sau."
    assert api.get(f"/wallpapers/{wallpaper.pk}").json()["description"] == "Mô tả bổ sung sau."


def test_patch_changes_and_clears_description(admin_client):
    wallpaper = WallpaperFactory(description="cũ")

    admin_client.patch(f"/admin/wallpapers/{wallpaper.pk}", {"description": "mới"}, format="json")
    wallpaper.refresh_from_db()
    assert wallpaper.description == "mới"

    res = admin_client.patch(
        f"/admin/wallpapers/{wallpaper.pk}", {"description": None}, format="json"
    )
    assert res.status_code == 200
    wallpaper.refresh_from_db()
    assert wallpaper.description is None


@pytest.mark.parametrize("blank", ["", "   ", "\n\t "])
def test_patch_whitespace_description_becomes_null(admin_client, blank):
    wallpaper = WallpaperFactory(description="cũ")

    res = admin_client.patch(
        f"/admin/wallpapers/{wallpaper.pk}", {"description": blank}, format="json"
    )
    assert res.status_code == 200
    wallpaper.refresh_from_db()
    assert wallpaper.description is None


def test_patch_cannot_touch_any_other_field(admin_client):
    """A one-field serializer makes this structural, not a review promise (spec FR-015)."""
    category = CategoryFactory()
    wallpaper = WallpaperFactory(title="Original", is_premium=False, category=category)
    other = CategoryFactory()

    res = admin_client.patch(
        f"/admin/wallpapers/{wallpaper.pk}",
        {
            "description": "chỉ mô tả đổi",
            "title": "Hijacked",
            "is_premium": True,
            "category_id": other.pk,
            "status": WallpaperStatus.FAILED,
        },
        format="json",
    )
    assert res.status_code == 200
    wallpaper.refresh_from_db()
    assert wallpaper.description == "chỉ mô tả đổi"
    assert wallpaper.title == "Original"
    assert wallpaper.is_premium is False
    assert wallpaper.category_id == category.pk
    assert wallpaper.status == WallpaperStatus.PUBLISHED


def test_patch_description_is_audited_without_the_text(admin_client, admin_user):
    from apps.audit.models import AuditLogEntry

    wallpaper = WallpaperFactory()
    secret_ish = "nội dung mô tả không nên nằm trong audit"
    admin_client.patch(
        f"/admin/wallpapers/{wallpaper.pk}", {"description": secret_ish}, format="json"
    )

    entry = AuditLogEntry.objects.filter(action="wallpaper.update").latest("id")
    assert entry.actor == admin_user
    assert entry.object_id == str(wallpaper.pk)
    assert entry.metadata == {"field": "description"}
    assert secret_ish not in str(entry.metadata)


def test_patch_missing_wallpaper_is_404(admin_client):
    assert (
        admin_client.patch(
            "/admin/wallpapers/999999", {"description": "x"}, format="json"
        ).status_code
        == 404
    )


def test_patch_soft_deleted_wallpaper_is_404(admin_client):
    from django.utils import timezone

    wallpaper = WallpaperFactory(deleted_at=timezone.now())
    res = admin_client.patch(
        f"/admin/wallpapers/{wallpaper.pk}", {"description": "x"}, format="json"
    )
    assert res.status_code == 404


def test_patch_requires_admin_tier(api):
    """App key must not reach an admin endpoint (Constitution II)."""
    wallpaper = WallpaperFactory()
    res = api.patch(f"/admin/wallpapers/{wallpaper.pk}", {"description": "x"}, format="json")
    assert res.status_code == 401
    assert res.json()["error"]["code"] == "UNAUTHORIZED_ADMIN"


# --- Contract shape: admin vs public tier (v0.7.1) ----------------------------

# Đúng shape mà `AdminWallpaper` khai trong contract = Wallpaper (18) + 2 field vòng đời.
_ADMIN_ONLY_FIELDS = {"status", "failure_reason"}


def test_admin_payload_is_public_shape_plus_lifecycle_fields(admin_client, api):
    """Contract khai `AdminWallpaper` = `Wallpaper` + status + failure_reason — khoá lại.

    Lệch này từng tồn tại âm thầm từ BE-004 tới v0.7.0: contract khai `Wallpaper` còn
    server trả thêm 2 field. Test so trực tiếp payload 2 tier nên lần sau ai thêm field
    vào serializer admin mà quên cập nhật contract sẽ đỏ ngay.
    """
    wallpaper = WallpaperFactory()

    admin_row = next(
        row
        for row in admin_client.get("/admin/wallpapers").json()["items"]
        if row["id"] == wallpaper.pk
    )
    public_row = api.get(f"/wallpapers/{wallpaper.pk}").json()

    assert set(admin_row) - set(public_row) == _ADMIN_ONLY_FIELDS
    assert set(public_row) - set(admin_row) == set()


def test_patch_response_uses_the_admin_shape(admin_client):
    wallpaper = WallpaperFactory()
    body = admin_client.patch(
        f"/admin/wallpapers/{wallpaper.pk}", {"description": "x"}, format="json"
    ).json()
    assert set(body) >= _ADMIN_ONLY_FIELDS


def test_lifecycle_fields_never_leak_to_the_app_tier(api):
    """Public tier phải sạch: `failure_reason` có thể lộ chi tiết pipeline nội bộ."""
    wallpaper = WallpaperFactory()
    for payload in (
        api.get(f"/wallpapers/{wallpaper.pk}").json(),
        api.get("/wallpapers").json()["items"][0],
        api.post("/wallpapers/batch", {"ids": [wallpaper.pk]}, format="json").json()[0],
    ):
        assert not (_ADMIN_ONLY_FIELDS & set(payload))

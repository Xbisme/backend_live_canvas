"""US5 — audit coverage & hygiene (spec FR-019, SC-007).

Every admin mutation leaves exactly one traceable record; no record ever contains a
secret, token, or signed URL — enforced by the sanitize guard, which is the single
write path into the trail.
"""

from datetime import UTC, datetime
from unittest import mock

import pytest

from apps.audit import services as audit
from apps.audit.models import AuditLogEntry
from apps.audit.services import AuditSanitizationError
from apps.wallpapers.tests.factories import CategoryFactory, WallpaperFactory

pytestmark = pytest.mark.django_db


# --- Sanitize guard (unit) ---------------------------------------------------


def test_guard_rejects_forbidden_keys(admin_user):
    for key in ("password", "token", "access", "refresh", "secret", "receipt"):
        with pytest.raises(AuditSanitizationError):
            audit.record(admin_user, "x.y", **{key: "anything"})
    assert AuditLogEntry.objects.count() == 0


def test_guard_rejects_signed_url_values(admin_user):
    with pytest.raises(AuditSanitizationError):
        audit.record(admin_user, "x.y", url="https://s3/x?X-Amz-Signature=abc")
    with pytest.raises(AuditSanitizationError):
        audit.record(admin_user, "x.y", note={"nested": ["Bearer eyJhbGciOi..."]})


def test_guard_allows_clean_metadata(admin_user):
    entry = audit.record(admin_user, "tag.create", slug="calm", count=3)
    assert entry.metadata == {"slug": "calm", "count": 3}
    assert entry.actor_label == "admin"


def test_actor_survives_user_deletion(admin_user):
    entry = audit.record(admin_user, "tag.create", slug="x")
    admin_user.delete()
    entry.refresh_from_db()
    assert entry.actor is None
    assert entry.actor_label == "admin"  # history stays attributable


# --- End-to-end coverage: every mutation writes a record --------------------


def _actions() -> list[str]:
    return list(AuditLogEntry.objects.values_list("action", flat=True))


def test_presign_and_register_are_audited(admin_client, admin_user, monkeypatch):
    from apps.uploads import services as upload_services
    from apps.uploads import views as upload_views

    monkeypatch.setattr(
        upload_views.storage,
        "presign_upload",
        mock.Mock(return_value=("https://signed", datetime.now(UTC))),
    )
    res = admin_client.post(
        "/admin/uploads/presign",
        {"filename": "clip.mp4", "content_type": "video/mp4"},
        format="json",
    )
    assert res.status_code == 200
    key = res.json()["upload_key"]

    monkeypatch.setattr(upload_services.storage, "head_size", mock.Mock(return_value=1000))
    cat = CategoryFactory()
    res = admin_client.post(
        "/admin/wallpapers",
        {
            "title": "T",
            "category_id": cat.pk,
            "tag_ids": [],
            "orientation": "portrait",
            "is_premium": False,
            "source_url": "https://example.com/s",
            "license_type": "L",
            "upload_key": key,
        },
        format="json",
    )
    assert res.status_code == 201

    actions = _actions()
    for expected in ("upload.presign", "upload.register", "wallpaper.create"):
        assert actions.count(expected) == 1, expected


def test_curated_mutations_are_audited(admin_client):
    tag_res = admin_client.post("/admin/tags", {"slug": "aud", "name": "Aud"}, format="json")
    admin_client.delete(f"/admin/tags/{tag_res.json()['id']}")
    col_res = admin_client.post(
        "/admin/collections",
        {"slug": "aud-col", "title": "C", "wallpaper_ids": [], "is_premium": False},
        format="json",
    )
    col_id = col_res.json()["id"]
    admin_client.patch(f"/admin/collections/{col_id}", {"title": "C2"}, format="json")
    admin_client.delete(f"/admin/collections/{col_id}")

    actions = _actions()
    for expected in (
        "tag.create",
        "tag.delete",
        "collection.create",
        "collection.update",
        "collection.delete",
    ):
        assert actions.count(expected) == 1, expected


def test_wallpaper_delete_is_audited(admin_client):
    w = WallpaperFactory()
    admin_client.delete(f"/admin/wallpapers/{w.pk}")
    assert "wallpaper.delete" in _actions()


def test_no_record_contains_secretlike_content(admin_client, admin_user, monkeypatch):
    """SC-007 sweep after a burst of real mutations."""
    from apps.uploads import views as upload_views

    monkeypatch.setattr(
        upload_views.storage,
        "presign_upload",
        mock.Mock(return_value=("https://signed?X-Amz-Signature=zzz", datetime.now(UTC))),
    )
    admin_client.post(
        "/admin/uploads/presign",
        {"filename": "a.mp4", "content_type": "video/mp4"},
        format="json",
    )
    admin_client.post("/admin/tags", {"slug": "sweep", "name": "S"}, format="json")

    for entry in AuditLogEntry.objects.all():
        blob = str(entry.metadata).lower()
        assert "x-amz-signature" not in blob
        assert "bearer ey" not in blob
        assert not {k.lower() for k in entry.metadata} & {"password", "token", "access", "refresh"}


def test_audit_trail_is_append_only_no_public_write_api():
    """No API route exposes audit mutation; the model is written via record() only."""
    from django.urls import get_resolver

    resolver = get_resolver()
    all_routes = str(resolver.url_patterns)
    assert "audit" not in all_routes.lower()

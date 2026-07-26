"""US3 — GET /wallpapers/{id}/download-url: real presigned edge (spec FR-018, SC-005).

Storage is mocked at the boundary (Constitution X) — no bucket is touched; what is
asserted is the contract shape, the entitlement gate, and the 404 surface.
"""

from datetime import UTC, datetime, timedelta
from unittest import mock

import pytest
from django.utils import timezone

from apps.wallpapers.models import WallpaperStatus
from apps.wallpapers.tests.factories import WallpaperFactory

pytestmark = pytest.mark.django_db

SIGNED_URL = "https://minio.test/livecanvas-private/masters/abc.mp4?X-Amz-Signature=sig"


@pytest.fixture
def presign(monkeypatch):
    from apps.uploads import storage

    fake = mock.Mock(return_value=(SIGNED_URL, datetime.now(UTC) + timedelta(minutes=5)))
    monkeypatch.setattr(storage, "presign_download", fake)
    return fake


def test_free_wallpaper_gets_presigned_url(api, presign):
    wp = WallpaperFactory(is_premium=False, master_key="masters/abc.mp4")
    resp = api.get(f"/wallpapers/{wp.id}/download-url")
    assert resp.status_code == 200
    body = resp.json()
    assert body["download_url"] == SIGNED_URL
    presign.assert_called_once_with("masters/abc.mp4")
    expires = datetime.fromisoformat(body["expires_at"].replace("Z", "+00:00"))
    # Presigned URLs must be short-lived (≤ 5 minutes, Constitution III).
    assert expires <= timezone.now() + timedelta(minutes=5, seconds=5)


def _entitle(transaction_id, *, status=None, auto_renew=True, expires_delta_days=30):
    """Create an entitlement resolvable by ``transaction_id`` (BE-005 gate)."""
    from datetime import UTC, datetime, timedelta

    from apps.iap.models import (
        EntitlementStatus,
        EntitlementTransaction,
        IapPlatform,
        SubscriptionEntitlement,
    )

    ent = SubscriptionEntitlement.objects.create(
        platform=IapPlatform.IOS,
        original_transaction_id=transaction_id,
        latest_transaction_id=transaction_id,
        product_id="premium_monthly",
        status=status or EntitlementStatus.ACTIVE,
        expires_at=datetime.now(UTC) + timedelta(days=expires_delta_days),
        auto_renew=auto_renew,
    )
    EntitlementTransaction.objects.create(
        entitlement=ent, platform=IapPlatform.IOS, transaction_id=transaction_id
    )
    return ent


def test_premium_without_transaction_id_returns_402(api, presign):
    wp = WallpaperFactory(is_premium=True, master_key="masters/abc.mp4")
    resp = api.get(f"/wallpapers/{wp.id}/download-url")
    assert resp.status_code == 402
    assert resp.json()["error"]["code"] == "ENTITLEMENT_REQUIRED"
    presign.assert_not_called()


def test_premium_with_unknown_or_expired_transaction_returns_402(api, presign):
    from apps.iap.models import EntitlementStatus

    wp = WallpaperFactory(is_premium=True, master_key="masters/abc.mp4")
    _entitle("expired-txn", status=EntitlementStatus.EXPIRED)
    assert api.get(f"/wallpapers/{wp.id}/download-url?transaction_id=nope").status_code == 402
    assert (
        api.get(f"/wallpapers/{wp.id}/download-url?transaction_id=expired-txn").status_code == 402
    )
    presign.assert_not_called()


def test_premium_with_active_entitlement_unlocks(api, presign):
    wp = WallpaperFactory(is_premium=True, master_key="masters/abc.mp4")
    _entitle("txn-active")
    resp = api.get(f"/wallpapers/{wp.id}/download-url?transaction_id=txn-active")
    assert resp.status_code == 200
    body = resp.json()
    assert body["download_url"] == SIGNED_URL
    expires = datetime.fromisoformat(body["expires_at"].replace("Z", "+00:00"))
    assert expires <= timezone.now() + timedelta(minutes=5, seconds=5)


def test_premium_grace_and_autorenew_off_still_unlock(api, presign):
    from apps.iap.models import EntitlementStatus

    grace = WallpaperFactory(is_premium=True, master_key="masters/g.mp4")
    _entitle("txn-grace", status=EntitlementStatus.IN_GRACE_PERIOD)
    assert (
        api.get(f"/wallpapers/{grace.id}/download-url?transaction_id=txn-grace").status_code == 200
    )

    cancelled = WallpaperFactory(is_premium=True, master_key="masters/c.mp4")
    _entitle("txn-cancel", auto_renew=False)  # active, auto_renew off, still in period (F1)
    assert (
        api.get(f"/wallpapers/{cancelled.id}/download-url?transaction_id=txn-cancel").status_code
        == 200
    )


def test_premium_processing_returns_404_before_gate(api, presign):
    """A premium wallpaper not yet published is 404 (evaluated before entitlement) — FR-022."""
    wp = WallpaperFactory(
        is_premium=True, master_key="masters/abc.mp4", status=WallpaperStatus.PROCESSING
    )
    resp = api.get(f"/wallpapers/{wp.id}/download-url?transaction_id=whatever")
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "NOT_FOUND"
    presign.assert_not_called()


def test_not_yet_selfhosted_returns_404(api, presign):
    """Seeded wallpaper before backfill: published but master_key is NULL → no bytes."""
    wp = WallpaperFactory(is_premium=False, master_key=None)
    resp = api.get(f"/wallpapers/{wp.id}/download-url")
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "NOT_FOUND"


@pytest.mark.parametrize(
    "state",
    [
        {"status": WallpaperStatus.PROCESSING},
        {"status": WallpaperStatus.FAILED},
        {"status": WallpaperStatus.PUBLISHED, "deleted_at_now": True},
    ],
)
def test_hidden_states_return_404(api, presign, state):
    kwargs = {"master_key": "masters/abc.mp4", "is_premium": False}
    deleted = state.pop("deleted_at_now", False)
    kwargs.update(state)
    wp = WallpaperFactory(**kwargs)
    if deleted:
        wp.deleted_at = timezone.now()
        wp.save(update_fields=["deleted_at"])
    resp = api.get(f"/wallpapers/{wp.id}/download-url")
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "NOT_FOUND"


def test_missing_returns_404(api):
    resp = api.get("/wallpapers/999999/download-url")
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "NOT_FOUND"


def test_requires_app_key(anon):
    wp = WallpaperFactory(master_key="masters/abc.mp4")
    assert anon.get(f"/wallpapers/{wp.id}/download-url").status_code == 401

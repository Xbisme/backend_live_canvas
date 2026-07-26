"""US2 — POST /iap/webhook/apple (spec FR-009..014). Verifier mocked at the seam."""

from datetime import UTC, datetime, timedelta

import pytest

from apps.iap.models import (
    EntitlementStatus,
    NotificationOutcome,
    StoreNotificationEvent,
    SubscriptionEntitlement,
)
from apps.iap.tests.conftest import make_event, make_sub
from core.errors import WebhookSignatureInvalid

pytestmark = pytest.mark.django_db

URL = "/iap/webhook/apple"
BODY = {"signedPayload": "signed-jws"}


def _seed_entitlement(status=EntitlementStatus.ACTIVE, expires_days=30, last_event=None):
    from apps.iap.models import EntitlementTransaction, IapPlatform

    ent = SubscriptionEntitlement.objects.create(
        platform=IapPlatform.IOS,
        original_transaction_id="orig-1",
        latest_transaction_id="orig-1",
        product_id="premium_monthly",
        status=status,
        expires_at=datetime.now(UTC) + timedelta(days=expires_days),
        auto_renew=True,
        last_store_event_at=last_event,
    )
    EntitlementTransaction.objects.create(
        entitlement=ent, platform=IapPlatform.IOS, transaction_id="orig-1"
    )
    return ent


def _mock_decode(monkeypatch, event):
    monkeypatch.setattr("apps.iap.stores.apple.decode_notification", lambda _p: event)


def test_invalid_signature_returns_400_no_state_change(api, monkeypatch):
    _seed_entitlement()
    monkeypatch.setattr(
        "apps.iap.stores.apple.decode_notification",
        lambda _p: (_ for _ in ()).throw(WebhookSignatureInvalid()),
    )
    resp = api.post(URL, BODY, format="json")
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "WEBHOOK_SIGNATURE_INVALID"
    assert StoreNotificationEvent.objects.count() == 0


def test_renewal_extends_expiry(api, monkeypatch):
    _seed_entitlement(expires_days=1)
    new_expiry = datetime.now(UTC) + timedelta(days=31)
    _mock_decode(
        monkeypatch,
        make_event(sub_overrides={"expires_at": new_expiry}, notification_type="DID_RENEW"),
    )
    resp = api.post(URL, BODY, format="json")
    assert resp.status_code == 200
    assert resp.json() == {}
    ent = SubscriptionEntitlement.objects.get()
    assert ent.expires_at.date() == new_expiry.date()
    assert StoreNotificationEvent.objects.get().outcome == NotificationOutcome.APPLIED


def test_refund_revokes_access(api, monkeypatch):
    _seed_entitlement()
    _mock_decode(
        monkeypatch,
        make_event(
            sub_overrides={"status": EntitlementStatus.REFUNDED}, notification_type="REFUND"
        ),
    )
    assert api.post(URL, BODY, format="json").status_code == 200
    ent = SubscriptionEntitlement.objects.get()
    assert ent.status == EntitlementStatus.REFUNDED
    assert ent.is_entitled is False


def test_duplicate_event_is_ignored(api, monkeypatch):
    _seed_entitlement()
    _mock_decode(monkeypatch, make_event(store_event_id="dup-1"))
    api.post(URL, BODY, format="json")
    api.post(URL, BODY, format="json")
    assert StoreNotificationEvent.objects.filter(store_event_id="dup-1").count() == 1


def test_out_of_order_event_does_not_regress(api, monkeypatch):
    _seed_entitlement()
    newer = datetime.now(UTC)
    older = newer - timedelta(hours=1)
    # Apply the newer renewal first.
    _mock_decode(
        monkeypatch,
        make_event(store_event_id="new", store_event_at=newer, notification_type="DID_RENEW"),
    )
    api.post(URL, BODY, format="json")
    # Now a stale EXPIRED event arrives late — must NOT revoke.
    _mock_decode(
        monkeypatch,
        make_event(
            store_event_id="old",
            store_event_at=older,
            notification_type="EXPIRED",
            sub_overrides={"status": EntitlementStatus.EXPIRED},
        ),
    )
    api.post(URL, BODY, format="json")
    ent = SubscriptionEntitlement.objects.get()
    assert ent.status == EntitlementStatus.ACTIVE  # no regression (SC-007)
    assert StoreNotificationEvent.objects.get(store_event_id="old").outcome == (
        NotificationOutcome.STALE_IGNORED
    )


def test_notification_for_unverified_subscription_is_recorded(api, monkeypatch):
    # No prior entitlement; webhook still records store-authoritative state.
    _mock_decode(
        monkeypatch, make_event(subscription=make_sub(original_transaction_id="brand-new"))
    )
    assert api.post(URL, BODY, format="json").status_code == 200
    assert SubscriptionEntitlement.objects.filter(original_transaction_id="brand-new").exists()


def test_webhook_ignores_app_key_header(api, monkeypatch):
    # A signature-only endpoint: presence of X-App-Key is irrelevant; the signature decides.
    _seed_entitlement()
    _mock_decode(monkeypatch, make_event())
    assert api.post(URL, BODY, format="json").status_code == 200

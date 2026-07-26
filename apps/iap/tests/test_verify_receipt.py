"""US1 — POST /iap/verify-receipt (spec FR-001..008). Store boundary mocked (Constitution X)."""

from datetime import UTC, datetime, timedelta

import pytest

from apps.iap.models import (
    EntitlementStatus,
    IapPlatform,
    SubscriptionEntitlement,
)
from apps.iap.tests.conftest import make_sub
from core.errors import ReceiptInvalid, StoreApiUnavailable

pytestmark = pytest.mark.django_db

URL = "/iap/verify-receipt"

BODY = {
    "platform": "ios",
    "receipt_data": "base64-receipt",
    "transaction_id": "orig-1",
    "product_id": "premium_monthly",
    "device_id": "device-abc",
}


def test_verify_ios_happy_returns_subscription_status(api, mock_apple):
    resp = api.post(URL, BODY, format="json")
    assert resp.status_code == 200
    body = resp.json()
    # Contract SubscriptionStatus shape (Constitution X — assert response shape).
    assert set(body) == {"transaction_id", "product_id", "status", "expires_at", "auto_renew"}
    assert body["transaction_id"] == "orig-1"
    assert body["product_id"] == "premium_monthly"
    assert body["status"] == "active"
    assert body["auto_renew"] is True
    assert SubscriptionEntitlement.objects.count() == 1


def test_verify_android_happy(api, mock_google):
    resp = api.post(URL, {**BODY, "platform": "android"}, format="json")
    assert resp.status_code == 200
    assert resp.json()["status"] == "active"
    ent = SubscriptionEntitlement.objects.get()
    assert ent.platform == IapPlatform.ANDROID


def test_verify_receipt_invalid_returns_400(api, monkeypatch):
    monkeypatch.setattr(
        "apps.iap.stores.apple.verify", lambda **_: (_ for _ in ()).throw(ReceiptInvalid())
    )
    resp = api.post(URL, BODY, format="json")
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "RECEIPT_INVALID"
    assert SubscriptionEntitlement.objects.count() == 0


def test_verify_store_unavailable_returns_503(api, monkeypatch):
    monkeypatch.setattr(
        "apps.iap.stores.apple.verify", lambda **_: (_ for _ in ()).throw(StoreApiUnavailable())
    )
    resp = api.post(URL, BODY, format="json")
    assert resp.status_code == 503
    assert resp.json()["error"]["code"] == "STORE_API_UNAVAILABLE"
    assert SubscriptionEntitlement.objects.count() == 0


def test_verify_is_idempotent(api, mock_apple):
    api.post(URL, BODY, format="json")
    api.post(URL, BODY, format="json")
    assert SubscriptionEntitlement.objects.count() == 1


def test_verify_conflict_when_txn_maps_to_other_subscription(api, monkeypatch):
    # First purchase binds transaction id "shared" to subscription orig-1.
    monkeypatch.setattr(
        "apps.iap.stores.apple.verify",
        lambda **_: make_sub(original_transaction_id="orig-1", transaction_ids=["shared"]),
    )
    assert api.post(URL, {**BODY, "transaction_id": "shared"}, format="json").status_code == 200

    # Same client id now resolves to a DIFFERENT subscription → conflict (FR-007).
    monkeypatch.setattr(
        "apps.iap.stores.apple.verify",
        lambda **_: make_sub(original_transaction_id="orig-2", transaction_ids=["shared"]),
    )
    resp = api.post(URL, {**BODY, "transaction_id": "shared"}, format="json")
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "RECEIPT_CONFLICT"


def test_verify_requires_app_key(anon, mock_apple):
    assert anon.post(URL, BODY, format="json").status_code == 401


def test_verify_admin_jwt_does_not_satisfy_app_tier(admin_client, mock_apple):
    # Admin Bearer JWT must NOT authenticate the app tier (Constitution II — no fallback).
    assert admin_client.post(URL, BODY, format="json").status_code == 401


def test_verify_persists_expiry_and_grace(api, monkeypatch):
    expires = datetime.now(UTC) + timedelta(days=5)
    monkeypatch.setattr(
        "apps.iap.stores.apple.verify",
        lambda **_: make_sub(status=EntitlementStatus.IN_GRACE_PERIOD, expires_at=expires),
    )
    resp = api.post(URL, BODY, format="json")
    assert resp.status_code == 200
    assert resp.json()["status"] == "in_grace_period"

"""US3 — GET /iap/subscription-status (spec FR-015..017). Read-only entitlement lookup."""

from datetime import UTC, datetime, timedelta

import pytest

from apps.iap.models import (
    EntitlementStatus,
    EntitlementTransaction,
    IapPlatform,
    SubscriptionEntitlement,
)

pytestmark = pytest.mark.django_db

URL = "/iap/subscription-status"


def _entitlement(txn_ids=("orig-1",)):
    ent = SubscriptionEntitlement.objects.create(
        platform=IapPlatform.IOS,
        original_transaction_id="orig-1",
        latest_transaction_id=txn_ids[-1],
        product_id="premium_monthly",
        status=EntitlementStatus.ACTIVE,
        expires_at=datetime.now(UTC) + timedelta(days=30),
        auto_renew=True,
    )
    for txn in txn_ids:
        EntitlementTransaction.objects.create(
            entitlement=ent, platform=IapPlatform.IOS, transaction_id=txn
        )
    return ent


def test_status_known_transaction_returns_shape(api):
    _entitlement()
    resp = api.get(f"{URL}?transaction_id=orig-1")
    assert resp.status_code == 200
    body = resp.json()
    assert set(body) == {"transaction_id", "product_id", "status", "expires_at", "auto_renew"}
    assert body["transaction_id"] == "orig-1"
    assert body["status"] == "active"


def test_status_resolves_by_renewal_chain_id(api):
    _entitlement(txn_ids=("orig-1", "renew-2"))
    resp = api.get(f"{URL}?transaction_id=renew-2")
    assert resp.status_code == 200
    assert resp.json()["transaction_id"] == "orig-1"  # resolves to the stable id


def test_status_unknown_returns_404(api):
    resp = api.get(f"{URL}?transaction_id=nope")
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "NOT_FOUND"


def test_status_missing_param_returns_400(api):
    resp = api.get(URL)
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "VALIDATION_ERROR"


def test_status_is_read_only(api):
    _entitlement()
    before = SubscriptionEntitlement.objects.get().last_verified_at
    api.get(f"{URL}?transaction_id=orig-1")
    assert SubscriptionEntitlement.objects.get().last_verified_at == before


def test_status_requires_app_key(anon):
    assert anon.get(f"{URL}?transaction_id=orig-1").status_code == 401

"""US1 — services.is_entitled + resolve_status (spec FR-017/018/021, F1)."""

from datetime import UTC, datetime, timedelta

import pytest
from django.http import Http404

from apps.iap import services
from apps.iap.models import (
    EntitlementStatus,
    EntitlementTransaction,
    IapPlatform,
    SubscriptionEntitlement,
)

pytestmark = pytest.mark.django_db


def _entitlement(*, status, expires_delta_days=30, auto_renew=True, txn_ids=("orig-1",)):
    ent = SubscriptionEntitlement.objects.create(
        platform=IapPlatform.IOS,
        original_transaction_id="orig-1",
        latest_transaction_id=txn_ids[-1],
        product_id="premium_monthly",
        status=status,
        expires_at=datetime.now(UTC) + timedelta(days=expires_delta_days),
        auto_renew=auto_renew,
    )
    for txn in txn_ids:
        EntitlementTransaction.objects.create(
            entitlement=ent, platform=IapPlatform.IOS, transaction_id=txn
        )
    return ent


def test_active_is_entitled():
    _entitlement(status=EntitlementStatus.ACTIVE)
    assert services.is_entitled("orig-1") is True


def test_grace_period_is_entitled():
    _entitlement(status=EntitlementStatus.IN_GRACE_PERIOD)
    assert services.is_entitled("orig-1") is True


def test_auto_renew_off_but_in_period_is_entitled():
    # F1: auto-renew off within the paid period is recorded as active(auto_renew=False).
    _entitlement(status=EntitlementStatus.ACTIVE, auto_renew=False)
    assert services.is_entitled("orig-1") is True


def test_expired_is_not_entitled():
    _entitlement(status=EntitlementStatus.EXPIRED)
    assert services.is_entitled("orig-1") is False


def test_active_but_past_expiry_is_not_entitled():
    _entitlement(status=EntitlementStatus.ACTIVE, expires_delta_days=-1)
    assert services.is_entitled("orig-1") is False


def test_refunded_is_not_entitled():
    _entitlement(status=EntitlementStatus.REFUNDED)
    assert services.is_entitled("orig-1") is False


def test_resolves_by_any_renewal_chain_id():
    _entitlement(status=EntitlementStatus.ACTIVE, txn_ids=("orig-1", "renew-2", "renew-3"))
    assert services.is_entitled("renew-3") is True
    assert services.is_entitled("renew-2") is True
    assert services.is_entitled("orig-1") is True


def test_unknown_or_missing_id_not_entitled():
    assert services.is_entitled("nope") is False
    assert services.is_entitled("") is False
    assert services.is_entitled(None) is False


def test_resolve_status_returns_entitlement():
    _entitlement(status=EntitlementStatus.ACTIVE)
    assert services.resolve_status("orig-1").original_transaction_id == "orig-1"


def test_resolve_status_unknown_raises_404():
    with pytest.raises(Http404):
        services.resolve_status("nope")

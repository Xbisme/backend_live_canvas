"""IAP test fixtures: store-boundary mocks + an app-tier anon client.

The store adapters are mocked at their single seam (``stores.apple.verify`` /
``stores.google.verify``) so no test touches Apple/Google (Constitution X).
"""

from datetime import UTC, datetime, timedelta
from unittest import mock

import pytest
from rest_framework.test import APIClient

from apps.iap.models import EntitlementStatus, IapPlatform
from apps.iap.stores.base import NotificationEvent, StoreSubscription


@pytest.fixture
def anon() -> APIClient:
    """App-tier client with NO ``X-App-Key`` — for 401 isolation checks."""
    return APIClient()


def make_sub(**overrides) -> StoreSubscription:
    """A normalized active-subscription result; override any field per test."""
    data = {
        "platform": IapPlatform.IOS,
        "original_transaction_id": "orig-1",
        "latest_transaction_id": "orig-1",
        "product_id": "premium_monthly",
        "status": EntitlementStatus.ACTIVE,
        "expires_at": datetime.now(UTC) + timedelta(days=30),
        "auto_renew": True,
        "transaction_ids": ["orig-1"],
    }
    data.update(overrides)
    return StoreSubscription(**data)


def make_event(**overrides) -> NotificationEvent:
    """A normalized notification carrying an active subscription; override per test."""
    sub_overrides = overrides.pop("sub_overrides", {})
    subscription = overrides.pop("subscription", make_sub(**sub_overrides))
    data = {
        "platform": IapPlatform.IOS,
        "store_event_id": "evt-1",
        "store_event_at": datetime.now(UTC),
        "notification_type": "DID_RENEW",
        "subscription": subscription,
    }
    data.update(overrides)
    return NotificationEvent(**data)


@pytest.fixture
def mock_apple(monkeypatch):
    fake = mock.Mock(return_value=make_sub())
    monkeypatch.setattr("apps.iap.stores.apple.verify", fake)
    return fake


@pytest.fixture
def mock_google(monkeypatch):
    fake = mock.Mock(return_value=make_sub(platform=IapPlatform.ANDROID))
    monkeypatch.setattr("apps.iap.stores.google.verify", fake)
    return fake

"""US2 — POST /iap/webhook/google (spec FR-009..014). Verifier mocked at the seam."""

import pytest

from apps.iap.models import (
    EntitlementStatus,
    IapPlatform,
    NotificationOutcome,
    StoreNotificationEvent,
    SubscriptionEntitlement,
)
from apps.iap.tests.conftest import make_event, make_sub
from core.errors import WebhookSignatureInvalid

pytestmark = pytest.mark.django_db

URL = "/iap/webhook/google"
BODY = {"message": {"data": "eyJ4IjoxfQ==", "messageId": "m-1"}}


def _android_sub(**over):
    return make_sub(platform=IapPlatform.ANDROID, **over)


def _mock_decode(monkeypatch, event):
    monkeypatch.setattr("apps.iap.stores.google.decode_notification", lambda _a, _m: event)


def test_invalid_oidc_token_returns_400(api, monkeypatch):
    monkeypatch.setattr(
        "apps.iap.stores.google.decode_notification",
        lambda _a, _m: (_ for _ in ()).throw(WebhookSignatureInvalid()),
    )
    resp = api.post(URL, BODY, format="json")
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "WEBHOOK_SIGNATURE_INVALID"
    assert SubscriptionEntitlement.objects.count() == 0


def test_renewed_creates_and_applies(api, monkeypatch):
    _mock_decode(
        monkeypatch,
        make_event(
            platform=IapPlatform.ANDROID,
            subscription=_android_sub(),
            notification_type="RENEWED",
        ),
    )
    resp = api.post(URL, BODY, format="json")
    assert resp.status_code == 200
    assert resp.json() == {}
    ent = SubscriptionEntitlement.objects.get()
    assert ent.platform == IapPlatform.ANDROID
    assert ent.status == EntitlementStatus.ACTIVE
    assert StoreNotificationEvent.objects.get().outcome == NotificationOutcome.APPLIED


def test_revoked_removes_access(api, monkeypatch):
    _mock_decode(
        monkeypatch,
        make_event(
            platform=IapPlatform.ANDROID,
            subscription=_android_sub(status=EntitlementStatus.REFUNDED),
            notification_type="REVOKED",
        ),
    )
    api.post(URL, BODY, format="json")
    assert SubscriptionEntitlement.objects.get().is_entitled is False


def test_duplicate_message_id_ignored(api, monkeypatch):
    _mock_decode(
        monkeypatch,
        make_event(
            platform=IapPlatform.ANDROID, store_event_id="dup-g", subscription=_android_sub()
        ),
    )
    api.post(URL, BODY, format="json")
    api.post(URL, BODY, format="json")
    assert StoreNotificationEvent.objects.filter(store_event_id="dup-g").count() == 1


def test_unmatched_notification_recorded(api, monkeypatch):
    # Purchase token that Google reports invalid → subscription None → unmatched, still recorded.
    _mock_decode(
        monkeypatch,
        make_event(platform=IapPlatform.ANDROID, subscription=None, store_event_id="u-1"),
    )
    assert api.post(URL, BODY, format="json").status_code == 200
    assert (
        StoreNotificationEvent.objects.get(store_event_id="u-1").outcome
        == NotificationOutcome.UNMATCHED
    )
    assert SubscriptionEntitlement.objects.count() == 0


def test_webhook_needs_no_app_key(anon, monkeypatch):
    _mock_decode(monkeypatch, make_event(platform=IapPlatform.ANDROID, subscription=_android_sub()))
    # No X-App-Key at all — signature-only endpoint still processes.
    assert anon.post(URL, BODY, format="json").status_code == 200

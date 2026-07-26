"""US2/polish — audit never leaks receipts/tokens (Constitution XI, FR-013/027)."""

import pytest

from apps.audit.models import AuditLogEntry
from apps.audit.services import AuditSanitizationError, record
from apps.iap import services

pytestmark = pytest.mark.django_db

VERIFY = "/iap/verify-receipt"
BODY = {
    "platform": "ios",
    "receipt_data": "SUPER-SECRET-RECEIPT-BLOB",
    "transaction_id": "orig-1",
    "product_id": "premium_monthly",
    "device_id": "device-abc",
}


def test_verify_audit_entry_carries_no_receipt(api, mock_apple):
    api.post(VERIFY, BODY, format="json")
    entry = AuditLogEntry.objects.get(action="iap.verify")
    serialized = str(entry.metadata)
    assert "SUPER-SECRET-RECEIPT-BLOB" not in serialized
    assert "receipt" not in {k.lower() for k in entry.metadata}
    assert "token" not in {k.lower() for k in entry.metadata}


def test_webhook_audit_entry_uses_platform_actor_label(api, monkeypatch):
    from apps.iap.tests.conftest import make_event

    monkeypatch.setattr("apps.iap.stores.apple.decode_notification", lambda _p: make_event())
    api.post("/iap/webhook/apple", {"signedPayload": "x"}, format="json")
    entry = AuditLogEntry.objects.get(action="iap.webhook")
    assert entry.actor is None
    assert entry.actor_label == "ios"


def test_audit_guard_rejects_receipt_metadata():
    # The sanitize guard is the backstop: a receipt-bearing metadata attempt must raise.
    with pytest.raises(AuditSanitizationError):
        record(None, "iap.verify", actor_label="app", receipt="leak")


def test_is_entitled_never_consults_a_user(api, mock_apple):
    # Sanity: entitlement resolves purely from transaction_id (account-less, FR-023).
    api.post(VERIFY, BODY, format="json")
    assert services.is_entitled("orig-1") is True

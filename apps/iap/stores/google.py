"""Google Play boundary adapter (BE-005).

Wraps the Google Play Developer API (``androidpublisher`` v3,
``purchases.subscriptionsv2.get``) via a service account. Normalizes to
``StoreSubscription``. The live call is mocked in tests (Constitution X); real
credential wiring is exercised in staging (research D2/D8).

Never logs the purchase token or service-account secret (Constitution XI).
"""

from __future__ import annotations

import base64
import json
from datetime import UTC, datetime

from django.conf import settings

from apps.iap.models import EntitlementStatus, IapPlatform
from apps.iap.stores.base import NotificationEvent, StoreSubscription
from core.errors import ReceiptInvalid, StoreApiUnavailable, WebhookSignatureInvalid

# Google subscriptionState → normalized status. CANCELED = auto-renew off but still in
# period → active(auto_renew=False) (F1); ON_HOLD/PAUSED/PENDING are not entitled.
_GOOGLE_STATE = {
    "SUBSCRIPTION_STATE_ACTIVE": EntitlementStatus.ACTIVE,
    "SUBSCRIPTION_STATE_IN_GRACE_PERIOD": EntitlementStatus.IN_GRACE_PERIOD,
    "SUBSCRIPTION_STATE_CANCELED": EntitlementStatus.ACTIVE,
    "SUBSCRIPTION_STATE_EXPIRED": EntitlementStatus.EXPIRED,
    "SUBSCRIPTION_STATE_ON_HOLD": EntitlementStatus.EXPIRED,
    "SUBSCRIPTION_STATE_PAUSED": EntitlementStatus.EXPIRED,
    "SUBSCRIPTION_STATE_PENDING": EntitlementStatus.EXPIRED,
}


def _parse_rfc3339(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _service():
    """Build an androidpublisher service from the service-account JSON (lazily)."""
    from google.oauth2 import service_account
    from googleapiclient.discovery import build

    info = json.loads(settings.IAP_GOOGLE_SERVICE_ACCOUNT_JSON)
    credentials = service_account.Credentials.from_service_account_info(
        info, scopes=["https://www.googleapis.com/auth/androidpublisher"]
    )
    return build("androidpublisher", "v3", credentials=credentials, cache_discovery=False)


def verify(*, receipt_data: str, transaction_id: str, product_id: str) -> StoreSubscription:
    """Verify an Android purchase (``receipt_data`` = purchase token) → normalized state.

    Raises ``ReceiptInvalid`` when Google reports the token invalid, ``StoreApiUnavailable``
    on transport/API failure.
    """
    from googleapiclient.errors import HttpError

    purchase_token = receipt_data
    try:
        service = _service()
        purchase = (
            service.purchases()
            .subscriptionsv2()
            .get(packageName=settings.IAP_GOOGLE_PACKAGE_NAME, token=purchase_token)
            .execute()
        )
    except HttpError as exc:
        if 400 <= exc.status_code < 500:
            raise ReceiptInvalid() from exc
        raise StoreApiUnavailable() from exc
    except Exception as exc:  # noqa: BLE001 — transport/timeout/config → retryable
        raise StoreApiUnavailable() from exc

    state = purchase.get("subscriptionState", "")
    status = _GOOGLE_STATE.get(state, EntitlementStatus.EXPIRED)

    line_items = purchase.get("lineItems") or []
    first = line_items[0] if line_items else {}
    expires_at = _parse_rfc3339(first.get("expiryTime"))
    resolved_product = first.get("productId") or product_id
    auto_renew = bool((first.get("autoRenewingPlan") or {}).get("autoRenewEnabled", False))

    # Stable identity: the root of the linked-purchase chain when present, else this token.
    original = purchase.get("linkedPurchaseToken") or purchase_token
    ids = [i for i in {original, purchase_token, transaction_id} if i]

    return StoreSubscription(
        platform=IapPlatform.ANDROID,
        original_transaction_id=original,
        latest_transaction_id=purchase_token,
        product_id=resolved_product,
        status=status,
        expires_at=expires_at,
        auto_renew=auto_renew,
        transaction_ids=ids,
    )


def _verify_pubsub_token(auth_header: str) -> None:
    """Verify the Pub/Sub push OIDC bearer token against our audience (the webhook auth)."""
    token = ""
    if auth_header and auth_header.lower().startswith("bearer "):
        token = auth_header.split(" ", 1)[1].strip()
    if not token:
        raise WebhookSignatureInvalid()
    try:
        from google.auth.transport import requests as g_requests
        from google.oauth2 import id_token

        id_token.verify_oauth2_token(
            token, g_requests.Request(), settings.IAP_GOOGLE_PUBSUB_AUDIENCE
        )
    except Exception as exc:  # noqa: BLE001 — any token failure → invalid signature
        raise WebhookSignatureInvalid() from exc


def decode_notification(auth_header: str, message: dict) -> NotificationEvent:
    """Verify a Play RTDN Pub/Sub push, decode it, and re-fetch authoritative state.

    Authenticated solely by the push request's OIDC token (Constitution II). Raises
    ``WebhookSignatureInvalid`` on a bad token/payload; ``StoreApiUnavailable`` may propagate
    from the re-fetch so Pub/Sub retries.
    """
    _verify_pubsub_token(auth_header)

    envelope = message or {}
    message_id = envelope.get("messageId") or envelope.get("message_id") or ""
    try:
        decoded = json.loads(base64.b64decode(envelope.get("data", "")))
    except Exception as exc:  # noqa: BLE001 — undecodable payload → invalid
        raise WebhookSignatureInvalid() from exc

    notif = decoded.get("subscriptionNotification") or {}
    purchase_token = notif.get("purchaseToken", "")
    event_ms = decoded.get("eventTimeMillis")
    store_event_at = datetime.fromtimestamp(int(event_ms) / 1000, tz=UTC) if event_ms else None

    subscription = None
    if purchase_token:
        try:
            subscription = verify(
                receipt_data=purchase_token,
                transaction_id=purchase_token,
                product_id=notif.get("subscriptionId", ""),
            )
        except ReceiptInvalid:
            subscription = None  # unmatched — still record the event

    return NotificationEvent(
        platform=IapPlatform.ANDROID,
        store_event_id=message_id,
        store_event_at=store_event_at,
        notification_type=str(notif.get("notificationType", "")),
        subscription=subscription,
    )

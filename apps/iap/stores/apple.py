"""Apple App Store boundary adapter (BE-005).

Wraps Apple's first-party ``app-store-server-library``: verify a purchase by looking up
its subscription status via the App Store Server API, then normalize to
``StoreSubscription``. The live store call is mocked in tests (Constitution X); real
credential wiring is exercised in staging (research D1/D8).

Never logs the receipt, transaction, or any signed payload (Constitution XI).
"""

from __future__ import annotations

from datetime import UTC, datetime

from django.conf import settings

from apps.iap.models import EntitlementStatus, IapPlatform
from apps.iap.stores.base import NotificationEvent, StoreSubscription
from core.errors import ReceiptInvalid, StoreApiUnavailable, WebhookSignatureInvalid

# Apple subscription status codes (get_all_subscription_statuses) → normalized status.
_APPLE_STATUS = {
    1: EntitlementStatus.ACTIVE,  # active
    2: EntitlementStatus.EXPIRED,  # expired
    3: EntitlementStatus.IN_GRACE_PERIOD,  # billing retry
    4: EntitlementStatus.IN_GRACE_PERIOD,  # billing grace period
    5: EntitlementStatus.REFUNDED,  # revoked
}


def _ms_to_dt(ms: int | None) -> datetime | None:
    if not ms:
        return None
    return datetime.fromtimestamp(ms / 1000, tz=UTC)


def _client():
    """Build an App Store Server API client from env config (lazily; import-safe)."""
    from appstoreserverlibrary.api_client import AppStoreServerAPIClient
    from appstoreserverlibrary.models.Environment import Environment

    env = (
        Environment.PRODUCTION
        if settings.IAP_APPLE_ENVIRONMENT.lower().startswith("prod")
        else Environment.SANDBOX
    )
    return AppStoreServerAPIClient(
        settings.IAP_APPLE_PRIVATE_KEY.encode("utf-8"),
        settings.IAP_APPLE_KEY_ID,
        settings.IAP_APPLE_ISSUER_ID,
        settings.IAP_APPLE_BUNDLE_ID,
        env,
    )


def _verifier():
    from appstoreserverlibrary.models.Environment import Environment
    from appstoreserverlibrary.signed_data_verifier import SignedDataVerifier

    # Apple root CAs are provisioned via env/secret store; loaded here in real deployments.
    from apps.iap.stores._apple_certs import load_apple_root_certs

    env = (
        Environment.PRODUCTION
        if settings.IAP_APPLE_ENVIRONMENT.lower().startswith("prod")
        else Environment.SANDBOX
    )
    return SignedDataVerifier(
        load_apple_root_certs(),
        True,
        env,
        settings.IAP_APPLE_BUNDLE_ID,
        settings.IAP_APPLE_APP_APPLE_ID,
    )


def verify(*, receipt_data: str, transaction_id: str, product_id: str) -> StoreSubscription:
    """Verify an iOS purchase and return normalized subscription state.

    ``receipt_data`` is accepted for parity with the contract but the App Store Server API
    resolves state from ``transaction_id`` (JWS-signed, store-authoritative). Raises
    ``ReceiptInvalid`` when Apple has no such transaction, ``StoreApiUnavailable`` on a
    transport/API failure.
    """
    from appstoreserverlibrary.api_client import APIException

    try:
        client = _client()
        response = client.get_all_subscription_statuses(transaction_id)
    except APIException as exc:
        # 4xx from Apple (unknown/invalid transaction) → receipt invalid; else unavailable.
        raise ReceiptInvalid() from exc
    except Exception as exc:  # noqa: BLE001 — transport/timeout/config → retryable
        raise StoreApiUnavailable() from exc

    verifier = _verifier()
    for group in response.data or []:
        for item in group.lastTransactions or []:
            txn = verifier.verify_and_decode_signed_transaction(item.signedTransactionInfo)
            renewal = (
                verifier.verify_and_decode_renewal_info(item.signedRenewalInfo)
                if item.signedRenewalInfo
                else None
            )
            status = _APPLE_STATUS.get(item.status, EntitlementStatus.EXPIRED)
            auto_renew = bool(getattr(renewal, "autoRenewStatus", 0)) if renewal else False
            # Auto-renew off but still within the paid period → active(auto_renew=False) (F1).
            original = txn.originalTransactionId
            ids = [i for i in {original, txn.transactionId, transaction_id} if i]
            return StoreSubscription(
                platform=IapPlatform.IOS,
                original_transaction_id=original,
                latest_transaction_id=txn.transactionId or transaction_id,
                product_id=txn.productId or product_id,
                status=status,
                expires_at=_ms_to_dt(getattr(txn, "expiresDate", None)),
                auto_renew=auto_renew,
                transaction_ids=ids,
            )

    raise ReceiptInvalid()


def _notification_status(notification_type: str, subtype: str, txn) -> EntitlementStatus:
    """Map an App Store Server Notification V2 type onto a normalized status.

    A refunded/revoked transaction wins; else EXPIRED → expired, a failed renewal in grace →
    in_grace_period; everything else (incl. cancel-but-in-period) stays active — the gate uses
    ``expires_at`` to bound it (F1).
    """
    if getattr(txn, "revocationDate", None):
        return EntitlementStatus.REFUNDED
    if notification_type == "EXPIRED":
        return EntitlementStatus.EXPIRED
    if notification_type == "DID_FAIL_TO_RENEW" and subtype != "GRACE_PERIOD":
        # billing retry without grace subtype still recoverable; grace subtype also recoverable.
        return EntitlementStatus.IN_GRACE_PERIOD
    if notification_type == "DID_FAIL_TO_RENEW":
        return EntitlementStatus.IN_GRACE_PERIOD
    if notification_type == "REFUND":
        return EntitlementStatus.REFUNDED
    return EntitlementStatus.ACTIVE


def decode_notification(signed_payload: str) -> NotificationEvent:
    """Verify + decode an App Store Server Notification V2 into a ``NotificationEvent``.

    Raises ``WebhookSignatureInvalid`` if the JWS or any inner payload fails verification.
    """
    if not signed_payload:
        raise WebhookSignatureInvalid()
    try:
        verifier = _verifier()
        payload = verifier.verify_and_decode_notification(signed_payload)
        data = payload.data
        txn = (
            verifier.verify_and_decode_signed_transaction(data.signedTransactionInfo)
            if data and data.signedTransactionInfo
            else None
        )
        renewal = (
            verifier.verify_and_decode_renewal_info(data.signedRenewalInfo)
            if data and data.signedRenewalInfo
            else None
        )
    except Exception as exc:  # noqa: BLE001 — any verify/decode failure → invalid signature
        raise WebhookSignatureInvalid() from exc

    subscription = None
    if txn is not None:
        subtype = getattr(payload, "subtype", "") or ""
        status = _notification_status(str(payload.notificationType), str(subtype), txn)
        auto_renew = bool(getattr(renewal, "autoRenewStatus", 0)) if renewal else False
        original = txn.originalTransactionId
        ids = [i for i in {original, txn.transactionId} if i]
        subscription = StoreSubscription(
            platform=IapPlatform.IOS,
            original_transaction_id=original,
            latest_transaction_id=txn.transactionId or original,
            product_id=txn.productId or "",
            status=status,
            expires_at=_ms_to_dt(getattr(txn, "expiresDate", None)),
            auto_renew=auto_renew,
            transaction_ids=ids,
        )

    return NotificationEvent(
        platform=IapPlatform.IOS,
        store_event_id=payload.notificationUUID,
        store_event_at=_ms_to_dt(getattr(payload, "signedDate", None)),
        notification_type=str(payload.notificationType),
        subscription=subscription,
    )

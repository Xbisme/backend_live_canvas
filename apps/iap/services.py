"""IAP domain services — the public surface other apps and views call (Constitution V).

Public functions:
- ``verify_receipt(...)`` — verify a purchase with the store and upsert its entitlement.
- ``is_entitled(transaction_id)`` — the boolean the download gate calls (no reach-in).
- ``resolve_status(transaction_id)`` — read-only entitlement lookup for status.
- ``process_apple_notification`` / ``process_google_notification`` — verify + apply a webhook.

Store I/O is isolated in ``apps.iap.stores.*`` (mocked at that seam in tests). Entitlement
records are store-authoritative and never overwritten by a lower-trust source (Constitution IX).
"""

from __future__ import annotations

from datetime import datetime

from django.db import transaction
from django.http import Http404
from django.utils import timezone

from apps.iap.models import (
    EntitlementTransaction,
    IapPlatform,
    NotificationOutcome,
    StoreNotificationEvent,
    SubscriptionEntitlement,
)
from apps.iap.stores import apple as apple_store
from apps.iap.stores import google as google_store
from apps.iap.stores.base import NotificationEvent, StoreSubscription
from core.errors import ReceiptConflict

_ADAPTERS = {IapPlatform.IOS: apple_store, IapPlatform.ANDROID: google_store}


# ---------------------------------------------------------------------------
# Verify (US1)
# ---------------------------------------------------------------------------
def verify_receipt(
    *, platform: str, receipt_data: str, transaction_id: str, product_id: str, device_id: str
) -> SubscriptionEntitlement:
    """Verify a purchase with the store and upsert the entitlement (idempotent).

    Raises ``ReceiptInvalid`` / ``StoreApiUnavailable`` (from the adapter) or
    ``ReceiptConflict`` when ``transaction_id`` is already bound to a different subscription.
    """
    adapter = _ADAPTERS[platform]
    sub = adapter.verify(
        receipt_data=receipt_data, transaction_id=transaction_id, product_id=product_id
    )
    _guard_conflict(sub, incoming_transaction_id=transaction_id)
    entitlement = _write_entitlement(
        sub, device_id=device_id, incoming_transaction_id=transaction_id
    )
    _audit(entitlement, "iap.verify", actor_label="app")
    return entitlement


def _guard_conflict(sub: StoreSubscription, *, incoming_transaction_id: str) -> None:
    """Reject a ``transaction_id`` already bound to a DIFFERENT subscription (FR-007)."""
    existing_ref = (
        EntitlementTransaction.objects.select_related("entitlement")
        .filter(platform=sub.platform, transaction_id=incoming_transaction_id)
        .first()
    )
    if (
        existing_ref
        and existing_ref.entitlement.original_transaction_id != sub.original_transaction_id
    ):
        raise ReceiptConflict()


@transaction.atomic
def _write_entitlement(
    sub: StoreSubscription,
    *,
    device_id: str = "",
    incoming_transaction_id: str = "",
    store_event_at: datetime | None = None,
) -> SubscriptionEntitlement:
    """Create or refresh the entitlement keyed by the store's original transaction id.

    Store-authoritative fields are overwritten from ``sub`` on every call (idempotent). All
    known chain ids are indexed so any of them resolves back to this entitlement.
    """
    entitlement, _created = SubscriptionEntitlement.objects.select_for_update().get_or_create(
        platform=sub.platform,
        original_transaction_id=sub.original_transaction_id,
        defaults={
            "product_id": sub.product_id,
            "status": sub.status,
            "expires_at": sub.expires_at,
            "auto_renew": sub.auto_renew,
            "latest_transaction_id": sub.latest_transaction_id,
            "origin_device_id": device_id or "",
        },
    )
    entitlement.product_id = sub.product_id
    entitlement.status = sub.status
    entitlement.expires_at = sub.expires_at
    entitlement.auto_renew = sub.auto_renew
    entitlement.latest_transaction_id = sub.latest_transaction_id
    entitlement.last_verified_at = timezone.now()
    if store_event_at is not None:
        entitlement.last_store_event_at = store_event_at
    if not entitlement.origin_device_id and device_id:
        entitlement.origin_device_id = device_id
    entitlement.save()

    for txn_id in {*sub.transaction_ids, incoming_transaction_id, sub.latest_transaction_id}:
        if not txn_id:
            continue
        EntitlementTransaction.objects.get_or_create(
            platform=sub.platform,
            transaction_id=txn_id,
            defaults={"entitlement": entitlement},
        )
    return entitlement


# ---------------------------------------------------------------------------
# Resolution / gate (US1, US3)
# ---------------------------------------------------------------------------
def _resolve(transaction_id: str) -> SubscriptionEntitlement | None:
    """Resolve any known per-period ``transaction_id`` → its entitlement (any platform)."""
    if not transaction_id:
        return None
    ref = (
        EntitlementTransaction.objects.select_related("entitlement")
        .filter(transaction_id=transaction_id)
        .first()
    )
    return ref.entitlement if ref else None


def is_entitled(transaction_id: str | None) -> bool:
    """Public gate helper: does this ``transaction_id`` currently grant premium access?

    Evaluated freshly from the stored entitlement (FR-021). Returns False for a missing/
    unknown id or a non-entitled status.
    """
    entitlement = _resolve(transaction_id or "")
    return bool(entitlement and entitlement.is_entitled)


def resolve_status(transaction_id: str) -> SubscriptionEntitlement:
    """Read-only lookup for ``GET /iap/subscription-status``; 404 if unknown (FR-016/017)."""
    entitlement = _resolve(transaction_id)
    if entitlement is None:
        raise Http404("No subscription for this transaction.")
    return entitlement


# ---------------------------------------------------------------------------
# Webhooks (US2)
# ---------------------------------------------------------------------------
def process_apple_notification(signed_payload: str) -> StoreNotificationEvent:
    """Verify + apply an App Store Server Notification V2 (raises WebhookSignatureInvalid)."""
    return apply_notification(apple_store.decode_notification(signed_payload))


def process_google_notification(auth_header: str, message: dict) -> StoreNotificationEvent:
    """Verify + apply a Google Play RTDN Pub/Sub push (raises WebhookSignatureInvalid)."""
    return apply_notification(google_store.decode_notification(auth_header, message))


@transaction.atomic
def apply_notification(event: NotificationEvent) -> StoreNotificationEvent:
    """Apply a verified notification to the entitlement, idempotent + order-safe (FR-011/012).

    Duplicate store event id → no-op (``duplicate_ignored``). An event older than the newest
    already applied → recorded ``stale_ignored`` with no state change (SC-007). Otherwise the
    entitlement state converges to the notification's authoritative state.
    """
    existing = StoreNotificationEvent.objects.filter(
        platform=event.platform, store_event_id=event.store_event_id
    ).first()
    if existing:
        return existing

    sub = event.subscription
    entitlement: SubscriptionEntitlement | None = None
    outcome = NotificationOutcome.UNMATCHED

    if sub is not None:
        entitlement = (
            SubscriptionEntitlement.objects.select_for_update()
            .filter(platform=sub.platform, original_transaction_id=sub.original_transaction_id)
            .first()
        )
        if entitlement is None:
            # A subscription never verified through the app — still record store truth.
            entitlement = _write_entitlement(sub, store_event_at=event.store_event_at)
            outcome = NotificationOutcome.APPLIED
        elif _is_stale(entitlement, event.store_event_at):
            outcome = NotificationOutcome.STALE_IGNORED
        else:
            entitlement = _write_entitlement(sub, store_event_at=event.store_event_at)
            outcome = NotificationOutcome.APPLIED

    record = StoreNotificationEvent.objects.create(
        platform=event.platform,
        store_event_id=event.store_event_id,
        notification_type=event.notification_type,
        original_transaction_id=sub.original_transaction_id if sub else "",
        store_event_at=event.store_event_at,
        outcome=outcome,
    )
    if entitlement is not None and outcome == NotificationOutcome.APPLIED:
        _audit(
            entitlement,
            "iap.webhook",
            actor_label=event.platform,
            event_type=event.notification_type,
        )
    return record


def _is_stale(entitlement: SubscriptionEntitlement, store_event_at: datetime | None) -> bool:
    """An event is stale if it is not newer than the last one applied (out-of-order guard)."""
    if entitlement.last_store_event_at is None or store_event_at is None:
        return False
    return store_event_at <= entitlement.last_store_event_at


# ---------------------------------------------------------------------------
# Audit
# ---------------------------------------------------------------------------
def _audit(entitlement: SubscriptionEntitlement, action: str, *, actor_label: str, **extra) -> None:
    """Record a sanitized audit entry — NEVER the receipt/token (guard forbids 'receipt')."""
    from apps.audit import services as audit

    audit.record(
        None,
        action,
        entitlement,
        actor_label=actor_label,
        platform=entitlement.platform,
        product_id=entitlement.product_id,
        status=entitlement.status,
        original_transaction_id=entitlement.original_transaction_id,
        **extra,
    )

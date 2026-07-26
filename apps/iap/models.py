"""IAP domain models — account-less premium entitlement (BE-005, Constitution II/IX).

``SubscriptionEntitlement`` is the sole source of truth for premium download access,
keyed by the store's **original transaction id** (stable across renewals). Every
per-period transaction id in a subscription's renewal chain is indexed by
``EntitlementTransaction`` so verify / status / download can resolve any id the client
holds back to the one entitlement. ``StoreNotificationEvent`` is the append-only
idempotency + audit ledger for store lifecycle notifications.

These are financial records: authoritative from the store, never overwritten by a
lower-trust source (Constitution IX).
"""

from __future__ import annotations

from django.db import models
from django.utils import timezone


class IapPlatform(models.TextChoices):
    IOS = "ios", "iOS (App Store)"
    ANDROID = "android", "Android (Google Play)"


class EntitlementStatus(models.TextChoices):
    ACTIVE = "active", "Active"
    IN_GRACE_PERIOD = "in_grace_period", "In grace period / billing retry"
    EXPIRED = "expired", "Expired"
    CANCELED = "canceled", "Canceled (lapsed)"
    REFUNDED = "refunded", "Refunded"


# Statuses that grant premium download access (grace/billing-retry counts — Clarification Q2/F1).
ENTITLED_STATUSES = frozenset({EntitlementStatus.ACTIVE, EntitlementStatus.IN_GRACE_PERIOD})


class SubscriptionEntitlement(models.Model):
    """One row per store subscription over its whole renewal life (data-model §1)."""

    platform = models.CharField(max_length=10, choices=IapPlatform.choices)
    # Stable key across renewals: Apple originalTransactionId / Google subscription root.
    original_transaction_id = models.CharField(max_length=255)
    # Most recent per-period transaction id seen (informational).
    latest_transaction_id = models.CharField(max_length=255, blank=True)
    product_id = models.CharField(max_length=255)
    status = models.CharField(max_length=20, choices=EntitlementStatus.choices)
    expires_at = models.DateTimeField(null=True, blank=True)
    auto_renew = models.BooleanField(default=False)
    # Recorded for abuse signals only — NEVER an access constraint (Clarification Q3).
    origin_device_id = models.CharField(max_length=255, blank=True)
    # Newest store event applied — idempotency / out-of-order guard (research D5).
    last_store_event_at = models.DateTimeField(null=True, blank=True)
    last_verified_at = models.DateTimeField(default=timezone.now)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["platform", "original_transaction_id"],
                name="iap_entitlement_unique_original_txn",
            ),
        ]
        indexes = [
            models.Index(
                fields=["platform", "original_transaction_id"], name="iap_ent_original_idx"
            ),
        ]

    def __str__(self) -> str:  # pragma: no cover - repr convenience
        return f"{self.platform}:{self.original_transaction_id} ({self.status})"

    @property
    def is_entitled(self) -> bool:
        """True iff the subscription currently grants premium download access.

        ``active`` or ``in_grace_period`` AND not past ``expires_at``. Evaluated freshly
        at the download edge (FR-021) — never cached from an earlier status query.
        """
        if self.status not in ENTITLED_STATUSES:
            return False
        return self.expires_at is None or self.expires_at > timezone.now()


class EntitlementTransaction(models.Model):
    """Secondary index: any known per-period ``transaction_id`` → its entitlement.

    Lets the client resolve its entitlement by whichever id it holds (original or any
    renewal), so status/download keep working after renewals (research D3).
    """

    entitlement = models.ForeignKey(
        SubscriptionEntitlement, on_delete=models.CASCADE, related_name="transactions"
    )
    platform = models.CharField(max_length=10, choices=IapPlatform.choices)
    transaction_id = models.CharField(max_length=255)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["platform", "transaction_id"],
                name="iap_txn_ref_unique",
            ),
        ]
        indexes = [
            models.Index(fields=["platform", "transaction_id"], name="iap_txn_ref_idx"),
        ]

    def __str__(self) -> str:  # pragma: no cover - repr convenience
        return f"{self.platform}:{self.transaction_id}"


class NotificationOutcome(models.TextChoices):
    APPLIED = "applied", "Applied"
    DUPLICATE_IGNORED = "duplicate_ignored", "Duplicate ignored"
    STALE_IGNORED = "stale_ignored", "Stale / out-of-order ignored"
    UNMATCHED = "unmatched", "Unmatched (no entitlement)"


class StoreNotificationEvent(models.Model):
    """Append-only ledger of accepted store notifications (data-model §2, FR-012/013).

    Unique on (platform, store_event_id) so replays are no-ops. Stores NO secrets or full
    signed payloads (Constitution XI).
    """

    platform = models.CharField(max_length=10, choices=IapPlatform.choices)
    store_event_id = models.CharField(max_length=255)
    notification_type = models.CharField(max_length=120)
    original_transaction_id = models.CharField(max_length=255, blank=True)
    store_event_at = models.DateTimeField(null=True, blank=True)
    outcome = models.CharField(max_length=20, choices=NotificationOutcome.choices)
    received_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["platform", "store_event_id"],
                name="iap_notif_event_unique",
            ),
        ]
        indexes = [
            models.Index(fields=["original_transaction_id"], name="iap_notif_original_idx"),
        ]

    def __str__(self) -> str:  # pragma: no cover - repr convenience
        return f"{self.platform}:{self.store_event_id} ({self.outcome})"

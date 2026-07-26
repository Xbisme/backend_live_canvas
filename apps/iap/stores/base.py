"""Normalized store-verification result — the boundary type both adapters return.

Keeping a single store-agnostic shape means ``apps.iap.services`` never branches on
platform-specific payloads (Constitution V) and tests mock at exactly one seam.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from apps.iap.models import EntitlementStatus


@dataclass(frozen=True)
class StoreSubscription:
    """Store-authoritative subscription state, normalized across Apple and Google."""

    platform: str
    original_transaction_id: str
    latest_transaction_id: str
    product_id: str
    status: EntitlementStatus
    expires_at: datetime | None
    auto_renew: bool
    # Known per-period transaction ids to index (at least original + latest).
    transaction_ids: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class NotificationEvent:
    """A verified store lifecycle notification, normalized for ``apply_notification``.

    ``subscription`` carries the authoritative state to apply (may be ``None`` when the
    notification could not be tied to a resolvable subscription).
    """

    platform: str
    store_event_id: str
    store_event_at: datetime | None
    notification_type: str
    subscription: StoreSubscription | None

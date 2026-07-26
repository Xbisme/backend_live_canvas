# Phase 1 Data Model: IAP Verify & Entitlement (BE-005)

New models live in **`apps/iap`** (scaffolded empty since BE-002). No existing model is
restructured; `apps/wallpapers.Wallpaper.is_premium` is read by the download gate but not
modified. All new tables are IAP/financial records — Constitution IX: authoritative from
the store, never overwritten by a lower-trust source.

---

## Entity: `SubscriptionEntitlement`

The account-less unit of premium access. One row per store subscription over its entire
renewal life. **Stable identity = the store's original/linking transaction identifier**
(Clarification D3).

| Field | Type | Notes |
|---|---|---|
| `id` | PK | surrogate |
| `platform` | enum `ios` \| `android` | store of origin |
| `original_transaction_id` | string, indexed | **stable key**; Apple `originalTransactionId`, Google subscription/linked-purchase root. Unique per `(platform, original_transaction_id)`. |
| `latest_transaction_id` | string | most recent per-period transaction id seen |
| `product_id` | string | e.g. `premium_monthly` |
| `status` | enum | `active` \| `in_grace_period` \| `expired` \| `canceled` \| `refunded` (matches contract `SubscriptionStatus.status`). Auto-renew turned off while still in the paid period → `active` with `auto_renew=false` (NOT `canceled`); `canceled` = actually lapsed (F1). |
| `expires_at` | datetime, nullable | current period end (store-authoritative) |
| `auto_renew` | bool | store-reported renewal intent |
| `origin_device_id` | string, nullable | recorded for abuse signals only — **never** an access constraint (Clarification D3) |
| `last_store_event_at` | datetime, nullable | timestamp of the newest store event applied (idempotency/order guard, D5) |
| `last_verified_at` | datetime | last successful store re-fetch |
| `created_at` / `updated_at` | datetime | audit |

**Derived — `is_entitled` (not stored, computed at read/gate time)**: true iff
`status ∈ {active, in_grace_period}` AND (`expires_at` is null OR `expires_at > now`).
This is the sole input to the premium download gate (FR-018, FR-021). Evaluated **freshly**
at each `download-url` request — never cached from an earlier status query.

**Uniqueness / integrity**:
- Unique `(platform, original_transaction_id)`.
- `RECEIPT_CONFLICT` (409) when an incoming `transaction_id` is already mapped to a
  *different* entitlement/subscription than the proof resolves to (identity mismatch) —
  not merely a different device (FR-007).

**State transitions** (driven by verify-receipt re-fetch and by webhooks, D4):

```
(new verify)            → active | in_grace_period | expired   (from store state)
active        --DID_RENEW/RENEWED-->        active (expires_at extended)
active        --auto-renew off-->           active (auto_renew=false) → later expired
active        --DID_FAIL_TO_RENEW/GRACE-->  in_grace_period
in_grace_period --recover/renew-->          active
in_grace_period --final expiry-->           expired
active|in_grace|expired --REFUND/REVOKED--> refunded   (access revoked immediately)
```

Transitions apply only if the driving event is **newer** than `last_store_event_at`
(older events recorded, no state regression — D5, SC-007).

---

## Entity: `StoreNotificationEvent`

Append-only audit + idempotency ledger of accepted store lifecycle notifications and the
entitlement change each produced. Does **not** store secrets or full signed payloads
(FR-013, FR-027).

| Field | Type | Notes |
|---|---|---|
| `id` | PK | surrogate |
| `platform` | enum `ios` \| `android` | |
| `store_event_id` | string | Apple `notificationUUID`, Google `messageId` |
| `notification_type` | string | normalized + raw store type (e.g. `DID_RENEW`, `EXPIRED`, `RENEWED`) |
| `original_transaction_id` | string, indexed, nullable | link to affected entitlement (nullable if unmatched) |
| `store_event_at` | datetime | store-reported event time (order guard) |
| `outcome` | enum | `applied` \| `duplicate_ignored` \| `stale_ignored` \| `unmatched` |
| `received_at` | datetime | server receive time |

**Uniqueness / integrity**:
- Unique `(platform, store_event_id)` → replays are recorded once and are no-ops (D5, FR-012).
- Append-only; rows are never mutated after write.

**Relationship**: many `StoreNotificationEvent` → one `SubscriptionEntitlement`
(by `original_transaction_id`); an event may be `unmatched` if it references a subscription
never verified through the app (still recorded so a later verify is consistent).

---

## Read/write access map

| Endpoint | Reads | Writes |
|---|---|---|
| `POST /iap/verify-receipt` | store API | upsert `SubscriptionEntitlement` |
| `POST /iap/webhook/apple` \| `/google` | store API (re-fetch) | `SubscriptionEntitlement` (transition), `StoreNotificationEvent` (append) |
| `GET /iap/subscription-status` | `SubscriptionEntitlement` (resolve by any `transaction_id`) | — (read-only, FR-017) |
| `GET /wallpapers/{id}/download-url` (premium) | `SubscriptionEntitlement.is_entitled` | — |

The existing append-only **audit trail** (`apps/audit`, BE-004) additionally records
webhook receipt + entitlement mutations for cross-cutting audit, via `audit.services.record`
(sanitized — no secrets/payloads). `StoreNotificationEvent` is the IAP-domain idempotency
ledger; the audit trail is the cross-cutting activity log — they are complementary.

---

## Migrations

- New app `apps/iap` migrations: create `SubscriptionEntitlement`, `StoreNotificationEvent`.
- Non-destructive, additive only (Constitution IX). No change to `wallpapers`/`uploads`
  schema. Indexes on `original_transaction_id` (both tables) and the transaction-id lookup
  path.

# Phase 0 Research: IAP Verify & Entitlement (BE-005)

Resolves the technical unknowns for verifying App Store / Google Play purchases,
processing store lifecycle notifications, and gating premium downloads — under the
constitution (two-tier auth isolation, account-less entitlement, download-edge
gate, structured errors, two-flavor config, dependency hygiene).

All external stores are mocked at their boundary in tests (Constitution X); no test
hits a real store API.

---

## D1. Apple purchase verification + notification decoding

**Decision**: Use Apple's official **`app-store-server-library`** (PyPI, latest stable
**3.1.2**, released 2026-06-01, requires Python 3.8+ — compatible with the repo's 3.11).

- Verification path: **App Store Server API** (JWT-authenticated with our issuer key /
  key id / private key) via the library's `AppStoreServerAPIClient` — look up the
  transaction / subscription status server-side using the `transactionId` the client
  sends. We do **not** use the deprecated `verifyReceipt` legacy endpoint.
- Notification path: the library's **`SignedDataVerifier`** verifies and decodes
  App Store Server Notifications **V2** `signedPayload` (JWS) against Apple root certs,
  bound to our bundle id + environment (sandbox in dev, production in prod).

**Rationale**: First-party library, tracks Apple's cert chain and payload schema,
handles JWS verification correctly (the security-critical part we must not hand-roll).
Provides both API client and notification verifier — covers FR-002, FR-009/010.

**Alternatives considered**:
- Hand-rolled JWS verification with `PyJWT` + manual x5c chain validation — rejected:
  re-implements security-critical cert-chain logic Apple already ships and maintains.
- Legacy `verifyReceipt` endpoint — rejected: deprecated by Apple; App Store Server API
  is the current path and returns richer, signed transaction/renewal info.

---

## D2. Google Play purchase verification + RTDN

**Decision**: Verify purchases with the **Google Play Developer API** (`androidpublisher`,
`purchases.subscriptionsv2.get`) via **`google-api-python-client`** (latest stable
**2.198.0**) authenticated by a **service account** through **`google-auth`** (latest
stable **2.56.2**, requires Python ≥3.10 — compatible). RTDN (Real-time Developer
Notifications) arrive via **Pub/Sub push**; verify the request's OIDC bearer token with
`google-auth` (`google.oauth2.id_token.verify_oauth2_token`) against our expected
audience, then decode the base64 `message.data` JSON.

**Rationale**: `subscriptionsv2.get` returns the authoritative subscription state
(line items, expiry, auto-renew, acknowledgement) keyed by purchase token; service-account
auth is the standard server-to-server pattern. Pub/Sub push authenticity is the OIDC
token, not the payload — verifying it is the real webhook gate for Google (FR-009/010).

**Alternatives considered**:
- `purchases.subscriptions.get` (v1) — rejected: superseded by `subscriptionsv2`, which
  models multi-line-item subscriptions and the current state machine.
- Trusting the Pub/Sub payload without OIDC verification — rejected: violates
  Constitution II (webhook authenticated solely by verified signature/token).

---

## D3. Entitlement identity & renewal linking (Clarification 2026-07-26)

**Decision**: The entitlement's **stable primary identity is the store's
original/linking transaction identifier** — Apple `originalTransactionId`, Google
`linkedPurchaseToken` chain root / the subscription's stable identifier. Every
per-period `transaction_id` in the renewal chain resolves to the one entitlement row.
Store a secondary index of "known transaction ids → entitlement" so `verify-receipt`,
`subscription-status`, and `download-url` can all resolve a client-supplied
`transaction_id` (any period) to the entitlement.

**Rationale**: Renewals mint new transaction ids; keying on the first-seen id would make
renewal webhooks fail to match (Clarification Q1). Keying on the stable original id keeps
one row per subscription over its whole life and makes webhook matching deterministic.

**Alternatives considered**: key by first-seen `transaction_id` (webhook renewals miss);
one row per transaction id (hard to express refund/expiry of the subscription as a whole).

---

## D4. Lifecycle state model & "entitled" definition (Clarification 2026-07-26)

**Decision**: Persist a normalized `status` ∈ {`active`, `in_grace_period`, `expired`,
`canceled`, `refunded`} (matches the contract `SubscriptionStatus.status` enum) plus
`expires_at` and `auto_renew`. The **download gate treats `active` and `in_grace_period`
(recoverable billing-retry) as entitled**; `expired`, `canceled`-and-lapsed, and
`refunded` are not. Map store-specific notification types onto these normalized states:
- Apple V2 `notificationType`/`subtype`: `SUBSCRIBED`/`DID_RENEW` → active,
  `DID_FAIL_TO_RENEW` (+ `GRACE_PERIOD`) → in_grace_period, `EXPIRED` → expired,
  `DID_CHANGE_RENEWAL_STATUS`(auto-renew off) → active but `auto_renew=false`,
  `REFUND` → refunded.
- Google RTDN `subscriptionNotificationType`: `RENEWED` → active, `IN_GRACE_PERIOD` →
  in_grace_period, `EXPIRED` → expired, `CANCELED` (auto-renew turned off, still within the
  paid period) → **active with `auto_renew=false`**, `REVOKED` → refunded.

**"auto-renew off but still in period" → `active` (Clarification F1, 2026-07-26)**: turning
off auto-renew while the paid period is still running maps to `status=active, auto_renew=false`
(NOT a `canceled` status). The `canceled` status is reserved for a subscription that has
actually **lapsed** (period ended, not renewed). This keeps the gate rule simple —
`is_entitled = status ∈ {active, in_grace_period}` — with `expires_at` still bounding an
`active` row.

**Rationale**: A single normalized state machine keeps the gate logic store-agnostic and
testable; the grace-period-as-entitled rule was confirmed in Clarification Q2. Mapping
"cancelled-but-in-period" to `active(auto_renew=false)` avoids a two-branch gate and prevents
wrongly denying a paying user who simply turned off renewal (F1).

**Alternatives considered**: store raw store-specific statuses and branch per platform at
the gate — rejected: duplicates entitlement logic and is error-prone to test.

---

## D5. Webhook idempotency & out-of-order safety

**Decision**: Each notification carries a store event identity + a monotonic signal
(Apple `signedDate`/`notificationUUID`; Google `eventTimeMillis`/`messageId`). Record every
accepted event in an append-only **Store Notification Event** table keyed by
(platform, store event id) with a unique constraint → duplicates are no-ops. Apply a
state transition only if the event's timestamp is **newer** than the entitlement's
`last_store_event_at`; older/out-of-order events are recorded but do not regress state.
Re-fetch authoritative state from the store API when a notification is ambiguous.

**Rationale**: Satisfies FR-012/SC-007 (converge to the store's latest authoritative
state, never corrupted by replays) without locking or relying on delivery order.

**Alternatives considered**: last-write-wins on arrival — rejected: out-of-order delivery
would let a stale event overwrite fresh state.

---

## D6. Async vs inline verification

**Decision**: Run `verify-receipt` **synchronously** within the request (single outbound
store call, user is waiting to unlock) with a bounded timeout; on store timeout/5xx return
`503 STORE_API_UNAVAILABLE` (retryable). Process **webhooks** by verifying signature inline
(fast, must ack quickly) and doing the store re-fetch + persistence inline as well, since it
is a single API call; only offload to Celery if a webhook needs heavy fan-out (not expected
here). No new Celery task is required for the MVP.

**Rationale**: Constitution VII mandates async only for *heavy media* work; a single
store lookup is a lightweight I/O call appropriate for the request thread with a timeout.
Keeps the design simple (Constitution V: boring composition).

**Alternatives considered**: push verification to Celery and poll — rejected: adds latency
and complexity to a user-blocking unlock with no benefit at this scale.

---

## D7. Secrets & two-flavor config

**Decision**: All store credentials come from the environment via `django-environ`, per
flavor (`.env.dev` / `.env.prod`), never committed; add the keys to `.env.*.example` only.
Needed config: Apple issuer id / key id / private key (.p8 contents) / bundle id / app apple
id / environment; Google service-account JSON (or path) / package name / Pub/Sub audience.
Dev uses store **sandbox**; prod uses production. Never log any of these, nor receipts /
purchase tokens / signed payloads (Constitution XI, FR-027).

**Rationale**: Direct application of Constitution VIII (two-flavor) and XI (secret hygiene).

**Alternatives considered**: a third "sandbox" flavor — explicitly forbidden by
Constitution VIII; sandbox vs prod is selected by env values within dev/prod.

---

## D8. Dependencies to add (versions verified on PyPI, 2026-07-26)

| Package | Latest stable | Python | Purpose |
|---|---|---|---|
| `app-store-server-library` | 3.1.2 (2026-06-01) | ≥3.8 | Apple App Store Server API client + V2 notification JWS verify/decode |
| `google-api-python-client` | 2.198.0 | ≥3.7 | Google Play Developer API (`androidpublisher` subscriptionsv2) |
| `google-auth` | 2.56.2 | ≥3.10 | Service-account auth + Pub/Sub OIDC token verification |

Pin in `requirements/base.in`, compile locks with `uv pip compile` (universal,
`--python-version 3.11`, matching the repo's existing lock convention), commit `.in` + `.txt`.
`PyJWT` / `cryptography` are already present (via simplejwt from BE-004) and are transitive
deps of the above; no separate JWT hand-rolling. Review each library's changelog before
pinning a major.

**Rationale**: First-party / standard Google libraries for the security-critical parsing;
matches Constitution XI dependency hygiene (versions looked up, not guessed).

---

## Open items deferred to later specs (not blocking BE-005)

- Rate limiting / load testing of `/iap/*` and `download-url` → **BE-006**.
- Production store credential provisioning, Pub/Sub topic + push subscription setup,
  App Store Server Notification URL registration → **BE-006/BE-007** (dev sandbox wired here).
- ClamAV (unrelated to IAP) remains deferred to BE-006.

# Feature Specification: IAP Verify & Entitlement

**Feature Branch**: `BE-005-iap-verify-entitlement`

**Created**: 2026-07-26

**Status**: Draft

**Input**: User description: "BE-005 IAP Verify & Entitlement — Self-hosted In-App Purchase verification và entitlement gate cho LiveCanvas. Không dùng RevenueCat. Không có user/account system: entitlement premium xác định qua store transaction_id (App Store / Google Play)."

## Overview

LiveCanvas monetizes premium wallpapers through store-native subscriptions (Apple App Store, Google Play). The app has **no user/account system** — a buyer's premium access is derived entirely from a verified store `transaction_id`, never from a login or profile. This feature makes premium unlock actually work end-to-end: the backend independently verifies purchases with the stores, keeps each subscription's lifecycle state current as the store reports changes, and enforces entitlement at the moment a premium wallpaper is downloaded.

Today (after BE-004) every premium wallpaper's `download-url` returns `402 ENTITLEMENT_REQUIRED` unconditionally. This feature replaces that hard block with a real entitlement check.

## Clarifications

### Session 2026-07-26

- Q: Subscription tự gia hạn cấp transaction_id mới mỗi kỳ — entitlement định danh ổn định theo identifier nào? → A: Theo **original/linking transaction id** của store (ổn định qua mọi kỳ renewal); backend resolve bất kỳ transaction_id trong chuỗi về entitlement gốc, nên webhook renewal khớp đúng và app tra cứu bằng transaction_id nào cũng ra.
- Q: Subscription ở trạng thái store còn cứu được (grace period / billing retry) có còn quyền tải premium không? → A: **Còn quyền** cho tới khi store báo hết hạn hẳn (final expiration); grace/billing-retry vẫn được coi là entitled.
- Q: Chính sách ràng buộc device_id với transaction_id (RECEIPT_CONFLICT + restore máy mới)? → A: **Không ràng buộc device** — transaction_id là chìa khoá duy nhất; device_id chỉ ghi nhận để phát hiện lạm dụng, không chặn. Restore trên máy mới tự do. RECEIPT_CONFLICT chỉ khi cùng transaction_id nhưng receipt trỏ tới transaction/tài khoản store khác.
- Q (F1): User TẮT auto-renew nhưng còn trong kỳ đã trả tiền — gate xử sao? → A: Map về **`status=active, auto_renew=false`** (KHÔNG phải `canceled`); `canceled` chỉ dành cho subscription đã lapse hẳn. Giữ `is_entitled = status ∈ {active, in_grace_period}` — người đã mua không bị chặn khi tắt gia hạn.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Buyer unlocks and downloads a premium wallpaper (Priority: P1)

A person buys a premium subscription in the app (handled by the store's native purchase sheet). The app sends the purchase proof to the backend, which verifies it directly with Apple/Google and records an active entitlement keyed by the purchase's `transaction_id`. From then on, the app can obtain time-limited download links for premium wallpapers by presenting that `transaction_id`.

**Why this priority**: This is the core monetization path and the whole reason the feature exists. Without it, premium content cannot be sold. It is the minimum viable slice: verify a purchase, then let that purchase unlock downloads.

**Independent Test**: With a valid (sandbox) purchase proof, call verify → receive an `active` status; then request a premium wallpaper's download link with that `transaction_id` → receive a short-lived link. Request the same link without a valid `transaction_id` → blocked.

**Acceptance Scenarios**:

1. **Given** a valid, un-registered purchase proof, **When** the app submits it for verification, **Then** the backend confirms it with the store and returns the subscription's status, product, expiry, and auto-renew flag.
2. **Given** a verified active entitlement, **When** the app requests a premium wallpaper's download link with the matching `transaction_id`, **Then** the backend returns a link that expires within 5 minutes.
3. **Given** a request for a premium wallpaper's download link with no `transaction_id`, **When** the backend evaluates entitlement, **Then** it refuses with an "entitlement required" error.
4. **Given** a request for a premium wallpaper's download link with a `transaction_id` whose entitlement is expired or not active, **When** the backend evaluates entitlement, **Then** it refuses with an "entitlement required" error.
5. **Given** a free (non-premium) wallpaper, **When** the app requests its download link with or without a `transaction_id`, **Then** the backend returns the link without an entitlement check (unchanged from prior behavior).
6. **Given** a purchase proof that the store rejects, **When** the app submits it, **Then** the backend returns a "receipt invalid" error and records no entitlement.

---

### User Story 2 - Subscription lifecycle stays current as the store reports changes (Priority: P2)

Subscriptions renew, lapse, get cancelled, enter billing-retry/grace periods, or are refunded — often while the app is closed. The stores push these events to the backend. The backend verifies each notification's authenticity and updates the affected entitlement so that download access reflects the true current state without the app having to re-submit a receipt.

**Why this priority**: Keeps entitlement honest over time — prevents lapsed/refunded subscriptions from retaining access and lets renewals extend access seamlessly. Important, but P1 already delivers a sellable unlock for the initial term; this hardens correctness across the lifecycle.

**Independent Test**: Send a store-signed renewal notification for a known subscription → its expiry extends. Send a signed refund/expiry notification → its access is revoked. Send a notification with a tampered/invalid signature → rejected, no state change.

**Acceptance Scenarios**:

1. **Given** an existing subscription, **When** a store-authenticated renewal notification arrives, **Then** the entitlement's expiry and auto-renew state are updated and access continues.
2. **Given** an existing active subscription, **When** a store-authenticated refund or expiration notification arrives, **Then** the entitlement is revoked so subsequent premium download requests are refused.
3. **Given** any store notification, **When** its signature/authenticity cannot be verified, **Then** the backend rejects it with a "webhook signature invalid" error and makes no state change.
4. **Given** a duplicate or out-of-order notification for a subscription, **When** it is processed, **Then** the entitlement reflects the store's authoritative latest state and is not corrupted by replays.

---

### User Story 3 - App re-checks / restores entitlement state (Priority: P3)

The app needs to reflect the current premium state in its UI (e.g., after reinstall, on a new device via store "restore purchases", or on app launch) without forcing a full re-verification each time. It queries the backend for the current status of a `transaction_id`.

**Why this priority**: Improves correctness of the app's premium UI and supports restore-across-devices, but the actual gate is enforced at download time regardless, so this is a convenience/consistency layer rather than a security boundary.

**Independent Test**: Query status for a known active `transaction_id` → returns active with expiry. Query for an unknown `transaction_id` → not found.

**Acceptance Scenarios**:

1. **Given** a known `transaction_id`, **When** the app queries its subscription status, **Then** the backend returns the current status, product, expiry, and auto-renew flag.
2. **Given** an unknown `transaction_id`, **When** the app queries its status, **Then** the backend returns a "not found" result.

---

### Edge Cases

- **Store API unreachable during verification**: the backend surfaces a "store temporarily unavailable" error (retryable) and records no false entitlement.
- **Receipt resolves to a different subscription**: a `transaction_id` presented with a proof that verifies to a different store subscription/account than the one already bound is rejected as `RECEIPT_CONFLICT` rather than silently re-bound. A merely different `device_id` is NOT a conflict — restore across devices succeeds.
- **Grace period / billing retry**: a subscription the store still considers recoverable grants download access (entitled) until the store reports final expiration.
- **Expiry crossing between checks**: an entitlement that lapses between a status query and a later download request is re-evaluated at download time — the download gate is always the authoritative check, never the earlier query.
- **Free wallpaper with a `transaction_id`**: the `transaction_id` is ignored; no entitlement check runs for free content.
- **Premium wallpaper not yet published (`processing`/`failed`/deleted)**: continues to return "not found" (unchanged), evaluated independently of the entitlement check.
- **Webhook for a subscription never verified via the app**: the backend still records the store-authoritative state so a later verify/status call is consistent.
- **Cross-platform product mismatch**: a proof whose platform (iOS/Android) does not match the claimed platform is treated as invalid.

## Requirements *(mandatory)*

### Functional Requirements

#### Purchase verification

- **FR-001**: System MUST accept a purchase-verification request carrying the platform, the store purchase proof, the `transaction_id`, the `product_id`, and a `device_id`, authenticated by the app tier (`X-App-Key`).
- **FR-002**: System MUST verify the purchase proof directly with the corresponding store's server-side verification service (Apple for iOS, Google for Android) — never trusting client-asserted status.
- **FR-003**: On successful verification, System MUST persist/refresh a subscription entitlement whose **stable identity is the store's original/linking transaction identifier** (constant across all renewals of the same subscription), recording at minimum: platform, product, status, expiry, auto-renew flag, the originating device, and the current/latest per-period transaction identifier. Any `transaction_id` belonging to the subscription's renewal chain MUST resolve to this single entitlement.
- **FR-004**: On successful verification, System MUST return the subscription's `transaction_id`, `product_id`, `status`, `expires_at`, and `auto_renew`.
- **FR-005**: When the store rejects the proof, System MUST return a `RECEIPT_INVALID` error and record no entitlement.
- **FR-006**: When the store's verification service is unavailable, System MUST return a `STORE_API_UNAVAILABLE` (retryable) error and record no false entitlement.
- **FR-007**: `device_id` MUST be recorded for abuse signals only and MUST NOT restrict entitlement — the same subscription re-verified from any device (store "restore purchases") MUST succeed, with no per-device limit. System MUST return `RECEIPT_CONFLICT` only when a `transaction_id` is presented with a proof/receipt that resolves to a **different** store subscription/account than the one already bound to it (identity mismatch), never merely because the device differs.
- **FR-008**: Verification MUST be idempotent — re-submitting the same valid proof refreshes (not duplicates) the entitlement and returns the current state.

#### Store lifecycle notifications (webhooks)

- **FR-009**: System MUST expose store notification endpoints for Apple and Google that are authenticated **solely** by verifying the notification's cryptographic signature/authenticity — accepting neither `X-App-Key` nor admin JWT.
- **FR-010**: System MUST reject any notification whose signature/authenticity fails verification with a `WEBHOOK_SIGNATURE_INVALID` error and MUST make no state change.
- **FR-011**: On an authenticated notification, System MUST update the affected entitlement's lifecycle state (e.g., renewed, expired, cancelled, refunded, grace/billing-retry) to match the store's authoritative state.
- **FR-012**: Notification processing MUST be resilient to duplicate and out-of-order delivery — the resulting entitlement state MUST converge to the store's latest authoritative state and never be corrupted by replays.
- **FR-013**: System MUST record an auditable trail of received store notifications and the entitlement changes they cause, without logging secrets or full signed payloads. [Uses the existing append-only audit trail.]
- **FR-014**: System MUST acknowledge a successfully processed notification with a success response so the store does not retry unnecessarily.

#### Subscription status query

- **FR-015**: System MUST expose a status-lookup endpoint (app tier, `X-App-Key`) that, given a `transaction_id`, returns the current `status`, `product_id`, `expires_at`, and `auto_renew`.
- **FR-016**: A status lookup for an unknown `transaction_id` MUST return `NOT_FOUND`.
- **FR-017**: The status lookup MUST be read-only and MUST NOT itself grant or extend entitlement.

#### Entitlement gate at download

- **FR-018**: For a premium wallpaper, System MUST require a `transaction_id` that resolves to a currently-**entitled** subscription before issuing a download link; otherwise it MUST refuse with `ENTITLEMENT_REQUIRED` (402). "Entitled" means `status ∈ {active, in_grace_period}` (the latter covering recoverable grace-period / billing-retry) and not past `expires_at` — access is granted until the store reports final expiration; `expired`, `canceled` (lapsed), and `refunded` are NOT entitled. Auto-renew turned off but still within the paid period is `active` (`auto_renew=false`), so it remains entitled (F1).
- **FR-019**: For a free wallpaper, System MUST issue the download link without any entitlement check (behavior unchanged from BE-004), and any supplied `transaction_id` is ignored.
- **FR-020**: A premium download link, when issued, MUST expire within 5 minutes.
- **FR-021**: The entitlement decision at download time MUST be the authoritative gate — evaluated freshly at request time from the stored entitlement, independent of any earlier status query.
- **FR-022**: The existing "not found for `processing`/`failed`/deleted wallpaper" behavior MUST be preserved and evaluated independently of the entitlement check.
- **FR-023**: Entitlement MUST be derived exclusively from a verified store `transaction_id` — never from any user record, session, or client-asserted claim.

#### Cross-cutting

- **FR-024**: All error responses MUST use the structured error envelope and codes from the catalog (`ENTITLEMENT_REQUIRED`, `RECEIPT_INVALID`, `RECEIPT_CONFLICT`, `STORE_API_UNAVAILABLE`, `WEBHOOK_SIGNATURE_INVALID`, `NOT_FOUND`, `INVALID_APP_KEY`, `VALIDATION_ERROR`, `SERVER_ERROR`), produced via the centralized handler.
- **FR-025**: The two auth tiers MUST remain strictly isolated: `/iap/verify-receipt` and `/iap/subscription-status` are app-tier only; the webhook endpoints are signature-only; none of these accept admin JWT, and none fall back across tiers.
- **FR-026**: The API contract (`openapi.yaml` + `api-context.md`) MUST be bumped for the new IAP surface and, after merge, copied verbatim to `livecanvas-mobile` per contract-first dual-repo sync.
- **FR-027**: System MUST never log store secrets, `X-App-Key`, receipts, purchase tokens, or full signed webhook payloads.

### Key Entities *(include if feature involves data)*

- **Subscription Entitlement**: the account-less unit of premium access. **Stable identity = the store's original/linking transaction identifier** (constant across renewals); every per-period `transaction_id` in the renewal chain resolves to it. Attributes: platform (iOS/Android), `product_id`, lifecycle `status` (`active` / `in_grace_period` / `expired` / `canceled` / `refunded`), `expires_at`, `auto_renew`, latest per-period transaction identifier, originating `device_id` (recorded for abuse signals only, not an access constraint), and verification/update timestamps. Access is granted for `active` and `in_grace_period` (recoverable billing-retry) states. Turning off auto-renew while still inside the paid period is recorded as `active` with `auto_renew=false` (not `canceled`); `canceled` denotes an actually-lapsed subscription (F1). Relationships: none to any user (there are no users); it is the sole source of truth for premium download access.
- **Store Notification Event**: an append-only record of a received, authenticated store lifecycle notification and the entitlement change it produced — for audit and idempotency/replay handling. Attributes: platform, notification type, associated transaction identifier, received time, processing outcome. Does not store secrets or full signed payloads.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A buyer with a valid purchase can go from "verify purchase" to "obtain a premium download link" with no login and no account, using only the store `transaction_id`.
- **SC-002**: 100% of premium download-link requests without a currently-active entitlement are refused; 100% of free download-link requests succeed regardless of `transaction_id`.
- **SC-003**: A subscription that the store reports as renewed regains/retains access, and one reported as expired/refunded loses access, within one notification-processing cycle of the store's push — with no app-initiated re-verification required.
- **SC-004**: 100% of store notifications with an invalid or tampered signature are rejected and cause zero entitlement changes.
- **SC-005**: Every premium download link issued expires within 5 minutes of issuance.
- **SC-006**: No user record or session is ever consulted to make an entitlement decision — every decision traces to a verified `transaction_id`.
- **SC-007**: Duplicate or out-of-order store notifications never leave an entitlement in a state that contradicts the store's latest authoritative report.

## Assumptions

- **Store purchase UX is client-side**: the native store purchase/subscription sheet, price display, and receipt acquisition happen in the mobile app; the backend's role begins at verification. Out of scope: any in-app purchase UI, pricing, or store product configuration.
- **Products are subscriptions**: premium is a renewable subscription (monthly/other) rather than a one-time non-consumable, so lifecycle notifications and expiry apply. (One-time purchases, if ever added, would be a later change.)
- **Grace/billing-retry access rule** (confirmed, Clarifications 2026-07-26): a subscription in a store-recoverable state (grace period / billing retry) is treated as **still entitled** until the store reports final expiration.
- **Entitlement identity** (confirmed, Clarifications 2026-07-26): the stable key is the store's **original/linking transaction identifier**; per-period renewal transaction IDs all resolve to the one entitlement, so webhook renewals match and the app can query by any `transaction_id` in the chain.
- **Device policy** (confirmed, Clarifications 2026-07-26): `device_id` is recorded for abuse signals only and never limits access; restore-on-new-device always works. `RECEIPT_CONFLICT` is reserved for a `transaction_id` presented with a proof resolving to a different store subscription/account.
- **Store credentials/config provided via environment** per the two-flavor discipline (dev vs prod); sandbox/test store environments are used in dev.
- **Reuses existing infrastructure**: the app-tier auth (`X-App-Key`), the centralized error catalog/handler, the presigned download-URL mechanism (BE-004), and the append-only audit trail (BE-004) are reused rather than rebuilt.
- **The `apps/iap` app** (scaffolded in BE-002) is the home for this feature's models, verification, webhook handling, and entitlement logic.
- **Contract placeholders exist**: `api-context.md`/`openapi.yaml` already sketch the IAP endpoints and error codes for BE-005; this feature makes them real and finalizes the contract version bump.

## Dependencies

- **BE-003** (content models + `download-url` edge) and **BE-004** (real presigned `download-url`, audit app, two-tier auth). This feature opens the entitlement gate that BE-004 stubbed at `402`.
- **External**: Apple App Store Server API + App Store Server Notifications V2; Google Play Developer API + Real-time Developer Notifications (Pub/Sub). Requires store-side credentials and notification configuration.
- **Downstream sync point**: `livecanvas-mobile` needs these endpoints working for real to test its purchase flow end-to-end (MO-005) — notify on merge.

## Out of Scope

- In-app purchase UI, price/paywall presentation, and store product setup (mobile/store responsibility).
- Refund initiation, customer support tooling, or admin dashboards for subscriptions.
- Promotional offers, free trials logic beyond what the store reports, family sharing nuances, and proration edge cases (may be revisited later).
- One-time / consumable purchase types.
- Rate limiting / load testing of these endpoints (BE-006) and production store credential provisioning/deploy (BE-006/BE-007).

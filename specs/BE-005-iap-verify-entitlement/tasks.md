---
description: "Task list for BE-005 IAP Verify & Entitlement"
---

# Tasks: IAP Verify & Entitlement (BE-005)

**Input**: Design documents from `specs/BE-005-iap-verify-entitlement/`

**Prerequisites**: [plan.md](plan.md), [spec.md](spec.md), [research.md](research.md), [data-model.md](data-model.md), [contracts/iap-contract-delta.md](contracts/iap-contract-delta.md), [quickstart.md](quickstart.md)

**Tests**: INCLUDED — Constitution X mandates tests for two-tier auth isolation, entitlement
gating at `download-url`, and IAP verify + webhook signature handling. Stores are mocked at
their boundary; no test hits a real store.

**Organization**: grouped by user story (P1→P3) for independent implementation + testing.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: parallelizable (different files, no dependency on an incomplete task)
- **[Story]**: US1 / US2 / US3 (setup, foundational, polish have no story label)

## Path Conventions

Single Django web-service project; feature lives in `apps/iap/` + surgical edits to
`apps/wallpapers/`, `core/`, `config/`, `requirements/`, and `.claude/` (contract). Tests are
colocated per app (`apps/iap/tests/`, `apps/wallpapers/tests/`, `core/tests/`).

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: contract-first bump + dependencies + config, before any server code (Constitution I, XI, VIII).

- [X] T001 Bump contract to **v0.5.0** in `.claude/openapi.yaml` (`info.version`, `download-url` summary → real premium gate, top description note) and `.claude/api-context.md` (header version, "Đổi so với v0.4.0" note, update download-url + IAP sections to drop "402 vô điều kiện / gate mở ở BE-005"), per [contracts/iap-contract-delta.md](contracts/iap-contract-delta.md)
- [X] T002 Sync both contract files verbatim to `livecanvas-mobile` (`.claude/` + `contracts/`) and note the sync in the mobile changelog (cross-repo, manual) — done 2026-07-26: also synced `screen-inventory.md`, bumped mobile `project-context.md`/`sdd-roadmap.md` headers, and corrected the MO-006 sync point from BE-004 to BE-005
- [X] T003 [P] Add `app-store-server-library==3.1.2`, `google-api-python-client==2.198.0`, `google-auth==2.56.2` to `requirements/base.in`; compile locks with `uv pip compile --universal --python-version 3.11`; commit `base.in` + `base.txt`
- [X] T004 [P] Add IAP env keys (`IAP_APPLE_*`, `IAP_GOOGLE_*`) across `config/settings/base.py` (default=""), `config/settings/prod.py` (no-default fail-fast), `config/settings/dev.py` (sandbox), and document them in `.env.dev.example` + `.env.prod.example`

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: shared building blocks every story needs. **⚠️ No user story can begin until these are done.**

- [X] T005 Add `AppError` subclasses `ReceiptInvalid` (400), `ReceiptConflict` (409), `StoreApiUnavailable` (503), `WebhookSignatureInvalid` (400) in `core/errors.py` (codes already declared at lines 34-39; `EntitlementRequired` already exists)
- [X] T006 Create `SubscriptionEntitlement` + `StoreNotificationEvent` models in `apps/iap/models.py` per [data-model.md](data-model.md) (unique `(platform, original_transaction_id)`; unique `(platform, store_event_id)`; indexes on `original_transaction_id`)
- [X] T007 Generate migration `apps/iap/migrations/0001_initial.py` (`makemigrations apps.iap`; additive only, verify `makemigrations --check` clean)
- [X] T008 [P] Create `SubscriptionStatus` serializer (shared by verify + status) in `apps/iap/serializers.py` matching the contract shape (`transaction_id`, `product_id`, `status` enum, `expires_at` nullable, `auto_renew`)
- [X] T009 Create `apps/iap/urls.py` skeleton and include it in `config/urls.py` **before** the Django-admin catch-all (`path("", include("apps.iap.urls"))`)

**Checkpoint**: models, errors, contract, config ready — user stories can begin.

---

## Phase 3: User Story 1 - Buyer unlocks and downloads a premium wallpaper (Priority: P1) 🎯 MVP

**Goal**: Verify a purchase → record entitlement → premium `download-url` returns a ≤5-min link for an entitled `transaction_id`, `402` otherwise; free unchanged.

**Independent Test**: with the store adapter mocked to return an active subscription,
`verify-receipt` → 200 active; `download-url?transaction_id=<id>` → 200 short-lived link;
without/expired txn → 402; free wallpaper → 200. (quickstart Scenario A.)

### Tests for User Story 1

- [X] T010 [P] [US1] Test `POST /iap/verify-receipt` (ios + android happy — assert `SubscriptionStatus` shape: `transaction_id/product_id/status/expires_at/auto_renew`; `RECEIPT_INVALID`, `RECEIPT_CONFLICT`, `STORE_API_UNAVAILABLE`, idempotent re-verify; adapter mocked) in `apps/iap/tests/test_verify_receipt.py`
- [X] T011 [P] [US1] Update `apps/wallpapers/tests/test_download_url.py` — premium + entitled txn → 200 ≤5min (assert `download_url` + `expires_at` shape); premium no/expired txn → 402 `ENTITLEMENT_REQUIRED`; grace-period → 200; **auto-renew-off-but-in-period (active, auto_renew=false) → 200**; free → 200 regardless of txn; **premium + `processing`/`failed` wallpaper + valid txn → 404 (404 evaluated before the entitlement gate — FR-022)**
- [X] T012 [P] [US1] Test `services.is_entitled()` resolves by any renewal-chain `transaction_id`, honors active + in_grace_period, rejects expired/refunded, in `apps/iap/tests/test_entitlement.py`

### Implementation for User Story 1

- [X] T013 [US1] Add `VerifyReceiptRequest` serializer (`platform` ios|android, `receipt_data`, `transaction_id`, `product_id`, `device_id`) in `apps/iap/serializers.py`
- [X] T014 [P] [US1] Apple verify adapter — App Store Server API client, resolve transaction/subscription state by `transactionId`, return normalized status/expiry/auto_renew/original_transaction_id, in `apps/iap/stores/apple.py`
- [X] T015 [P] [US1] Google verify adapter — Play Developer API `purchases.subscriptionsv2.get` via service account, return normalized state, in `apps/iap/stores/google.py`
- [X] T016 [US1] `services.verify_receipt(data)` — call platform adapter, upsert `SubscriptionEntitlement` keyed by original transaction id (idempotent); raise `ReceiptConflict` when the incoming `transaction_id` is already mapped to an entitlement whose `original_transaction_id` differs from the one the adapter resolves (identity mismatch — NOT a device difference); raise `ReceiptInvalid` when the adapter rejects; `StoreApiUnavailable` on store timeout/5xx; in `apps/iap/services.py`
- [X] T017 [US1] `services.is_entitled(transaction_id)` (public boundary fn) — resolve any chain id → entitlement, return true iff `status ∈ {active, in_grace_period}` and not past `expires_at`, in `apps/iap/services.py`
- [X] T018 [US1] `VerifyReceiptView(AppTierAPIView)` (thin: validate → `verify_receipt` → `SubscriptionStatus`) in `apps/iap/views.py` + route `POST /iap/verify-receipt` in `apps/iap/urls.py`
- [X] T019 [US1] Open the gate: read `transaction_id` from `request.query_params` in `apps/wallpapers/views.py` `WallpaperDownloadUrlView.get` and pass to `build_download_url`; in `apps/wallpapers/services.py` replace the unconditional premium `EntitlementRequired` (lines 162-163) with `if wallpaper.is_premium and not iap_services.is_entitled(transaction_id): raise EntitlementRequired()` (import the **public** `apps.iap.services`, no internal reach-in)
- [X] T020 [US1] Record a sanitized audit entry on successful verify via `audit.services.record` (use `actor_label` for the app principal; **never** put `receipt_data`/tokens in metadata — sanitize guard forbids "receipt")

**Checkpoint**: MVP — premium content is sellable and gated end-to-end.

---

## Phase 4: User Story 2 - Subscription lifecycle stays current via store webhooks (Priority: P2)

**Goal**: signature-verified Apple/Google notifications update entitlement state (renew/expire/refund), idempotent and order-safe; invalid signatures rejected with no state change.

**Independent Test**: valid renewal → expiry extended; valid refund/expiry → access revoked;
invalid signature → 400, no change; duplicate → no-op; out-of-order → no regression.
(quickstart Scenario B.)

### Tests for User Story 2

- [X] T021 [P] [US2] Test `POST /iap/webhook/apple` — valid vs invalid JWS signature, `DID_RENEW`/`EXPIRED`/`REFUND` transitions, duplicate (idempotent), out-of-order (no regression); verifier mocked — in `apps/iap/tests/test_webhook_apple.py`
- [X] T022 [P] [US2] Test `POST /iap/webhook/google` — valid vs invalid Pub/Sub OIDC token, `RENEWED`/`EXPIRED`/`REVOKED` transitions, duplicate + out-of-order; verifier mocked — in `apps/iap/tests/test_webhook_google.py`

### Implementation for User Story 2

- [X] T023 [US2] Add a signature-only base view (no `X-App-Key`, no JWT — `authentication_classes = []`, `permission_classes = [AllowAny]`) in `core/api.py` for webhooks, keeping it distinct from `AppTierAPIView`/`AdminTierAPIView`
- [X] T024 [P] [US2] Apple notification decode — `SignedDataVerifier` V2 verify+decode `signedPayload` against Apple root certs + bundle id + environment; map `notificationType`/`subtype` → normalized state; raise `WebhookSignatureInvalid` on failure — in `apps/iap/stores/apple.py`
- [X] T025 [P] [US2] Google RTDN handling — verify Pub/Sub OIDC bearer token (`google-auth`) against expected audience, base64-decode `message.data`, map `subscriptionNotificationType` → normalized state; raise `WebhookSignatureInvalid` on failure — in `apps/iap/stores/google.py`
- [X] T026 [US2] `services.apply_notification(platform, event)` — append `StoreNotificationEvent` (unique store event id → duplicate no-op), apply transition only if newer than `last_store_event_at` (else `stale_ignored`), re-fetch store state when ambiguous, revoke on refund/expire; in `apps/iap/services.py`
- [X] T027 [US2] `AppleWebhookView` + `GoogleWebhookView` (signature-only base) — verify → `apply_notification` → `200 {}` — in `apps/iap/views.py` + routes `POST /iap/webhook/apple|google` in `apps/iap/urls.py`
- [X] T028 [US2] Record sanitized audit entries for webhook receipt + entitlement mutation via `audit.services.record` with `actor=None, actor_label="apple"|"google"` (webhooks have no request user); no signed payload / token in metadata

**Checkpoint**: entitlement stays honest across the subscription lifecycle.

---

## Phase 5: User Story 3 - App re-checks / restores entitlement state (Priority: P3)

**Goal**: read-only status lookup by `transaction_id` (any chain id) → current state; unknown → 404.

**Independent Test**: known/renewal-chain id → 200 current state; unknown → 404; no mutation.
(quickstart Scenario C.)

### Tests for User Story 3

- [X] T029 [P] [US3] Test `GET /iap/subscription-status` — known txn → 200 `SubscriptionStatus`, renewal-chain id resolves to same entitlement, unknown → `404 NOT_FOUND`, read-only (no DB write) — in `apps/iap/tests/test_status.py`

### Implementation for User Story 3

- [X] T030 [US3] `services.resolve_status(transaction_id)` — read-only resolve any chain id → `SubscriptionEntitlement`, raise `NotFound` if none; never mutate/extend (FR-017) — in `apps/iap/services.py`
- [X] T031 [US3] `SubscriptionStatusView(AppTierAPIView)` (validate required `transaction_id` query → `resolve_status` → `SubscriptionStatus`) in `apps/iap/views.py` + route `GET /iap/subscription-status` in `apps/iap/urls.py`

**Checkpoint**: all three stories independently functional.

---

## Phase 6: Polish & Cross-Cutting Concerns

- [X] T032 [P] Update `core/tests/test_tier_isolation.py` — add `/iap/verify-receipt` + `/iap/subscription-status` as app-tier (401 without `X-App-Key`, admin JWT does not satisfy), and `/iap/webhook/apple|google` as signature-only
- [X] T033 [P] Verify no secret/receipt/token/payload reaches logs or audit metadata (review logging + a negative test asserting `AuditSanitizationError` on a receipt-bearing metadata attempt)
- [X] T034 Run quality gates: `ruff check . && ruff format --check .`; `pytest`; `python manage.py makemigrations --check --dry-run` (all clean)
- [X] T035 Run [quickstart.md](quickstart.md) validation end-to-end (mocked stores) incl. the auth-isolation table
- [X] T036 Update `.claude/project-context.md`, `.claude/sdd-roadmap.md` (BE-005 status), and `.claude/changelog.md` (contract v0.5.0 shipped, synced to mobile)

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: start immediately. T001 (contract) precedes code per Constitution I; T003/T004 [P].
- **Foundational (Phase 2)**: after Setup; **blocks all stories**. T006→T007 (model before migration); T005/T008 [P]; T009 after urls exist.
- **User Stories (Phase 3-5)**: after Foundational. US1→US2→US3 in priority order, or parallel by developer (they share `apps/iap/services.py` + `stores/*.py`, so parallel work needs coordination on those files).
- **Polish (Phase 6)**: after the targeted stories are complete.

### User Story Dependencies

- **US1 (P1)**: after Foundational. No dependency on US2/US3. Delivers the MVP.
- **US2 (P2)**: after Foundational. Mutates the same entitlement US1 creates but is independently testable (can seed an entitlement directly). Extends `stores/*.py` + `services.py`.
- **US3 (P3)**: after Foundational. Read-only over the entitlement; independently testable (seed then query).

### Within Each Story

- Tests written first and failing before implementation (Constitution X / TDD).
- Serializers/adapters (models exist from Foundational) → services → views/routes → gate/audit wiring.

### Parallel Opportunities

- Setup: T003, T004 in parallel.
- Foundational: T005, T008 in parallel (T006/T007/T009 ordered).
- US1: tests T010–T012 in parallel; adapters T014, T015 in parallel.
- US2: tests T021, T022 in parallel; adapters T024, T025 in parallel.
- Polish: T032, T033 in parallel.
- ⚠️ `apps/iap/services.py` is touched by T016/T017 (US1), T026 (US2), T030 (US3) — **not** parallel-safe across those; same for `stores/apple.py`/`stores/google.py` (US1 verify + US2 notification parts).

---

## Parallel Example: User Story 1

```bash
# Tests together:
Task: "test_verify_receipt.py (T010)"
Task: "update test_download_url.py (T011)"
Task: "test_entitlement.py (T012)"

# Store adapters together (verify parts):
Task: "Apple verify adapter apps/iap/stores/apple.py (T014)"
Task: "Google verify adapter apps/iap/stores/google.py (T015)"
```

---

## Implementation Strategy

### MVP First (User Story 1 only)

1. Phase 1 Setup → 2. Phase 2 Foundational → 3. Phase 3 US1 → 4. **STOP & VALIDATE** premium
   unlock + gate (quickstart Scenario A + auth-isolation) → sellable increment.

### Incremental Delivery

Setup + Foundational → US1 (MVP: verify + gate) → US2 (webhook lifecycle) → US3 (status/restore),
each tested independently against mocked stores before moving on.

---

## Notes

- [P] = different files, no incomplete-task dependency; `services.py` / `stores/*.py` are shared across stories — coordinate.
- Contract (T001) lands before code; sync to mobile (T002) can trail but before merge.
- Keep views thin; all orchestration in `apps/iap/services.py`; the gate calls only the **public** `apps.iap.services.is_entitled` (Constitution V).
- Never log or audit receipts/tokens/signed payloads (Constitution XI; audit guard forbids "receipt").
- Commit after each task or logical group; run the Phase 6 quality gates before merge.

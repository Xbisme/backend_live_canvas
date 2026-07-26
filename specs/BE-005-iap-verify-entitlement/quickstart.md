# Quickstart & Validation: IAP Verify & Entitlement (BE-005)

End-to-end validation that BE-005 works. Stores are **mocked at their boundary** — no test or
local run hits Apple/Google (Constitution X). Implementation code (model bodies, service logic,
migrations, full test suites) belongs to `/speckit-tasks` + implement, not here.

## Prerequisites

```bash
uv pip sync requirements/dev.txt          # after the 3 IAP libs are added + compiled
docker compose up -d db redis minio       # existing dev infra (BE-004)
python manage.py migrate                  # applies apps/iap 0001_initial
python manage.py seed_content             # 397 wallpapers incl. 83 premium
# .env.dev must define IAP_APPLE_* / IAP_GOOGLE_* (sandbox); see .env.dev.example
```

## Config sanity (two-flavor)

```bash
python manage.py check                                        # dev boots without IAP creds set
export DJANGO_SETTINGS_MODULE=config.settings.prod
python manage.py check --deploy   # prod FAILS FAST if IAP_APPLE_* / IAP_GOOGLE_* unset
```

Expected: dev tolerates empty IAP creds (sandbox ergonomics); prod refuses to boot without them.

## Scenario A — Buyer unlocks a premium wallpaper (User Story 1, P1)

With the Apple/Google adapter mocked to return an active subscription:

1. `POST /iap/verify-receipt` with header `X-App-Key` and body
   `{platform, receipt_data, transaction_id, product_id, device_id}`
   → `200` `SubscriptionStatus` with `status: "active"`, `expires_at`, `auto_renew`.
2. `GET /wallpapers/{premiumId}/download-url?transaction_id=<same id>` with `X-App-Key`
   → `200` `{download_url, expires_at}`, `expires_at` ≤ now + 5 min.
3. `GET /wallpapers/{premiumId}/download-url` **without** `transaction_id` → `402 ENTITLEMENT_REQUIRED`.
4. `GET /wallpapers/{premiumId}/download-url?transaction_id=<expired/unknown>` → `402 ENTITLEMENT_REQUIRED`.
5. `GET /wallpapers/{freeId}/download-url` (with or without `transaction_id`) → `200` (unchanged).
6. `POST /iap/verify-receipt` with adapter mocked to reject → `400 RECEIPT_INVALID`, no entitlement row.

## Scenario B — Lifecycle via webhooks (User Story 2, P2)

Adapter mocked to verify signatures/tokens deterministically:

1. Seed an entitlement (via Scenario A). Send a **valid** Apple `DID_RENEW` /
   Google `RENEWED` notification → entitlement `expires_at` extended, still entitled;
   `200 {}`; a `StoreNotificationEvent` row (`outcome: applied`).
2. Send a **valid** refund/expiry (`REFUND`/`REVOKED`/`EXPIRED`) → entitlement revoked;
   subsequent premium `download-url` → `402`.
3. Send a notification with an **invalid** signature/OIDC token → `400 WEBHOOK_SIGNATURE_INVALID`,
   **no** state change, no applied event.
4. Re-send the **same** notification (same store event id) → `200`, `outcome: duplicate_ignored`,
   entitlement unchanged (idempotent).
5. Send an **older** (out-of-order) event after a newer one → recorded `outcome: stale_ignored`,
   no state regression (SC-007).

## Scenario C — Status lookup / restore (User Story 3, P3)

1. `GET /iap/subscription-status?transaction_id=<known>` with `X-App-Key`
   → `200` `SubscriptionStatus` (current state). Also succeeds for a **renewal-chain** id that
   differs from the originally-verified one (resolves to same entitlement).
2. `GET /iap/subscription-status?transaction_id=<unknown>` → `404 NOT_FOUND`.
3. Status lookup performs **no** store write and does not extend entitlement (FR-017).

## Auth-isolation checks (Constitution II) — required

| Request | Expected |
|---|---|
| `POST /iap/verify-receipt` without `X-App-Key` | `401 INVALID_APP_KEY` |
| `GET /iap/subscription-status` without `X-App-Key` | `401 INVALID_APP_KEY` |
| `POST /iap/verify-receipt` with admin `Bearer` JWT but no `X-App-Key` | `401` (admin token does NOT satisfy app tier) |
| `POST /iap/webhook/apple` with `X-App-Key` but invalid signature | `400 WEBHOOK_SIGNATURE_INVALID` (app key irrelevant to webhooks) |
| `POST /iap/webhook/*` with valid signature, no `X-App-Key` | `200` (signature-only auth) |

Update `core/tests/test_tier_isolation.py` to include `/iap/verify-receipt` +
`/iap/subscription-status` as app-tier and the two webhooks as signature-only.

## Required test coverage (Constitution X)

- verify-receipt: ios + android happy path, `RECEIPT_INVALID`, `RECEIPT_CONFLICT`,
  `STORE_API_UNAVAILABLE`, idempotent re-verify.
- webhook: valid + invalid signature (both platforms), renew/expire/refund transitions,
  duplicate (idempotent) + out-of-order (no regression), unmatched notification recorded.
- entitlement gate: premium entitled → 200, premium not-entitled/no-txn → 402, free → 200,
  grace-period → 200, renewal-chain id resolves.
- status: found, unknown → 404, read-only (no mutation).
- error-catalog mapping: every code above returns the structured envelope with the right HTTP.

## Definition of done

- All scenarios A–C pass with mocked store boundaries; auth-isolation table green.
- `ruff check . && ruff format --check .` clean; `pytest` green;
  `python manage.py makemigrations --check --dry-run` reports no drift.
- Contract bumped to v0.5.0 and synced to `livecanvas-mobile`.
- No secret/receipt/token/payload appears in logs or audit metadata (sanitize guard holds).

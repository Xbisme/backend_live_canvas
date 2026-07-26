# Implementation Plan: IAP Verify & Entitlement (BE-005)

**Branch**: `BE-005-iap-verify-entitlement` | **Date**: 2026-07-26 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/BE-005-iap-verify-entitlement/spec.md`

## Summary

Make self-hosted IAP work end-to-end: verify App Store / Google Play purchases against
the stores' server APIs, keep each subscription's lifecycle current via signature-verified
store webhooks, expose a read-only status lookup, and open the real premium entitlement gate
at `GET /wallpapers/{id}/download-url` (today an unconditional `402`). All premium access is
account-less — derived only from a store `transaction_id` resolved to a stored entitlement.

Technical approach: a new populated `apps/iap` (models + serializers + views + a public
`services` module + store adapters) using Apple's first-party `app-store-server-library` and
Google's `google-api-python-client`/`google-auth`; the wallpapers download gate calls a
**public** `apps.iap.services` function (no cross-app internal imports) to decide entitlement.
Contract endpoints already exist as placeholders at v0.4.0 — this feature activates them and
bumps the contract to **v0.5.0** (download-url premium semantics change).

## Technical Context

**Language/Version**: Python 3.11 (repo locks compiled `--python-version 3.11`)

**Primary Dependencies**: Django 5.2 + DRF 3.17.1; **new**: `app-store-server-library` 3.1.2
(Apple API client + V2 JWS notification verify), `google-api-python-client` 2.198.0 +
`google-auth` 2.56.2 (Google Play Developer API `subscriptionsv2` + Pub/Sub OIDC verify).
`cryptography`/`PyJWT` already present transitively (simplejwt). See [research.md](research.md) D8.

**Storage**: PostgreSQL — two new tables in `apps/iap` (`SubscriptionEntitlement`,
`StoreNotificationEvent`); see [data-model.md](data-model.md). Reuses existing private-bucket
presign (`apps/uploads/storage.presign_download`, TTL 300s) for premium downloads.

**Testing**: `pytest-django` with existing fixtures (`api` = X-App-Key client, `anon`,
`admin_client`); stores mocked at their boundary (Constitution X — no real store/API calls).

**Target Platform**: Linux server (Django API), two flavors dev/prod.

**Project Type**: Web service (Django + DRF API), single backend project.

**Performance Goals**: `verify-receipt` and premium `download-url` complete within a normal
web request (single bounded outbound store call for verify; entitlement gate is one indexed
DB read). Store timeout → `503 STORE_API_UNAVAILABLE`. No throughput target here (BE-006).

**Constraints**: presigned premium URL expiry ≤ 5 min (existing `PRESIGNED_DOWNLOAD_TTL=300`);
webhook auth is signature/OIDC-only; never log secrets/receipts/tokens/payloads.

**Scale/Scope**: 4 endpoints (2 app-tier, 2 signature-only webhooks) + 1 modified gate;
2 new models; ~1 store adapter per platform. Catalog of 397 wallpapers (83 premium) unchanged.

## Constitution Check

*GATE: evaluated pre-Phase 0 and re-checked post-Phase 1 design.*

| Principle | Gate | Status |
|---|---|---|
| I. Contract-First & Dual-Repo Sync | Contract updated before code; version bumped; synced to mobile | ✅ Plan bumps `.claude/openapi.yaml` + `api-context.md` to **v0.5.0** (download-url premium gate + IAP endpoints live) as the first implementation task; sync-to-mobile is an explicit task. Endpoints/schemas/error codes already sketched in the frozen contract. |
| II. Two-Tier Auth Isolation & Account-Less | `/iap/verify-receipt`, `/iap/subscription-status` app-tier only; webhooks signature-only; no admin JWT; entitlement only from `transaction_id` | ✅ IAP views subclass `AppTierAPIView`; webhook views use a **new signature-only base** (no `X-App-Key`, no JWT) — do NOT touch `AdminTierAPIView`. No user record consulted. |
| III. Entitlement at Download Edge | Gate at `download-url`, presigned ≤5min, single object, non-enumerable key | ✅ Modifies the one gate (`apps/wallpapers/services.build_download_url`); reuses existing presign (300s, private bucket, UUID master_key). No bulk bypass. |
| IV. Structured Errors & Catalog | All errors via centralized handler using catalog codes | ✅ Codes already in `core/errors.py:34-39`; add missing `AppError` subclasses (`ReceiptInvalid`, `ReceiptConflict`, `StoreApiUnavailable`, `WebhookSignatureInvalid`). No ad-hoc error bodies. |
| V. Feature-First App Architecture | Logic in services; no cross-app internal imports; thin views | ✅ All IAP logic in `apps/iap/services` + store adapters; the wallpapers gate calls a **public** `apps.iap.services` entitlement function (no reaching into iap internals). |
| VI. Cursor Pagination & Envelopes | N/A — no new list endpoints | ✅ Not applicable (status is a single-object lookup). |
| VII. Async Media Pipeline Safety | Heavy work async | ✅ N/A to media; a single store lookup is lightweight I/O run inline with a timeout (research D6). No file handling. |
| VIII. Two-Flavor Config | Only dev/prod; secrets from env | ✅ New `IAP_APPLE_*` / `IAP_GOOGLE_*` env keys, base default="" + prod fail-fast; dev uses sandbox. No third flavor. |
| IX. Data Integrity & Migrations | Non-destructive migrations; IAP records store-authoritative | ✅ Additive migrations only; entitlement never overwritten by lower-trust source; idempotency/order guard (research D5). |
| X. Testing Discipline | Auth isolation, entitlement gate, verify + webhook signature tested; stores mocked | ✅ Test matrix in [quickstart.md](quickstart.md); update `core/tests/test_tier_isolation.py` for `/iap/*`. |
| XI. Code Quality & Dependency Hygiene | ruff clean; deps version-verified; no secret logging | ✅ Versions looked up on PyPI 2026-07-26 (research D8); pin in `base.in`, `uv pip compile`. Never log receipts/tokens/payloads. |

**Result**: PASS, no violations. Complexity Tracking table below intentionally empty.

## Project Structure

### Documentation (this feature)

```text
specs/BE-005-iap-verify-entitlement/
├── plan.md              # This file
├── research.md          # Phase 0 — approach + dependency decisions
├── data-model.md        # Phase 1 — SubscriptionEntitlement, StoreNotificationEvent
├── quickstart.md        # Phase 1 — end-to-end validation guide
├── contracts/
│   └── iap-contract-delta.md   # Phase 1 — v0.4.0→v0.5.0 contract delta (maps to .claude/openapi.yaml)
├── checklists/
│   └── requirements.md  # spec quality checklist (from /speckit-specify)
└── tasks.md             # Phase 2 — /speckit-tasks (NOT created here)
```

### Source Code (repository root)

```text
apps/iap/                         # populated in BE-005 (empty skeleton before)
├── apps.py                       # existing IapConfig
├── models.py                     # NEW — SubscriptionEntitlement, StoreNotificationEvent
├── serializers.py                # NEW — VerifyReceiptRequest, SubscriptionStatus (contract shapes)
├── views.py                      # NEW — VerifyReceiptView, SubscriptionStatusView (AppTierAPIView);
│                                 #        AppleWebhookView, GoogleWebhookView (signature-only base)
├── urls.py                       # NEW — /iap/verify-receipt, /iap/subscription-status,
│                                 #        /iap/webhook/apple, /iap/webhook/google
├── services.py                   # NEW — PUBLIC api: verify_receipt(), resolve_status(),
│                                 #        is_entitled(transaction_id), apply_notification()
├── stores/                       # NEW — boundary adapters (mocked in tests)
│   ├── apple.py                  #   App Store Server API + SignedDataVerifier
│   └── google.py                 #   Play Developer API subscriptionsv2 + Pub/Sub OIDC verify
└── migrations/0001_initial.py    # NEW — two tables

core/
├── errors.py                     # ADD AppError subclasses for the 4 IAP codes (codes already declared)
└── api.py                        # ADD a signature-only base view for webhooks (no auth tiers)

apps/wallpapers/
├── views.py                      # MODIFY WallpaperDownloadUrlView.get → read ?transaction_id
└── services.py                   # MODIFY build_download_url → call apps.iap.services.is_entitled

config/
├── urls.py                       # MODIFY — include apps.iap.urls BEFORE django-admin catch-all
└── settings/{base,dev,prod}.py   # ADD IAP_APPLE_* / IAP_GOOGLE_* env (2-flavor)

requirements/base.in (+ .txt)     # ADD app-store-server-library, google-api-python-client, google-auth

.claude/openapi.yaml, .claude/api-context.md   # BUMP v0.4.0 → v0.5.0 (then sync to livecanvas-mobile)

# tests (pytest-django) — colocated per app
apps/iap/tests/                   # NEW — verify (ios/android, invalid, conflict, store-down, idempotent),
                                  #        webhook (valid/invalid signature, renew/expire/refund, replay/order),
                                  #        status (found/unknown), entitlement resolution
apps/wallpapers/tests/test_download_url.py   # UPDATE — premium now unlocks with active txn; still 402 otherwise
core/tests/test_tier_isolation.py            # UPDATE — add /iap/* tier expectations
```

**Structure Decision**: Single Django web-service project; the feature is contained in the
existing `apps/iap` (populated) plus small, surgical edits to `apps/wallpapers` (the gate),
`core` (error classes + webhook base), `config` (urls + settings), and `requirements`. Store
integrations are isolated in `apps/iap/stores/*` so they can be mocked at the boundary and so
one provider's SDK never leaks into view/service logic (Constitution V).

## Cross-app boundary (entitlement gate)

`apps/wallpapers/services.build_download_url()` must NOT import `apps.iap` internals. It calls
a single **public** function `apps.iap.services.is_entitled(transaction_id: str) -> bool`
(Constitution V). The wallpapers view reads `transaction_id` from `request.query_params` and
passes it through. When `wallpaper.is_premium` and `not is_entitled(...)` → raise
`EntitlementRequired` (402); free wallpapers skip the call entirely (transaction_id ignored).

## Phased implementation shape (detail deferred to /speckit-tasks)

1. **Contract v0.5.0** — bump `.claude/openapi.yaml` + `api-context.md` (download-url premium
   gate now real; IAP endpoints live), sync to `livecanvas-mobile`. (Constitution I — before code.)
2. **Dependencies** — add 3 libs to `base.in`, `uv pip compile`, commit locks.
3. **Config** — `IAP_APPLE_*` / `IAP_GOOGLE_*` env across base/dev/prod + `.env.*.example`.
4. **Errors** — add 4 `AppError` subclasses in `core/errors.py`.
5. **Models + migration** — `SubscriptionEntitlement`, `StoreNotificationEvent`.
6. **Store adapters** — `stores/apple.py`, `stores/google.py` (boundary; mockable).
7. **Services** — public `verify_receipt`, `resolve_status`, `is_entitled`, `apply_notification`.
8. **Views + urls** — 2 app-tier + 2 signature-only webhook; mount before admin catch-all.
9. **Gate** — wire `apps/wallpapers` download-url to `apps.iap.services.is_entitled`.
10. **Tests** — per the matrix in [quickstart.md](quickstart.md); update tier-isolation + download-url tests.

## Complexity Tracking

No constitution violations — table intentionally empty.

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| — | — | — |

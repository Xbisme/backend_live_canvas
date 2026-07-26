# Contract Delta: v0.4.0 → v0.5.0 (BE-005 IAP)

The authoritative contract lives at `.claude/openapi.yaml` + `.claude/api-context.md`
(this repo has no `contracts/` dir — the mobile repo holds the mirrored copy). The IAP
endpoints and schemas were already **sketched as placeholders** in v0.4.0; BE-005 makes them
real and changes one behavior, so the version bumps to **v0.5.0**. After merge, both files are
copied verbatim to `livecanvas-mobile` (Constitution I — Contract Sync).

## What changes (behavioral, mostly no shape change)

### 1. `GET /wallpapers/{id}/download-url` — premium gate goes live (BREAKING behavior)

- **Before (v0.4.0)**: premium wallpaper → `402 ENTITLEMENT_REQUIRED` **unconditionally**.
- **After (v0.5.0)**: premium wallpaper requires `?transaction_id=<id>` resolving to an
  **entitled** subscription (`status ∈ {active, in_grace_period}` and not past `expires_at`):
  - entitled → `200` presigned `DownloadUrlResponse` (expiry ≤ 5 min), same shape as free.
  - missing/expired/not-entitled `transaction_id` → `402 ENTITLEMENT_REQUIRED`.
  - free wallpaper → `200` regardless of `transaction_id` (unchanged); `transaction_id` ignored.
  - `processing`/`failed`/deleted → `404` (unchanged, evaluated independently of entitlement).
- Request shape unchanged (`transaction_id` query param already documented as "required if premium").
- Update the endpoint `summary` in `openapi.yaml` (currently says "Premium → 402 vô điều kiện
  cho tới BE-005") and the matching `api-context.md` note.

### 2. IAP endpoints — activated (shapes already frozen, no change)

| Endpoint | Auth | Request | Success | Errors |
|---|---|---|---|---|
| `POST /iap/verify-receipt` | app-tier `X-App-Key` | `VerifyReceiptRequest` | `200 SubscriptionStatus` | `400 RECEIPT_INVALID`, `409 RECEIPT_CONFLICT`, `503 STORE_API_UNAVAILABLE`, `401 INVALID_APP_KEY` |
| `GET /iap/subscription-status` | app-tier `X-App-Key` | `?transaction_id=` (required) | `200 SubscriptionStatus` | `404 NOT_FOUND`, `401 INVALID_APP_KEY` |
| `POST /iap/webhook/apple` | signature-only (`security: []`) | `AppleServerNotification` (`signedPayload` JWS) | `200 {}` | `400 WEBHOOK_SIGNATURE_INVALID` |
| `POST /iap/webhook/google` | signature-only (`security: []`) | `GoogleRtdnNotification` (Pub/Sub) | `200 {}` | `400 WEBHOOK_SIGNATURE_INVALID` |

Schemas already present in `openapi.yaml`: `VerifyReceiptRequest`
(`platform` ios|android, `receipt_data`, `transaction_id`, `product_id`, `device_id`),
`SubscriptionStatus` (`transaction_id`, `product_id`, `status` enum
[active, expired, canceled, in_grace_period, refunded], `expires_at` nullable, `auto_renew`),
`AppleServerNotification`, `GoogleRtdnNotification`, `DownloadUrlResponse`, `ErrorResponse`.
**No schema field changes required** — reuse as-is.

### 3. Error codes — no new codes

All required codes already exist in the catalog (`api-context.md` Error Code Catalog +
`core/errors.py:34-39`): `ENTITLEMENT_REQUIRED` (402), `RECEIPT_INVALID` (400),
`RECEIPT_CONFLICT` (409), `STORE_API_UNAVAILABLE` (503), `WEBHOOK_SIGNATURE_INVALID` (400),
`NOT_FOUND` (404), `INVALID_APP_KEY` (401), `VALIDATION_ERROR` (400), `SERVER_ERROR` (500).
BE-005 only adds the **server-side exception classes** for four of them; the contract catalog
is unchanged.

## Version bump checklist (Constitution I)

- [ ] `openapi.yaml`: `info.version: "0.4.0"` → `"0.5.0"`; update `download-url` summary; update
      top-of-file description note.
- [ ] `api-context.md`: header `Contract version: v0.5.0`; add a "Đổi so với v0.4.0" note
      (download-url premium gate live; IAP endpoints active; no new error code); update the
      `download-url` and IAP endpoint sections to drop "gate mở ở BE-005 / 402 vô điều kiện".
- [ ] Copy both files verbatim to `livecanvas-mobile` (`.claude/` + its `contracts/`), note the
      sync in the mobile changelog. Mobile needs the real endpoints for MO-005.

## Clarification-driven semantics baked into the contract prose

- Entitlement is keyed by the store **original/linking transaction id**; any `transaction_id`
  in a subscription's renewal chain resolves to the same entitlement (so status/download work
  after renewals). — note in `api-context.md` IAP section.
- `in_grace_period` **counts as entitled** at the download gate. — note beside the status enum.
- `device_id` is recorded for abuse signals only; restore across devices is supported;
  `RECEIPT_CONFLICT` is a cross-subscription identity mismatch, not a device difference.

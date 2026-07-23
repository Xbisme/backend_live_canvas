# Data Model: BE-002 Backend Foundation

**No database models are introduced in BE-002.** `makemigrations --check` MUST stay clean. The
"entities" below are runtime/config constructs and cross-cutting request-handling contracts, not
persisted tables. Business models (`Category`, `Tag`, `Wallpaper`, `Collection`, …) arrive in BE-003+.

---

## 1. Error-Code Catalog (`core/errors.py`)

Mirror of the catalog in `.claude/api-context.md` as Python constants — the single in-code source
consumed by the exception handler. **BE-002 adds `SERVER_ERROR` and `METHOD_NOT_ALLOWED`** (see
research R7; contract patch v0.3.1).

| Constant | `code` string | HTTP | Raised by (BE-002 scope) |
|---|---|---|---|
| `INVALID_APP_KEY` | `INVALID_APP_KEY` | 401 | app-tier auth (missing/wrong `X-App-Key`) |
| `VALIDATION_ERROR` | `VALIDATION_ERROR` | 400 | DRF `ValidationError`/`ParseError`, invalid cursor |
| `NOT_FOUND` | `NOT_FOUND` | 404 | `Http404`/DRF `NotFound` |
| `METHOD_NOT_ALLOWED` | `METHOD_NOT_ALLOWED` | 405 | DRF `MethodNotAllowed` **(new)** |
| `SERVER_ERROR` | `SERVER_ERROR` | 500 | any unhandled exception **(new)** |

> The remaining catalog codes (`ENTITLEMENT_REQUIRED`, `RECEIPT_*`, `TAG_*`, `WALLPAPER_NOT_FOUND`,
> `COLLECTION_SLUG_CONFLICT`, `UNAUTHORIZED_ADMIN`, `FORBIDDEN_ADMIN_ROLE`, `FILE_REJECTED`,
> `STORE_API_UNAVAILABLE`, `WEBHOOK_SIGNATURE_INVALID`, `TAG_IN_USE`) are defined as constants too
> (full mirror) but are **not raised** by any BE-002 code path — they belong to later specs.

**Custom exception types**:
- `AppError(APIException)` — base carrying `code`, `status_code`, `default_detail`. Subclasses set
  the three. Serialized by the handler into the envelope.
- `InvalidAppKey(AppError)` → `code="INVALID_APP_KEY"`, `status_code=401`.

**Validation rules**: `code` values are immutable string enums; HTTP status and code MUST agree
(Principle IV). Adding/removing a code is a contract change (Principle I).

---

## 2. Error Envelope (response contract)

The single permitted error shape, produced only by the centralized handler:

```json
{ "error": { "code": "<CODE>", "message": "<human-readable, non-sensitive>" } }
```

**Rules**: exactly one top-level `error` object; `code` ∈ catalog; `message` never contains a stack
trace, SQL, secret, `X-App-Key`, or PII. Applies in both flavors (identical body under
`DEBUG=True`/`False`).

---

## 3. Pagination Envelope (response contract)

Emitted by `EnvelopeCursorPagination.get_paginated_response()`:

```json
{ "items": [ /* serialized objects */ ], "next_cursor": "<opaque-string|null>", "has_more": true }
```

**Rules**: `limit` query param default 20, max 100 (over-max → `VALIDATION_ERROR`); `cursor` is an
opaque keyset token; `next_cursor: null` ⇔ `has_more: false` ⇔ end of data. No `page`/offset params.
Exercised for real once list endpoints exist (BE-003).

---

## 4. App-Tier Credential (runtime, not persisted)

- **`X-App-Key`**: single shared opaque secret, configured via env `X_APP_KEY` (declared in BE-001).
  Validated by constant-time exact match. Presence + correctness is the sole app-tier auth factor.
- **`AppPrincipal`** (transient): non-`User` sentinel returned by `AppKeyAuthentication` on success so
  `request.user.is_authenticated` is truthy for the permission — represents the *app*, never a person
  or account (Principle II, account-less).

**State/transitions**: none — stateless per request. No DB row, no session.

---

## 5. Storage / CDN Configuration (settings, not persisted)

| Setting / env | Flavor behavior |
|---|---|
| `STORAGES["default"]` | dev → `FileSystemStorage` fallback (or MinIO if `AWS_S3_ENDPOINT_URL` set); prod → `S3Storage` |
| `AWS_STORAGE_BUCKET_NAME` | dev optional; **prod required (no default)** |
| `AWS_S3_ENDPOINT_URL` | dev optional (MinIO); prod set for non-AWS providers (R2/Spaces) |
| `AWS_S3_REGION_NAME` | provider-dependent |
| `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` | dev optional; **prod required** |
| `CDN_BASE_URL` | dev → local media URL default; **prod required (no default)** |

**Rules**: prod fails fast (`ImproperlyConfigured`) if any required value is missing (FR-011); dev
degrades to local fallback (FR-010). No bucket is created/written in BE-002 (config only).

---

## 6. Feature Apps (code structure, no models)

| App | `AppConfig.name` | Models in BE-002 | Fills in |
|---|---|---|---|
| `apps.wallpapers` | `apps.wallpapers` | none | BE-003 (Category/Tag/Wallpaper/Collection) |
| `apps.uploads` | `apps.uploads` | none | BE-004 (upload/presign/transcode) |
| `apps.iap` | `apps.iap` | none | BE-005 (verify-receipt/webhooks/entitlement) |

**Rules**: registered in `INSTALLED_APPS`; importable; produce **zero** migrations; no cross-app
imports (Principle V).

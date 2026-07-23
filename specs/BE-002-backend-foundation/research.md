# Research & Decisions: BE-002 Backend Foundation

Phase 0 output. Resolves the technical unknowns behind the plan. Each item: **Decision /
Rationale / Alternatives considered**.

---

## R1 — Cursor pagination class (contract envelope vs DRF default)

**Decision**: Add `core/pagination.py::EnvelopeCursorPagination`, subclassing DRF
`rest_framework.pagination.CursorPagination`, overriding `get_paginated_response()` to emit
`{ "items": [...], "next_cursor": <str|null>, "has_more": <bool> }`. Set `page_size = 20`,
`max_page_size = 100`, `page_size_query_param = "limit"`, `cursor_query_param = "cursor"`,
`ordering = "-created_at"` as the class default (per-view overridable when models arrive). Register
as `REST_FRAMEWORK["DEFAULT_PAGINATION_CLASS"]`. An invalid/expired cursor raises DRF `NotFound`
by default — the exception handler (R4) remaps cursor-decode failures to `VALIDATION_ERROR` (400),
satisfying Constitution VI.

**Rationale**: DRF's built-in `CursorPagination` gives keyset (opaque cursor) semantics the contract
requires, but its default body is `{next, previous, results}` with absolute URLs — wrong shape and it
leaks the host. Overriding only the response builder keeps DRF's proven cursor encode/decode while
matching the frozen envelope. `has_more` = "a next cursor exists".

**Alternatives considered**: (a) `LimitOffsetPagination`/`PageNumberPagination` — FORBIDDEN by
Principle VI (offset degrades and double-serves under insert/shift). (b) Hand-rolled keyset cursor —
re-implements encode/decode DRF already ships; rejected as needless risk. (c) drf-cursor-style third
party lib — unnecessary dependency for a 20-line override.

**Note**: `ordering` needs a real field; with no models in BE-002 the class is wired but only
exercised for its config/response-shape in tests (a throwaway in-memory queryset or settings
assertion). Real list behavior lands with `Wallpaper` in BE-003.

---

## R2 — App-tier `X-App-Key`: DRF authentication class, NOT global middleware

**Decision**: Implement app-tier auth as a **DRF `BaseAuthentication` subclass**
`core/authentication.py::AppKeyAuthentication` plus a marker permission
`core/permissions.py::IsAppAuthenticated`, exposed through a base view
`core/api.py::AppTierAPIView` (sets `authentication_classes = [AppKeyAuthentication]`,
`permission_classes = [IsAppAuthenticated]`). Public + IAP views in BE-003/BE-005 subclass it.
`AppKeyAuthentication.authenticate()` reads `HTTP_X_APP_KEY`; if absent **or** mismatched it raises
`core.errors.InvalidAppKey` (401, code `INVALID_APP_KEY`); on match it returns
`(AppPrincipal(), None)` — a lightweight sentinel principal (NOT a Django `User`) so
`request.user.is_authenticated` is true for the permission without implying an account.

**Rationale**: Making it a DRF class (opt-in per view via the base class) — rather than global
middleware or a global `DEFAULT_AUTHENTICATION_CLASSES` — is what guarantees Principle II isolation:
the admin tier (BE-004) simply uses a *different* base class, and health/admin routes never carry the
app-key auth at all. Raising in **both** the missing and mismatched cases yields one consistent
`INVALID_APP_KEY` and prevents an information-leaking distinction (spec edge case). Comparison uses
`hmac.compare_digest` (constant-time) to avoid timing oracles.

**Alternatives considered**: (a) A process-wide middleware gating every request — would have to
special-case `/health` and `/admin/`, and risks accidentally coupling tiers; contradicts "never share
middleware between tiers." (b) Global `DEFAULT_AUTHENTICATION_CLASSES = [AppKeyAuthentication]` — would
force the app key onto future admin endpoints too; rejected. (c) A DRF **permission-only** approach —
a failed permission returns 403, but the catalog demands 401 `INVALID_APP_KEY`; authentication is the
correct DRF layer for a 401.

**Fail-closed on misconfiguration**: an empty/unset `settings.X_APP_KEY` MUST NOT authenticate anyone
(no `compare_digest("", "")` bypass) — the auth denies all requests, and `prod` reads `X_APP_KEY` with
no default so it fails fast at startup (FR-021), mirroring the storage/DB fail-fast discipline. `dev`
keeps a known default key for ergonomics.

**Isolation test**: a request bearing only `Authorization: Bearer x` (no valid `X-App-Key`) against an
app-tier view MUST still 401 `INVALID_APP_KEY` — asserted in `test_app_key_auth.py`, alongside the
empty-configured-key denial and the assertion that `/health*` remains reachable without a key.

---

## R3 — Object storage: `django-storages[s3]` version + per-flavor backend

**Decision**: Add `django-storages[s3]==1.14.6` to `requirements/base.in` (pulls `boto3` — locked
transitively by `uv pip compile`; observed latest boto3 1.43.54). Configure via Django's
`STORAGES` setting (Django ≥4.2 / 5.2 native; django-storages 1.14 supports it):
- **base.py**: declare the storage env catalog (`AWS_STORAGE_BUCKET_NAME`, `AWS_S3_ENDPOINT_URL`,
  `AWS_S3_REGION_NAME`, `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `CDN_BASE_URL`) with sane
  declared-but-unset defaults; keep `STATIC` on whitenoise (BE-001) unchanged.
- **dev.py**: `default` storage → `FileSystemStorage` local fallback when S3 creds absent (FR-010);
  optional MinIO by pointing `AWS_S3_ENDPOINT_URL` at `http://localhost:9000` when the dev wants it.
  `CDN_BASE_URL` defaults to the local media URL.
- **prod.py**: `default` storage → `storages.backends.s3.S3Storage`; `AWS_STORAGE_BUCKET_NAME`,
  `CDN_BASE_URL` (and credentials/region/endpoint as required) read with **no default** → fail-fast
  via `env()`/`ImproperlyConfigured` (FR-011), consistent with BE-001 prod discipline.

**Rationale**: `django-storages` is the standard S3 abstraction and is provider-agnostic
(AWS S3 / Cloudflare R2 / DO Spaces differ only by `endpoint_url`/`region`) — matching the
still-open provider decision in project-context without committing code to one vendor. Verified on
PyPI 2026-07-23 per Constitution XI. **No bucket is created or written** in BE-002 — configuration
only; the first real PUT/presign is BE-004.

**Alternatives considered**: (a) Raw `boto3` client wiring — reinvents django-storages' Django
integration; rejected. (b) Committing to a specific provider now — premature; the product decision is
still open (project-context "Chưa quyết định"). (c) Deferring all storage config to BE-004 — the spec
explicitly scopes per-flavor storage *config* to BE-002 so BE-004 builds on a settled substrate.

---

## R4 — Centralized exception handler & the `core.errors` catalog module

**Decision**: `core/errors.py` defines an `ErrorCode` catalog (string constants mirroring
`.claude/api-context.md`) and custom exceptions (`InvalidAppKey`, plus a small `AppError` base that
carries `(code, http_status, default_message)`). `core/exception_handler.py::structured_exception_handler`
wraps DRF's `exception_handler`:
1. Call DRF's default handler first.
2. Map the exception to a catalog `code`: `Http404`/`NotFound` → `NOT_FOUND` (404);
   `ValidationError`/`ParseError` → `VALIDATION_ERROR` (400); `InvalidAppKey`/`NotAuthenticated`/
   `AuthenticationFailed` on the app tier → `INVALID_APP_KEY` (401); `MethodNotAllowed` →
   `METHOD_NOT_ALLOWED` (405); any `AppError` subclass → its own `code`.
3. If DRF returns `None` (unhandled, non-DRF exception) → log the full exception server-side
   (`logger.exception`, no client leakage) and return `SERVER_ERROR` (500).
4. Always render `{ "error": { "code": <CODE>, "message": <safe text> } }`.
Register as `REST_FRAMEWORK["EXCEPTION_HANDLER"]`.

**Rationale**: One handler = one audit point (Principle IV). Delegating to DRF's default first keeps
correct status codes and header handling (e.g. `Allow` on 405), then we normalize the *body*.
Unhandled exceptions never expose a traceback — critical under prod `DEBUG=False` and equally enforced
in dev so tests catch leaks early.

**Alternatives considered**: (a) Per-view try/except with `Response({...})` — FORBIDDEN by Principle
IV. (b) Custom DRF renderer — renderers shape success bodies too; the exception handler is the precise
hook for errors. (c) DRF `settings.DEFAULT_EXCEPTION_REPORTER` — reporter is for the debug 500 page,
not the API body.

---

## R5 — Feature-app layout: `apps/` namespace, model-less shells

**Decision**: Create `apps/__init__.py` (namespace) and three apps
`apps/wallpapers`, `apps/uploads`, `apps/iap`, each with `__init__.py`, `apps.py`
(`class WallpapersConfig(AppConfig): name = "apps.wallpapers"; default_auto_field = "...BigAutoField"`),
and an empty `migrations/` package. Register all three in `INSTALLED_APPS` via their dotted
`AppConfig` path. No `models.py` content (no business models). `makemigrations --check --dry-run`
must report nothing.

**Rationale**: Establishes the Principle V app boundaries now so BE-003 (`Category/Tag/Wallpaper/
Collection` in `apps/wallpapers`), BE-004 (`apps/uploads`), and BE-005 (`apps/iap`) drop models in
without moving files or editing `INSTALLED_APPS` again. `default_auto_field` set explicitly avoids the
`makemigrations` auto-field warning later.

**Alternatives considered**: (a) Flat top-level apps (no `apps/` package) — the constitution and
project-context both specify `apps/<domain>`; rejected. (b) Deferring app creation to each feature
spec — re-scaffolds settings repeatedly and muddies the "foundation is complete" boundary.

---

## R6 — Validating US1/US2 without business endpoints (the probe route)

**Decision**: Add a minimal temporary **app-tier probe view** in `core/views.py` mounted at an
internal path (e.g. `/_probe/app-tier` under `core.urls`), subclassing `AppTierAPIView`, returning
`200 {"ok": true}` on success. Tests hit it to exercise the app-key gate (US1) and to raise sample
errors (a probe that 404s / raises `ValidationError` / raises an unhandled error) for the envelope
(US2). The route is clearly marked temporary foundation scaffolding, excluded from the product
contract, and slated for removal once BE-003 supplies real app-tier endpoints.

**Rationale**: US1 and US2 are the two P1 slices and must be independently testable *now*, but no
product endpoint exists yet. A throwaway probe is the smallest honest way to prove the cross-cutting
machinery end-to-end. Alternative — asserting only settings wiring without an HTTP round-trip — would
not prove the 401/envelope behavior the acceptance scenarios demand.

**Alternatives considered**: (a) Test via DRF `APIRequestFactory` against the classes directly, no
route — lighter but skips URLconf/handler integration; we do BOTH (unit + one integration probe).
(b) Leave US1/US2 untested until BE-003 — violates independent-testability and Principle X.

---

## R7 — Two new foundation error codes → contract patch bump v0.3.1

**Decision**: The handler must emit a code for two classes the current catalog (v0.3.0) does not
cover: unhandled 500s and 405s. Add **`SERVER_ERROR` (500)** and **`METHOD_NOT_ALLOWED` (405)** to the
Error-Code Catalog. Because error codes are part of the contract (Principle I/IV), this is a **patch
bump v0.3.0 → v0.3.1**: update `.claude/api-context.md` (catalog table + changelog header) and
`contracts/openapi.yaml` together, then **copy both verbatim into `livecanvas-mobile`** and note the
sync. `ParseError` maps to the existing `VALIDATION_ERROR` (no new code). Throttling (`429`) is
deferred to BE-006, so no `THROTTLED` code is added now.

**Rationale**: FR-018 requires a generic server-error code; leaving 500/405 bodies code-less would
break the "every error has a catalog code" invariant the mobile client relies on. A patch bump is the
minimal, honest contract change; adding only the two foundation-level codes avoids speculative entries.

**Alternatives considered**: (a) Reuse an existing code for 500 — none fits; misusing `VALIDATION_ERROR`
for a server fault would mislead the client. (b) Emit an off-catalog code — violates Principle IV. (c)
Skip the contract sync — violates Principle I (dual-repo lockstep).

**Open handoff**: the `livecanvas-mobile` repo is not in this workspace; the verbatim copy of the two
contract files is flagged as a required cross-repo action for the user at sync time (per
`dev-workflow.md` Contract Sync). BE-002 server code and the backend copy of the contract stay in
lockstep regardless.

---

## Resolved unknowns summary

| Unknown | Resolution |
|---|---|
| Pagination shape vs DRF default | R1 — custom `EnvelopeCursorPagination` |
| App-key as middleware vs DRF class | R2 — DRF auth class, opt-in per tier |
| Storage lib + version + per-flavor backend | R3 — `django-storages[s3]==1.14.6`, S3 in prod / FS fallback in dev |
| Error handler design + catalog module | R4 — `core.errors` + wrapped DRF handler |
| App package layout | R5 — `apps/{wallpapers,uploads,iap}` model-less |
| How to test US1/US2 with no endpoints | R6 — temporary app-tier probe route |
| Missing 500/405 catalog codes | R7 — add `SERVER_ERROR`/`METHOD_NOT_ALLOWED`, contract v0.3.1 + mobile sync |

# Feature Specification: Backend Foundation (DRF + App Layer + Infra Config)

**Feature Branch**: `BE-002-backend-foundation`

**Created**: 2026-07-23

**Status**: Draft

**Input**: User description: "BE-002 Backend Foundation — DRF skeleton + app layer + infra
config, chưa có model/endpoint nghiệp vụ. Cấu hình DRF (cursor pagination, response envelope),
3 app rỗng feature-first (wallpapers/uploads/iap), wiring PostgreSQL 2 flavor, django-storages
S3+CDN config theo flavor, middleware/authentication X-App-Key cho tầng public+IAP, centralized
DRF exception handler trả `{ error: { code, message } }`. Ngoài scope: model/endpoint nghiệp vụ
(BE-003+), Celery/Redis (BE-004), IAP verify thật (BE-005), admin JWT thật (BE-004)."

## Overview

BE-002 turns the bare Django skeleton delivered in BE-001 into an **API-serving foundation**:
the REST framework is wired with the project-wide response and pagination conventions, the three
feature apps exist as empty (model-less) shells ready for BE-003+, both flavors persist to
PostgreSQL, object storage + CDN are configured per flavor, and the two cross-cutting runtime
contracts from the constitution — the **app-tier `X-App-Key` boundary** and the **structured
error envelope** — are enforced centrally so every later endpoint inherits them for free.

No business models or product endpoints ship here. The value is a correct, demonstrable
*substrate*: a request that reaches the API is authenticated at the app tier or rejected with a
catalog error, any failure returns the structured envelope (never a traceback), and both flavors
boot against real infrastructure configuration.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - App-tier requests are gated by `X-App-Key` (Priority: P1)

The mobile app (not an end user — there is no account system) calls a public/IAP-tier endpoint.
The backend must accept the request only when a valid `X-App-Key` is presented, and otherwise
reject it with the catalog error `INVALID_APP_KEY` (HTTP 401) in the structured envelope. This is
the security boundary every public and IAP endpoint in BE-003/BE-005 will sit behind, so it must
exist and be provably isolated from the (future) admin tier before any business endpoint is built.

**Why this priority**: The two-tier auth isolation is a non-negotiable constitution principle and
the single most security-sensitive piece of the foundation. Getting it wrong (or letting it fall
back to another tier) would compromise every downstream endpoint. It is also independently
demonstrable using a throwaway probe endpoint, with no business logic required.

**Independent Test**: Mount a temporary app-tier probe view; call it with no `X-App-Key` → 401
`INVALID_APP_KEY`; with a wrong key → 401 `INVALID_APP_KEY`; with the configured key → 200. Confirm
the admin Bearer scheme is **not** accepted on this tier and vice-versa.

**Acceptance Scenarios**:

1. **Given** an app-tier endpoint, **When** a request arrives with no `X-App-Key` header, **Then**
   the response is HTTP 401 with body `{ "error": { "code": "INVALID_APP_KEY", "message": "..." } }`.
2. **Given** an app-tier endpoint, **When** a request arrives with an `X-App-Key` that does not
   match the configured value, **Then** the response is HTTP 401 `INVALID_APP_KEY`.
3. **Given** an app-tier endpoint, **When** a request arrives with the correct `X-App-Key`, **Then**
   the request is authenticated and passes to the view (probe returns 200).
4. **Given** an app-tier endpoint, **When** a request presents only an `Authorization: Bearer`
   token and no valid `X-App-Key`, **Then** it is still rejected `INVALID_APP_KEY` (no cross-tier
   fallback).
5. **Given** the configured `X-App-Key`, **When** an authentication failure is logged, **Then** the
   key value itself is never written to logs.

---

### User Story 2 - Every error is a structured catalog envelope (Priority: P1)

Any error raised anywhere in the API — validation failure, not-found, auth failure, or an
unexpected server exception — is returned to the client as
`{ "error": { "code": "<CODE>", "message": "..." } }` with `code` drawn from the error-code catalog
in `.claude/api-context.md`. Raw DRF error shapes, stack traces, and ad-hoc bodies never reach a
client. Every later endpoint relies on this handler rather than formatting errors itself.

**Why this priority**: The structured-error contract is a constitution principle and part of the
API's public contract with the mobile repo. It must be centralized before business endpoints exist,
otherwise each endpoint invents its own error shape and the contract fragments.

**Independent Test**: Trigger each error class through probe/throwaway routes — a 404, a validation
error, an unhandled exception, an app-key failure — and assert each response body matches the
envelope with the correct catalog `code` and the correct HTTP status; assert no traceback text
appears in any response, including in the `prod` flavor with `DEBUG=False`.

**Acceptance Scenarios**:

1. **Given** any API route, **When** the resource does not exist, **Then** the response is HTTP 404
   with `code` `NOT_FOUND`.
2. **Given** any API route, **When** request data fails validation, **Then** the response is HTTP
   400 with `code` `VALIDATION_ERROR`.
3. **Given** any API route, **When** an unhandled exception is raised in a view, **Then** the client
   receives the structured envelope with a generic server-error `code` and message — never a stack
   trace or Django debug page — under both flavors.
4. **Given** the app-key failure from User Story 1, **When** it is rendered, **Then** it uses the
   same envelope and the `INVALID_APP_KEY` code (the two contracts compose).

---

### User Story 3 - REST framework + feature-app skeleton is in place (Priority: P2)

The REST framework is installed and configured with the project-wide defaults — cursor-based
pagination as the default list style (default page size 20, max 100) and a consistent response
convention — and the three feature apps `apps/wallpapers`, `apps/uploads`, `apps/iap` exist as
registered, model-less shells so BE-003+ can add models and endpoints without re-scaffolding.

**Why this priority**: Necessary substrate but not itself a security boundary; it enables
subsequent specs rather than delivering an externally observable behavior on its own. Depends on
nothing from US1/US2 and can be built in parallel.

**Independent Test**: The three apps import and are listed as installed; `makemigrations --check`
reports no missing migrations (empty apps produce none); the configured default pagination and
exception-handler wiring are asserted by inspecting the running framework configuration; both
flavors boot with the framework loaded.

**Acceptance Scenarios**:

1. **Given** the project, **When** it starts, **Then** `apps/wallpapers`, `apps/uploads`, `apps/iap`
   are all registered and import without error, each with **no** business models.
2. **Given** the framework configuration, **When** a list endpoint is added later, **Then** it
   inherits cursor pagination (default limit 20, max 100) without per-view configuration.
3. **Given** the framework configuration, **When** any error is raised, **Then** it is routed to the
   centralized handler from User Story 2 (single global wiring, not per-view).
4. **Given** the repository, **When** `makemigrations --check --dry-run` runs, **Then** it reports no
   uncommitted migration changes.

---

### User Story 4 - Object storage & CDN are configured per flavor (Priority: P3)

Object storage (S3-compatible) and a CDN base URL are configured through environment per flavor:
`dev` uses a local/optional MinIO-style target (or a safe local fallback) and `prod` reads real
S3 + CDN settings from the environment and fails fast if required values are missing. Only
configuration lands here — no upload, presign, or media-processing logic (that is BE-004).

**Why this priority**: Required before the upload pipeline (BE-004) but produces no user-facing
behavior in this spec; lowest risk and can land last.

**Independent Test**: With storage env vars set, both flavors boot and expose a resolvable storage
backend + CDN base URL; on `prod`, unsetting a required storage variable causes a fail-fast startup
error (consistent with BE-001's prod config discipline); no bucket write is attempted.

**Acceptance Scenarios**:

1. **Given** the `dev` flavor, **When** it boots without external storage credentials, **Then** it
   uses the documented local fallback and does not crash.
2. **Given** the `prod` flavor with all required storage variables set, **When** it boots, **Then**
   the storage backend and CDN base URL resolve from the environment.
3. **Given** the `prod` flavor with a required storage variable missing, **When** it boots, **Then**
   startup fails fast with a clear configuration error (no silent insecure default).

---

### Edge Cases

- **Empty vs malformed `X-App-Key`**: both an absent header and a present-but-wrong value resolve to
  the same `INVALID_APP_KEY` 401 (no information leak distinguishing the two).
- **Empty *configured* key (misconfiguration)**: if the server's `X_APP_KEY` is unset/empty, the app
  tier MUST deny all requests (never treat an empty presented key as a match); `prod` MUST refuse to
  boot in this state (fail-fast), so a deploy can never silently disable the app-tier gate.
- **Unhandled exception under `prod`**: with `DEBUG=False` the client still receives the structured
  envelope (generic server-error code), and the full exception is logged server-side only.
- **Error raised at the auth layer** (before a view runs): the app-key rejection must still render as
  the structured envelope, not a bare framework 401/403.
- **Health endpoints** (`/health`, `/health/ready` from BE-001) are operational, **not** part of the
  product contract, and therefore are **not** placed behind the `X-App-Key` gate.
- **Django built-in admin** (`/admin/`, session auth) is a separate internal-staff tier and is
  neither app-tier nor DRF-admin-API; it must not be affected by the `X-App-Key` gate.
- **Storage misconfiguration on `dev`** should degrade to the local fallback rather than fail the
  developer's boot.

## Requirements *(mandatory)*

### Functional Requirements

**REST framework & conventions**

- **FR-001**: The system MUST install and configure the REST framework so that list endpoints
  default to cursor-based pagination with a default page size of 20 and a hard maximum of 100,
  matching the contract's Cursor Pagination convention.
- **FR-002**: The system MUST apply pagination and error handling as **global framework defaults**,
  so future endpoints inherit them without per-view configuration.
- **FR-003**: The system MUST NOT expose offset/`page`-number pagination on any list surface.

**Feature-app skeleton**

- **FR-004**: The system MUST provide three registered, feature-first application shells —
  `apps/wallpapers`, `apps/uploads`, `apps/iap` — each importable and containing **no** business
  models in this spec.
- **FR-005**: The system MUST produce no missing migrations (`makemigrations --check` clean) with
  the empty apps registered.

**PostgreSQL wiring**

- **FR-006**: The system MUST persist to PostgreSQL in **both** flavors — `dev` pointing at the local
  containerized Postgres and `prod` reading a managed `DATABASE_URL` from the environment (no default).
- **FR-007**: The system MUST run contrib + app migrations cleanly against PostgreSQL in the `dev`
  flavor.

**Object storage & CDN configuration**

- **FR-008**: The system MUST configure an S3-compatible object-storage backend via environment,
  per flavor, without performing any upload/presign/media logic (deferred to BE-004).
- **FR-009**: The system MUST expose a CDN base URL resolved from the environment per flavor.
- **FR-010**: On the `dev` flavor, the system MUST boot using a documented local storage fallback
  when external storage credentials are absent.
- **FR-011**: On the `prod` flavor, the system MUST fail fast at startup if a required storage or CDN
  configuration value is missing (no silent insecure default).

**App-tier authentication (`X-App-Key`)**

- **FR-012**: The system MUST authenticate app-tier (public + IAP) requests by validating an
  `X-App-Key` header against the configured key.
- **FR-013**: The system MUST reject app-tier requests with a missing or incorrect `X-App-Key` using
  HTTP 401 and catalog code `INVALID_APP_KEY`.
- **FR-014**: The system MUST keep the app tier and the (future) admin Bearer tier strictly isolated:
  a valid credential of one tier MUST NOT authenticate the other, and there MUST be no fallback
  between tiers.
- **FR-015**: The system MUST NOT place the operational health endpoints or the Django built-in
  internal-staff admin behind the `X-App-Key` gate.
- **FR-016**: The system MUST NOT log the `X-App-Key` value (or any secret) on success or failure.
- **FR-021**: The system MUST treat an empty/unset configured app key as a **misconfiguration, not an
  open door**: when no app key is configured, the app tier MUST deny every request (never
  authenticate), and the `prod` flavor MUST fail fast at startup if `X_APP_KEY` is unset/empty — the
  same fail-fast discipline applied to required storage/database config. `dev` MAY run with a default
  dev key for local ergonomics but MUST NOT authenticate a request whose presented key is empty.

**Structured error envelope**

- **FR-017**: The system MUST return every API error as
  `{ "error": { "code": "<CODE>", "message": "..." } }` with `code` taken from the error-code catalog
  in `.claude/api-context.md`, produced by a single centralized handler.
- **FR-018**: The system MUST map standard error classes to catalog codes and correct HTTP statuses
  — at minimum `NOT_FOUND` (404), `VALIDATION_ERROR` (400), `INVALID_APP_KEY` (401), and a generic
  server-error code for unhandled exceptions (500).
- **FR-019**: The system MUST NOT return stack traces, Django debug pages, or ad-hoc/raw error bodies
  to clients in either flavor; unexpected exceptions MUST be logged server-side only.
- **FR-020**: The system MUST keep the two-flavor discipline intact — no third settings flavor is
  introduced by any storage, database, or framework configuration added here.

### Key Entities

*No business/domain entities are introduced in BE-002.* The only new "entities" are runtime
configuration and cross-cutting request-handling contracts:

- **App-tier credential**: the single configured `X-App-Key` value that authenticates the *app*
  (not a user); presence/correctness is the sole app-tier authentication factor.
- **Error envelope**: the canonical error response shape `{ error: { code, message } }` with `code`
  bound to the catalog; the unit of the API's error contract with the mobile repo.
- **Storage/CDN configuration**: per-flavor object-storage target and CDN base URL, sourced from the
  environment.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% of app-tier requests without a valid `X-App-Key` are rejected with HTTP 401
  `INVALID_APP_KEY`; 100% of requests with the valid key pass authentication.
- **SC-002**: 0 cross-tier authentications — no admin-tier credential authenticates an app-tier
  request, verified by test. (The reverse — an app key failing against an admin endpoint — cannot be
  fully asserted until the admin tier exists in BE-004; BE-002 tests the app-tier side and documents
  the deferred half.)
- **SC-003**: 100% of error responses across all exercised error classes match the structured
  envelope with a valid catalog `code`; 0 responses contain a stack trace or debug page, including
  under `prod` (`DEBUG=False`).
- **SC-004**: Both flavors boot to a serving state with the framework loaded; `dev` migrates and
  serves against local PostgreSQL, and `prod` passes `check --deploy` with the added configuration.
- **SC-005**: The three feature apps are registered and model-less, and `makemigrations --check`
  reports no changes.
- **SC-006**: The `config.settings` package still contains exactly `base`, `dev`, `prod` (+
  `__init__`) — no third flavor introduced (flavor-audit test stays green).
- **SC-007**: `prod` fails fast when a required storage/CDN or database variable **or `X_APP_KEY`** is
  missing/empty; `dev` boots on its local fallback when storage credentials are absent. In no flavor
  does an empty configured app key authenticate a request.
- **SC-008**: `ruff check`, `ruff format --check`, and the test suite pass on the branch.

## Assumptions

- **Single shared app key** authenticates the app tier for BE-002 (one configured `X_APP_KEY`
  value); multi-key rotation/registry is out of scope and can arrive in a later hardening spec
  (BE-006) if needed. This key is **required (non-empty) in `prod`** (fail-fast) and defaults to a
  known dev value in `dev`; an empty configured key never authenticates (FR-021).
- **`X-App-Key` is validated by exact match** against the configured value; it is an opaque shared
  secret, not a signed/derived token (webhooks — signature-verified — are BE-005 and out of scope).
- **Admin Bearer JWT is only declared/isolated, not implemented** here; the real admin auth lands in
  BE-004. BE-002 only guarantees the app tier does not accept or fall back to it.
- **Object storage is configured, not exercised** — no bucket is created or written to in this spec;
  the first real upload path is BE-004. The chosen S3-compatible provider for `prod` is still an open
  product decision (per project-context); configuration is provider-agnostic via environment.
- **The error-code catalog in `.claude/api-context.md` is the source of truth** for `code` values;
  BE-002 wires the handler to it and uses the subset relevant to foundation-level errors.
- **Contract-sync is not triggered by BE-002**: health endpoints and internal foundation wiring are
  not part of the product contract, so no `openapi.yaml` copy to the mobile repo is required by this
  spec (the app-tier auth header is already documented in the frozen contract).
- **Reuses BE-001 configuration discipline** — `django-environ`, `.env.dev`/`.env.prod`, two-flavor
  selection, and prod fail-fast behavior are extended, not replaced.

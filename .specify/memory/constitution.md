<!--
================================================================================
SYNC IMPACT REPORT
================================================================================
Version Change: (template) → 1.0.0 (initial ratification)

This is the first concrete constitution for the LiveCanvas Backend, replacing
the unfilled speckit template. All placeholder tokens have been resolved.

Principles defined (11):
  I.    Contract-First & Dual-Repo Contract Sync
  II.   Two-Tier Auth Isolation & Account-Less Entitlement
  III.  Entitlement Enforced at the Download Edge
  IV.   Structured Errors & Error-Code Catalog
  V.    Feature-First Django App Architecture
  VI.   Cursor Pagination & Consistent Response Envelopes
  VII.  Async Media Pipeline Safety
  VIII. Two-Flavor Configuration (dev + prod only)
  IX.   Data Integrity, Migrations & Curated Referential Integrity
  X.    Testing Discipline
  XI.   Code Quality, Security Hygiene & Dependency Management

Sections added:
  - Technical Standards (Platform & Stack, Core Domains, Data & Storage)
  - Development Workflow (SDD flow, Contract Sync, Pre-Commit, Gates, Review)
  - Governance (amendment process, versioning, compliance, communication)

Templates Requiring Updates:
  - .specify/templates/plan-template.md ✅ (Constitution Check reads generically
    from this file; no principle names hard-coded — stays aligned)
  - .specify/templates/spec-template.md ✅ (no constitution references)
  - .specify/templates/tasks-template.md ✅ (no constitution references)
  - CLAUDE.md ⚠ pending — not yet created; when authored (BE-001) it MUST mirror
    the runtime-relevant rules here (auth isolation, error catalog, 2-flavor,
    contract sync).

Deferred / Follow-up TODOs: None.
================================================================================
-->

# LiveCanvas Backend Constitution

> Repo: `livecanvas-backend` — Django + Django REST Framework API for the
> LiveCanvas live-wallpaper app. Serves public content (wallpaper / category /
> tag / collection), admin content management + upload pipeline, and
> self-hosted In-App-Purchase verification (no RevenueCat). There is **no user
> or account system** — premium entitlement is resolved per `transaction_id`
> verified directly against Apple / Google.
>
> The mobile client lives in a separate repo (`livecanvas-mobile`) and is fully
> independent; the two are coupled ONLY through the hand-synced contract
> (`contracts/openapi.yaml` + `.claude/api-context.md`).

## Core Principles

### I. Contract-First & Dual-Repo Contract Sync

The API contract is the single source of truth, and it is derived from screens —
never the reverse. Any API change MUST flow: `docs/screen-inventory.md` (what a
screen needs) → `contracts/openapi.yaml` + `.claude/api-context.md` → server code.

- `contracts/openapi.yaml` (machine-readable) and `.claude/api-context.md`
  (human/LLM-readable companion) MUST stay in lockstep; editing one without the
  other is FORBIDDEN.
- Both contract files exist in BOTH repos. When the contract changes in the repo
  currently implementing it, the change MUST be copied verbatim to the other repo
  (see Development Workflow → Contract Sync).
- The contract carries an explicit `version`. Changing request/response shape,
  adding/removing endpoints, or changing an error code MUST bump the contract
  version and be noted in `api-context.md`'s changelog header.
- Server behavior MUST NOT diverge from the frozen contract. If implementation
  reveals the contract is wrong, stop and amend the contract first, then code.

**Rationale**: Two independently-developed repos with no shared build can only
stay compatible if the contract is authoritative and synchronized deliberately.
Screen-driven design keeps the API surface exactly as large as the product needs
— no speculative endpoints.

### II. Two-Tier Auth Isolation & Account-Less Entitlement

The system has exactly two authentication tiers, and they MUST remain completely
separate. There is no end-user login.

- `X-App-Key` authenticates the **app** (not a user) for all public and IAP
  endpoints (except signature-verified webhooks).
- `Authorization: Bearer <jwt>` authenticates an **admin** for all `/admin/*`
  endpoints.
- The two tiers MUST NOT be mixed on a single endpoint, share middleware, or fall
  back to one another. An admin token MUST NEVER grant access to a public
  endpoint's app-key checks and vice versa.
- Webhooks (`/iap/webhook/apple`, `/iap/webhook/google`) carry no app key — they
  are authenticated solely by verifying the JWS / Pub-Sub signature in the body.
- Premium entitlement is derived from a store `transaction_id` verified against
  Apple / Google — NEVER from a user record, session, or account. The backend
  stores no passwords and has no login flow.

**Rationale**: Conflating an app-level key with an admin credential is a direct
path to privilege escalation. Keeping the tiers physically separate makes every
endpoint's trust boundary obvious and reviewable. An account-less model removes an
entire class of auth vulnerabilities and PII obligations.

### III. Entitlement Enforced at the Download Edge

Premium access MUST be enforced at the point of file delivery, not merely at
listing time. Metadata may be public; the bytes are gated.

- Listing and detail endpoints MAY return premium items with full metadata
  (`is_premium: true`); this drives the "unlock" UI on the client.
- The ONLY authoritative entitlement gate is `GET /wallpapers/{id}/download-url`,
  which MUST require a valid active `transaction_id` for premium items and return
  `402 ENTITLEMENT_REQUIRED` otherwise.
- "Download all" for a premium collection is client-side iteration over per-item
  `download-url` calls; there is NO bulk endpoint that bypasses the per-file gate.
- Download URLs MUST be presigned, short-lived (expiry ≤ 5 minutes), and scoped to
  a single object. Object keys MUST NOT be guessable/enumerable in a way that
  enables IDOR.

**Rationale**: Gating only at the list level is trivially bypassed by calling the
detail or download endpoint directly. Centralizing the check at the one edge that
serves bytes means there is exactly one place to audit for revenue-critical
correctness.

### IV. Structured Errors & Error-Code Catalog

Every error response MUST use one shape, and every code MUST come from the shared
catalog. Error codes are part of the contract.

- Error body MUST be `{ "error": { "code": "<CODE>", "message": "<human text>" } }`
  — no other error shape is permitted.
- `code` MUST be a stable, machine-consumable enum from the Error-Code Catalog in
  `api-context.md`; the mobile client branches on `code`, never on `message`.
- Adding, removing, or repurposing a code is a contract change (Principle I).
- Errors MUST be produced by a centralized DRF exception handler — raising ad-hoc
  `Response({...}, status=...)` error bodies at view level is FORBIDDEN.
- Raw exceptions, stack traces, or database errors MUST NEVER reach the client.
- HTTP status and catalog code MUST agree (e.g. `ENTITLEMENT_REQUIRED` → 402,
  `INVALID_APP_KEY` → 401).

**Rationale**: A client parsing free-text messages is fragile and un-localizable.
A single catalog and a single handler make error behavior consistent, testable,
and safe (no accidental leakage of internal detail).

### V. Feature-First Django App Architecture

The codebase MUST be organized into cohesive Django apps by domain, with clear,
enforced boundaries. Business logic lives in services, not views.

- Apps: `apps/wallpapers` (Category, Tag, Wallpaper, Collection + public API),
  `apps/uploads` (admin upload, presign, transcode pipeline),
  `apps/iap` (verify-receipt, webhooks, entitlement). New domains → new apps.
- Views/serializers MUST stay thin: parse/validate in → delegate to a service or
  queryset → serialize out. Non-trivial orchestration MUST live in a service
  module, not in the view.
- One app MUST NOT import another app's internal modules directly. Cross-app
  collaboration goes through a public service function or a shared `core` module.
- Config, cross-cutting middleware (e.g. `X-App-Key`), the exception handler, and
  base classes live under `config/` or a `core`/shared package — NEVER duplicated
  per app.
- Prefer explicit, boring composition over clever abstraction; introduce an
  abstraction only when a second concrete caller exists.

**Rationale**: Clear app boundaries let content, upload, and billing evolve
independently and keep revenue logic from leaking into content code. Thin views
keep behavior unit-testable without spinning up the full request stack.

### VI. Cursor Pagination & Consistent Response Envelopes

Large lists MUST use keyset (cursor) pagination; small curated lists return in
full. Response shapes MUST match the contract exactly.

- `GET /wallpapers` and `GET /admin/wallpapers` MUST use cursor pagination
  (`?cursor=&limit=`, `limit` default 20, max 100). Offset/`page`-based pagination
  is FORBIDDEN.
- Paginated responses MUST use the envelope
  `{ "items": [...], "next_cursor": <string|null>, "has_more": <bool> }`.
- Curated lists — `GET /categories`, `GET /tags`, `GET /collections` — are
  bounded (expected < 100) and MUST return the full array unpaginated.
  `GET /collections/{id}` embeds its `items` in curated order, unpaginated
  (soft cap ≤ 100 wallpapers/collection).
- An invalid or expired cursor MUST return `400 VALIDATION_ERROR`, never a 500 or
  a silently-reset first page.

**Rationale**: Offset pagination degrades and double-serves rows as the dataset
grows and shifts; keyset pagination is stable and index-friendly. Returning small
curated sets whole avoids needless round-trips and matches how the client renders
them.

### VII. Async Media Pipeline Safety

Media processing MUST run asynchronously and defensively. The request thread MUST
NOT do heavy work, and untrusted files MUST be validated before use.

- Upload is a two-step presigned flow: client PUTs to storage via a presigned URL,
  then registers the object key. The API process MUST NOT proxy file bytes.
- Transcode, thumbnailing, watermarking, and malware scanning MUST run in Celery
  tasks — NEVER inline in a request.
- Uploaded files MUST be validated by **real** content sniffing (actual MIME /
  magic bytes), not by trusting the client-supplied `content_type` or extension,
  and MUST be malware-scanned (ClamAV) before publish. Failures MUST surface as
  `422 FILE_REJECTED`.
- Celery tasks MUST be idempotent and safe to retry; a failed task MUST leave the
  wallpaper in an inspectable `failed` state, never a half-published one.
- Media-derived fields (`thumbnail_url`, `resolution`, …) MAY be `null` while
  processing; the contract already models this and the client MUST tolerate it.

**Rationale**: Admin-uploaded video is the largest attack surface and the heaviest
workload. Pushing it off-thread keeps the API responsive; content-sniffing and
scanning stop malicious or malformed files from reaching users or the CDN.

### VIII. Two-Flavor Configuration (dev + prod only)

The project MUST support exactly two configuration flavors: `dev` and `prod`.
No third flavor may be introduced.

- Settings MUST be split into `config/settings/base.py` plus exactly two flavor
  modules: `config/settings/dev.py` and `config/settings/prod.py`. Creating a
  `staging.py` or any additional flavor is FORBIDDEN.
- Flavor selection MUST be via `DJANGO_SETTINGS_MODULE`
  (`config.settings.dev` | `config.settings.prod`); `manage.py` defaults to `dev`.
- Configuration and secrets MUST be read from the environment via `django-environ`
  (`.env.dev` / `.env.prod`). Only `.env.*.example` files are committed; real
  `.env.dev` / `.env.prod` MUST be git-ignored.
- `prod` MUST run with `DEBUG=False`, strict `ALLOWED_HOSTS`, security headers,
  real S3 + CDN, and structured logging. `dev` MAY relax these for local ergonomics
  but MUST NOT be reachable in production.
- Promotion path is: verify on `dev` → deploy `prod`. There is no intermediate
  staging environment.

**Rationale**: Two flavors keep configuration honest and reviewable — every
setting has exactly one dev value and one prod value. Extra flavors multiply the
matrix of untested combinations and drift; the product does not need them.

### IX. Data Integrity, Migrations & Curated Referential Integrity

Content and billing data MUST never be silently corrupted. Schema changes and
curated relationships MUST protect integrity.

- Migrations MUST be non-destructive and reversible where feasible; a migration
  that drops or rewrites data MUST be called out in review.
- Tags and Collections are **curated**, not free-form. Attaching a wallpaper to a
  non-existent tag/collection MUST fail with the catalog code
  (`TAG_NOT_FOUND` / `WALLPAPER_NOT_FOUND`); duplicate slugs MUST fail with
  `*_SLUG_CONFLICT`. Deleting a tag still in use MUST fail with `TAG_IN_USE`.
- Collection membership is an **ordered** many-to-many: the join row carries a
  `position`, and read endpoints MUST return items in that curated order.
  Reordering replaces the ordered set atomically.
- Deletions of user-visible content SHOULD be soft (mark deleted) so downloads and
  references degrade gracefully rather than 500-ing.
- IAP records (`transaction_id` → entitlement) are financial truth; mutations MUST
  be traceable and MUST NOT be overwritten by a lower-trust source than the store.

**Rationale**: This backend holds curated catalog data and revenue-bearing
entitlement records. Referential-integrity codes make admin mistakes visible
instead of producing orphaned or mis-ordered content; ordered joins are what make
"Collection" a product feature rather than a bag.

### X. Testing Discipline

Business logic, API contracts, and revenue-critical paths MUST be tested. Coverage
is judged by scope, not by a hard percentage.

- `pytest-django` is the standard runner. Tests MUST be deterministic (no reliance
  on wall-clock, network, or ordering) and use factories/fixtures for data.
- REQUIRED coverage: two-tier auth enforcement, entitlement gating at
  `download-url`, IAP verify + webhook signature handling, cursor pagination
  (including invalid-cursor), the error-code catalog mapping, and curated
  integrity rules (Principle IX).
- API contract tests MUST assert response shape against the frozen contract
  (envelope, field names, error body) so drift from `openapi.yaml` is caught.
- External stores (Apple/Google, S3, ClamAV) MUST be mocked at their boundary;
  tests MUST NOT hit real store APIs or object storage.
- No hard coverage threshold gates merges; reviewers assess whether the critical
  paths above are exercised.

**Rationale**: Silent auth or entitlement bugs cost revenue and trust and produce
no error until exploited. Testing the trust boundaries and the contract — rather
than chasing a coverage number — puts effort where correctness actually matters.

### XI. Code Quality, Security Hygiene & Dependency Management

Code MUST be clean, secure by default, and built on deliberately-chosen
dependencies.

- `ruff` (lint + format) MUST pass with zero warnings. Public functions SHOULD
  carry type hints; new modules MUST.
- Input MUST be validated at every boundary (query params, request bodies, webhook
  payloads, presigned-upload registrations, admin input) via DRF serializers —
  never trust client-supplied data.
- Secrets, `X-App-Key`, admin tokens, receipts, and signed payloads MUST NEVER be
  written to logs, error messages, or traces. Logs MUST NOT leak PII or credentials.
- **Dependency hygiene**: before adding or upgrading a package, its latest stable
  version MUST be looked up on PyPI and its official docs consulted for API surface
  and breaking changes. Versions MUST NOT be guessed or copied from memory.
  Dependencies MUST be pinned (compatible-release / exact) and `requirements/*.txt`
  lock state committed. A MAJOR upgrade MUST review the CHANGELOG before merge.
- Self-documenting code is preferred; comments explain *why*, not *what*.

**Rationale**: A public API handling money and admin uploads is a target;
validating every boundary and never logging secrets closes the common holes.
Verifying dependencies at plan time turns install-time surprises into a
30-second lookup and avoids pulling in fictional or known-vulnerable packages.

## Technical Standards

### Platform & Stack

- **Framework**: Django + Django REST Framework
- **Language**: Python 3.11+
- **Database**: PostgreSQL (managed in `prod`)
- **Storage / CDN**: S3-compatible object storage (provider TBD: AWS S3 /
  Cloudflare R2 / DO Spaces) fronted by a CDN, via `django-storages`
- **Async**: Celery + Redis (transcode, thumbnail, watermark, malware scan)
- **Config**: `django-environ`, split settings `base` + `dev` + `prod` (Principle VIII)
- **Auth**: `X-App-Key` middleware (app tier) + admin Bearer JWT (`/admin/*`)
- **Linting/Format**: `ruff` (zero warnings)
- **Testing**: `pytest-django` + factories, boundary mocks
- **Media tooling**: ffmpeg (transcode), ClamAV (scan)
- **Build flavors**: `dev`, `prod` — and only these two

### Core Domains

- **Content**: `Category`, `Tag` (curated, M2M with Wallpaper), `Wallpaper`,
  `Collection` (curated, **ordered** M2M via join `position`) + public read API
- **Uploads**: presigned 2-step upload, transcode pipeline, admin CRUD, audit log
- **IAP**: self-hosted `verify-receipt` (App Store Server API / Google Play
  Developer API), Apple/Google webhooks, `subscription-status`, entitlement gate
- **Delivery**: presigned, short-lived, single-object `download-url` (the gate)

### Data & Storage

- Sensitive/financial data (entitlement records) is authoritative from the store;
  never overwritten by lower-trust input.
- Object keys for premium content MUST NOT be enumerable in a way enabling IDOR.
- Curated lists (categories/tags/collections) are bounded and returned whole.

## Development Workflow

### SDD Flow (speckit)

Each backend feature follows:

```
/speckit.specify → /speckit.clarify → /speckit.plan → /speckit.tasks → /speckit.implement
```

Branch: `BE-NNN-feature-name`, folder `specs/BE-NNN-feature-name/`. Spec planning
is tracked in `.claude/sdd-roadmap.md`; current state in `.claude/project-context.md`.

### Contract Sync (cross-repo)

1. Update `docs/screen-inventory.md` FIRST if the screen's data need changed.
2. Edit `contracts/openapi.yaml` and `.claude/api-context.md` together; bump the
   contract `version`.
3. Copy both files verbatim into `livecanvas-mobile` and note the sync.
4. Only then implement server code against the frozen contract.

### Pre-Commit Checklist (MANDATORY)

```bash
ruff check . && ruff format --check .   # zero warnings
pytest                                  # all tests pass
python manage.py makemigrations --check --dry-run   # no unstaged schema drift
```

### Testing Gates

All changes MUST pass before merge:

1. `ruff` lint + format clean (zero warnings)
2. `pytest` green, deterministic
3. Migrations consistent (no un-generated migrations)
4. Contract tests pass against the current frozen `openapi.yaml`
5. Critical-path tests (auth isolation, entitlement gate, IAP verify) present for
   touched areas

### Review Requirements

- All changes reviewed before merge.
- Auth, entitlement, IAP, and presigned-URL changes MUST receive extra scrutiny.
- Contract changes MUST confirm the mobile repo was (or will be) synced.
- New dependencies MUST be justified and version-verified (Principle XI).
- Schema changes MUST include migration review (Principle IX).

## Governance

This constitution defines the non-negotiable principles for LiveCanvas Backend.
All implementation and planning decisions MUST align with it; where a spec or PR
conflicts, the constitution wins unless it is formally amended.

### Amendment Process

1. Proposed amendments MUST be documented with rationale.
2. Amendments MUST be assessed for impact on existing code and the contract.
3. Breaking governance changes require a migration note before approval.
4. The version MUST increment per semantic versioning:
   - **MAJOR**: principle removal or backward-incompatible redefinition.
   - **MINOR**: new principle or materially expanded guidance.
   - **PATCH**: clarification or wording refinement.
5. The Sync Impact Report at the top of this file MUST be updated on every change.

### Compliance & Communication

- Every PR MUST verify compliance with the principles relevant to its scope.
- Complexity beyond these standards MUST be explicitly justified (use the plan
  template's Complexity Tracking table).
- Deviations MUST be documented with rationale and approved by the project lead.
- **Communication convention**: Vietnamese between the user and Claude; English
  for all code, comments, commit messages, and identifiers.
- Runtime development guidance lives in `CLAUDE.md` (to be authored in BE-001) and
  MUST mirror the runtime-relevant rules here without contradicting them.

**Version**: 1.0.0 | **Ratified**: 2026-07-23 | **Last Amended**: 2026-07-23

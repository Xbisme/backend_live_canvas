---
description: "Task list for BE-002 Backend Foundation (DRF + App Layer + Infra Config)"
---

# Tasks: Backend Foundation (DRF + App Layer + Infra Config)

**Input**: Design documents from `specs/BE-002-backend-foundation/`

**Prerequisites**: [plan.md](plan.md), [spec.md](spec.md), [research.md](research.md),
[data-model.md](data-model.md), [contracts/foundation-contracts.md](contracts/foundation-contracts.md),
[quickstart.md](quickstart.md)

**Tests**: INCLUDED — Constitution Principle X makes two-tier auth enforcement, the error-code
catalog mapping, and cursor pagination REQUIRED coverage. Test tasks are first-class here.

**Organization**: Grouped by user story (US1 P1 → US2 P1 → US3 P2 → US4 P3) for independent delivery.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependency on an incomplete task)
- **[Story]**: US1 / US2 / US3 / US4 (only on user-story phase tasks)
- Every task lists an exact file path.

## Path Conventions

Single backend service at repo root. Cross-cutting machinery under `core/` (Constitution V); feature
apps under `apps/`; settings in `config/settings/{base,dev,prod}.py`; contract in `.claude/` +
`contracts/`, per [plan.md](plan.md) → Project Structure.

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: New dependency, recompiled locks, and the empty feature-app packages.

- [X] T001 [P] Add `django-storages[s3]==1.14.6` to `requirements/base.in` (boto3 pulled + locked
  transitively; versions verified on PyPI 2026-07-23 — Constitution XI), with a one-line comment
- [X] T002 Recompile `requirements/base.txt`, `dev.txt`, `prod.txt` via `uv pip compile` and
  `uv pip sync requirements/dev.txt`; commit both `.in` and `.txt` — depends on T001
- [X] T003 [P] Create `apps/__init__.py` (namespace) and three model-less app shells —
  `apps/wallpapers/`, `apps/uploads/`, `apps/iap/` — each with `__init__.py`, `apps.py`
  (`AppConfig` with `name="apps.<domain>"`, explicit `default_auto_field="django.db.models.BigAutoField"`)
  and an empty `migrations/__init__.py`; **no** `models.py` content

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: The shared error catalog, the centralized exception handler, app registration, and the
base DRF/storage settings that every user story builds on.

**⚠️ CRITICAL**: No user story can be completed until this phase is done.

- [X] T004 [P] Implement `core/errors.py` — `ErrorCode` constants mirroring the catalog in
  `.claude/api-context.md` (full mirror incl. the new `SERVER_ERROR`, `METHOD_NOT_ALLOWED`), an
  `AppError(APIException)` base carrying `(code, status_code, default_detail)`, and `InvalidAppKey`
  (401, `INVALID_APP_KEY`) per [data-model.md](data-model.md) §1
- [X] T005 [P] Contract patch **v0.3.0 → v0.3.1**: add `SERVER_ERROR` (500) and `METHOD_NOT_ALLOWED`
  (405) to the Error-Code Catalog in `.claude/api-context.md` (table + changelog header + version)
  and mirror in `contracts/openapi.yaml`; add a **⚠️ mobile-sync handoff note** (copy both files
  verbatim to `livecanvas-mobile`) per [research.md](research.md) R7 (that repo is not in this
  workspace)
- [X] T006 Implement `core/exception_handler.py::structured_exception_handler` — wrap DRF's default
  handler, map `Http404`/`NotFound`→`NOT_FOUND`, `ValidationError`/`ParseError`→`VALIDATION_ERROR`,
  `InvalidAppKey`/`NotAuthenticated`/`AuthenticationFailed`→`INVALID_APP_KEY`,
  `MethodNotAllowed`→`METHOD_NOT_ALLOWED`, `AppError`→its own code, and `None`(unhandled)→log via
  `logger.exception` + `SERVER_ERROR` (500); always render `{ "error": { "code", "message" } }`
  (depends on T004)
- [X] T007 Wire `config/settings/base.py` — add `apps.wallpapers`/`apps.uploads`/`apps.iap` to
  `INSTALLED_APPS` (rest_framework already present from BE-001); add a `REST_FRAMEWORK` block setting
  `EXCEPTION_HANDLER="core.exception_handler.structured_exception_handler"`,
  `DEFAULT_AUTHENTICATION_CLASSES=[]` and `DEFAULT_PERMISSION_CLASSES=["rest_framework.permissions.AllowAny"]`
  (app-key is **opt-in per tier**, never global — Constitution II); **no** pagination key yet
  (added in US3) (depends on T003, T006)
- [X] T008 Declare the storage/CDN env catalog in `config/settings/base.py` — read
  `AWS_STORAGE_BUCKET_NAME`, `AWS_S3_ENDPOINT_URL`, `AWS_S3_REGION_NAME`, `AWS_ACCESS_KEY_ID`,
  `AWS_SECRET_ACCESS_KEY`, `CDN_BASE_URL` as declared-not-required (base has safe unset defaults);
  leave the `STATIC` whitenoise config from BE-001 untouched (depends on T007)

**Checkpoint**: Skeleton boots on dev; migrations still clean (no business models); errors already
render as the envelope. User stories can now proceed.

---

## Phase 3: User Story 1 — App-tier requests gated by `X-App-Key` (Priority: P1) 🎯 MVP

**Goal**: Public/IAP-tier requests are accepted only with a valid `X-App-Key`, else `401`
`INVALID_APP_KEY`; the app tier is provably isolated from the (future) admin Bearer tier.

**Independent Test**: [quickstart.md](quickstart.md) "User Story 1" — probe with no key / wrong key /
Bearer-only → 401 `INVALID_APP_KEY`; correct key → 200; key never logged.

### Tests for User Story 1 ⚠️ (write first, ensure they fail before implementation)

- [X] T009 [P] [US1] App-key auth tests in `core/tests/test_app_key_auth.py` — missing key → 401
  `INVALID_APP_KEY`; wrong key → 401 `INVALID_APP_KEY`; `Authorization: Bearer …` only → 401
  `INVALID_APP_KEY` (no cross-tier fallback); correct key → 200; **empty configured key** (`X_APP_KEY=""`)
  → app tier denies every request incl. an empty presented key (FR-021); **`GET /health` and
  `/health/ready` still return 200 without any `X-App-Key`** (FR-015, gate not applied to health);
  assert the key value is absent from captured logs per
  [contracts/foundation-contracts.md](contracts/foundation-contracts.md) C1

### Implementation for User Story 1

- [X] T010 [US1] Implement `core/authentication.py` — `AppKeyAuthentication(BaseAuthentication)`
  reading `HTTP_X_APP_KEY`, constant-time (`hmac.compare_digest`) match against `settings.X_APP_KEY`,
  raising `InvalidAppKey` on absent/mismatch, returning `(AppPrincipal(), None)` on success; define a
  lightweight non-`User` `AppPrincipal` with `is_authenticated=True`. **Guard misconfiguration
  (FR-021)**: if `settings.X_APP_KEY` is empty/unset, deny **every** request (never authenticate an
  empty presented key) — raise `InvalidAppKey` regardless of the presented value (depends on T004)
- [X] T011 [P] [US1] Implement `core/permissions.py::IsAppAuthenticated` — allow only when
  `request.user` is an authenticated `AppPrincipal`
- [X] T012 [US1] Implement `core/api.py::AppTierAPIView(APIView)` base setting
  `authentication_classes=[AppKeyAuthentication]`, `permission_classes=[IsAppAuthenticated]`
  (depends on T010, T011)
- [X] T013 [US1] Add the temporary app-tier probe: `AppTierProbeView` in `core/views.py` (→ `200
  {"ok": true}`), route `/_probe/app-tier` in `core/urls.py`, marked temporary/out-of-contract
  (depends on T012)
- [X] T014 [US1] Run the US1 quickstart on dev; confirm the T009 tests pass — incl. the empty-key
  denial and the health-not-gated assertions (depends on T013). **Prod fail-fast for the key is
  configured in T025** (same `prod.py` file as storage fail-fast)

**Checkpoint**: MVP — the app-tier security boundary works, is isolated, and cannot be silently
disabled by a missing key in prod.

---

## Phase 4: User Story 2 — Every error is a structured catalog envelope (Priority: P1)

**Goal**: Every error (404 / validation / unhandled 500 / app-key) returns
`{ error: { code, message } }` with a catalog `code` and no traceback, in both flavors.

**Independent Test**: [quickstart.md](quickstart.md) "User Story 2" — probe routes raise each error
class; assert envelope + code + status; assert no stack trace, incl. prod `DEBUG=False`.

### Tests for User Story 2 ⚠️

- [X] T015 [P] [US2] Error-envelope tests in `core/tests/test_error_envelope.py` — 404→`NOT_FOUND`,
  validation→`VALIDATION_ERROR`, unhandled→`SERVER_ERROR` (500) with **no** traceback text,
  app-key→`INVALID_APP_KEY`; assert identical safe body under the prod flavor (`DEBUG=False`) per
  [contracts/foundation-contracts.md](contracts/foundation-contracts.md) C2

### Implementation for User Story 2

- [X] T016 [US2] Add error probe views + routes to `core/views.py` and `core/urls.py` —
  `/_probe/validation` (raises DRF `ValidationError`) and `/_probe/boom` (raises an unhandled
  exception), both subclassing `AppTierAPIView` (so they require a valid `X-App-Key`, matching the
  quickstart which passes `$KEY`); the 404 case uses any unmatched path and needs no key
  (temporary/out-of-contract)
- [X] T017 [US2] Harden `core/exception_handler.py` for the 500 path — ensure `logger.exception`
  logs server-side only and the client body carries no internal detail; confirm `ParseError`→
  `VALIDATION_ERROR` mapping (depends on T006, T016)
- [X] T018 [US2] Run the US2 quickstart on **both** flavors; confirm T015 passes and the prod 500
  body has no debug page (depends on T017)

**Checkpoint**: All errors are catalog envelopes; the two P1 contracts compose (app-key error uses
the envelope).

---

## Phase 5: User Story 3 — REST framework + feature-app skeleton (Priority: P2)

**Goal**: DRF defaults to cursor pagination (`{items,next_cursor,has_more}`, limit 20/max 100) and
the three feature apps are registered, model-less, migration-clean.

**Independent Test**: [quickstart.md](quickstart.md) "User Story 3" — apps registered & model-less;
`makemigrations --check` clean; default pagination class + exception handler are the configured
defaults.

### Tests for User Story 3 ⚠️

- [X] T019 [P] [US3] Foundation tests in `core/tests/test_drf_foundation.py` — the three `apps.*`
  are registered and have no models; `DEFAULT_PAGINATION_CLASS` is `EnvelopeCursorPagination` with
  `page_size=20`/`max_page_size=100`; `EXCEPTION_HANDLER` is the structured handler; the pagination
  response builder emits `{items,next_cursor,has_more}` — test `get_paginated_response()` **directly**
  with a stub page object (no real model needed; `ordering="-created_at"` only bites once BE-003 adds
  a model with that field)

### Implementation for User Story 3

- [X] T020 [US3] Implement `core/pagination.py::EnvelopeCursorPagination(CursorPagination)` —
  `page_size=20`, `max_page_size=100`, `page_size_query_param="limit"`, `cursor_query_param="cursor"`,
  `ordering="-created_at"`, `get_paginated_response()` → `{items,next_cursor,has_more}` per
  [contracts/foundation-contracts.md](contracts/foundation-contracts.md) C3
- [X] T021 [US3] Add `DEFAULT_PAGINATION_CLASS="core.pagination.EnvelopeCursorPagination"` +
  `PAGE_SIZE=20` to the `REST_FRAMEWORK` block in `config/settings/base.py` (depends on T020)
- [X] T022 [US3] Run the US3 quickstart; confirm `makemigrations --check --dry-run` clean and T019
  passes (depends on T021)

**Checkpoint**: DRF conventions inherited by any future endpoint; app boundaries established.

---

## Phase 6: User Story 4 — Object storage & CDN per flavor (Priority: P3)

**Goal**: `dev` boots on a local storage fallback; `prod` resolves S3 + CDN from env and fails fast
on missing required config. Config only — no upload/presign logic.

**Independent Test**: [quickstart.md](quickstart.md) "User Story 4" — dev `default_storage` is the
local fallback; prod with full vars resolves `S3Storage`; prod missing a required var →
`ImproperlyConfigured`.

### Tests for User Story 4 ⚠️

- [X] T023 [P] [US4] Storage-config tests in `core/tests/test_storage_config.py` — dev fallback
  storage class when S3 creds absent (FR-010); prod resolves `S3Storage` + `CDN_BASE_URL` with vars
  set; prod raises `ImproperlyConfigured` when a required storage/CDN var is missing (FR-011)

### Implementation for User Story 4

- [X] T024 [US4] Configure `config/settings/dev.py` — `STORAGES["default"]` → `FileSystemStorage`
  local fallback (optional MinIO when `AWS_S3_ENDPOINT_URL` set); `CDN_BASE_URL` defaults to the
  local media URL (depends on T008)
- [X] T025 [US4] Configure `config/settings/prod.py` — `STORAGES["default"]` →
  `storages.backends.s3.S3Storage`; read `AWS_STORAGE_BUCKET_NAME`, `CDN_BASE_URL`, and required
  credentials/region with **no default** (fail-fast, consistent with BE-001 prod discipline); **also
  read `X_APP_KEY` with no default / reject empty** so prod refuses to boot without a configured app
  key (FR-021 — same fail-fast discipline; the app-key concern lives here because it edits the same
  `prod.py`) (depends on T008)
- [X] T026 [US4] Run the US4 quickstart; confirm dev fallback, prod resolve, prod fail-fast, and
  `check --deploy` stays clean with a valid prod env (depends on T024, T025)

**Checkpoint**: Storage substrate settled per flavor; BE-004 can build the upload pipeline on it.

---

## Phase 7: Polish & Cross-Cutting Concerns

**Purpose**: Env-example parity, doc alignment, secret-hygiene, and full two-flavor validation.

- [X] T027 [P] Update `.env.dev.example` and `.env.prod.example` with the storage/CDN catalog
  (`AWS_STORAGE_BUCKET_NAME`, `AWS_S3_ENDPOINT_URL`, `AWS_S3_REGION_NAME`, `AWS_ACCESS_KEY_ID`,
  `AWS_SECRET_ACCESS_KEY`, `CDN_BASE_URL`) — real `.env.*` stay git-ignored
- [X] T028 [P] Update `CLAUDE.md` — mark the exception handler as **landed in BE-002** (was
  "arrives in BE-002/BE-003"); note the app-tier `X-App-Key` auth base class now exists
- [X] T029 [P] Secret-hygiene check — confirm no code path logs `X-App-Key`, storage secrets, or the
  `SECRET_KEY`; assert `core/authentication.py` and the exception handler never include the key in
  log/error output (grep + review)
- [X] T030 Run the full [quickstart.md](quickstart.md) on both flavors + the full gate
  (`ruff check`, `ruff format --check`, `pytest`, `makemigrations --check --dry-run`, prod
  `check --deploy`); confirm SC-001…SC-008 and the BE-001 flavor-audit test still green

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (P1)**: T002 ⟵ T001. T003 independent.
- **Foundational (P2)**: T006 ⟵ T004; T007 ⟵ T003,T006; T008 ⟵ T007. Blocks all user stories.
- **US1 (P3)**: T010 ⟵ T004; T012 ⟵ T010,T011; T013 ⟵ T012; T014 ⟵ T013. (Foundational done.)
- **US2 (P4)**: T017 ⟵ T006,T016; T018 ⟵ T017. Handler already exists (T006); US2 adds probes+tests.
- **US3 (P5)**: T021 ⟵ T020; T022 ⟵ T021.
- **US4 (P6)**: T024/T025 ⟵ T008; T026 ⟵ T024,T025.
- **Polish (P7)**: T027 ⟵ T008; T028 after US1/US2; T029 after US1; T030 after everything.

### User Story Independence

- **US1** (app-key) and **US2** (errors) share the Foundational handler but are separately testable:
  US1 via the app-tier probe, US2 via the error probes. US2's envelope also renders US1's failure.
- **US3** (DRF+apps) and **US4** (storage) are independent of US1/US2 and of each other; both only
  depend on Foundational and can be built in parallel by different people.

### Parallel Opportunities

- Setup: T001, T003 in parallel.
- Foundational: T004, T005 in parallel (T005 is the contract/docs bump).
- US1: T009 (tests) + T011 in parallel with T010; then T012→T013→T014.
- Cross-story after Foundational: US3 and US4 fully parallel; US1/US2 parallel to them.
- Polish: T027, T028, T029 in parallel; T030 last.

---

## Parallel Example: after Foundational

```bash
# Different files, no incomplete-task dependency — run together:
Task: "App-key auth tests core/tests/test_app_key_auth.py (T009)"
Task: "core/permissions.py IsAppAuthenticated (T011)"
Task: "core/pagination.py EnvelopeCursorPagination (T020)"
Task: "Storage-config tests core/tests/test_storage_config.py (T023)"
```

---

## Implementation Strategy

### MVP First (User Story 1 only)

1. Phase 1 Setup → 2. Phase 2 Foundational (CRITICAL) → 3. Phase 3 US1 →
4. **STOP & VALIDATE**: app-tier `X-App-Key` gate + isolation (quickstart US1) → the security
   boundary every later endpoint sits behind is provably in place.

### Incremental Delivery

1. Setup + Foundational → skeleton boots, errors already enveloped, apps registered.
2. US1 → app-key boundary → **MVP** (security substrate).
3. US2 → full error-catalog coverage across all classes + prod safety.
4. US3 → cursor-pagination default + confirmed model-less app skeleton.
5. US4 → storage/CDN per flavor with prod fail-fast.
6. Polish → env-example parity, doc alignment, secret-hygiene, full two-flavor gate.

### Parallel Team Strategy

After Foundational: Dev A → US1, Dev B → US2, Dev C → US3, Dev D → US4. Converge at Polish.

---

## Notes

- [P] = different files, no incomplete-task dependency.
- Constitution guardrails enforced here: two-tier isolation (app-key opt-in per tier, never global —
  T007/T010/T012), **app-tier fail-safe** (empty configured key never authenticates + prod fail-fast —
  T010/T014/T025, FR-021), health/admin never gated (T009 asserts), structured-error catalog via one
  handler (T004/T006), exactly-two-flavor discipline
  (all storage/DB config in base/dev/prod only — BE-001 flavor-audit stays green), pinned reproducible
  deps (T001/T002), no secret logging (T029), contract lockstep for the v0.3.1 code additions (T005).
- The `/_probe/*` routes are **temporary foundation scaffolding**, out of the product contract, and
  are slated for removal when BE-003 supplies real app-tier endpoints.
- ⚠️ T005 leaves a cross-repo obligation: copy the updated `.claude/api-context.md` +
  `contracts/openapi.yaml` verbatim into `livecanvas-mobile` (not in this workspace).
- Commit after each task or logical group; stop at any checkpoint to validate a story.
- Total: 30 tasks (Setup 3 · Foundational 5 · US1 6 · US2 4 · US3 4 · US4 4 · Polish 4).
```

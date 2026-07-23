---
description: "Task list for BE-001 Project Bootstrap & 2-Flavor Setup"
---

# Tasks: Project Bootstrap & 2-Flavor Setup

**Input**: Design documents from `specs/BE-001-project-bootstrap/`

**Prerequisites**: [plan.md](plan.md), [spec.md](spec.md), [research.md](research.md),
[data-model.md](data-model.md), [contracts/health-endpoints.md](contracts/health-endpoints.md),
[quickstart.md](quickstart.md)

**Tests**: INCLUDED — the spec's FR-018 mandates automated health-endpoint tests (incl. the
DB-unavailable readiness path). Test tasks are therefore first-class here.

**Organization**: Grouped by user story (US1 P1 → US2 P2 → US3 P3) for independent delivery.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependency on an incomplete task)
- **[Story]**: US1 / US2 / US3 (only on user-story phase tasks)
- Every task lists an exact file path.

## Path Conventions

Single backend service at repo root. Project package `config/`, support app `core/`, deps in
`requirements/`, per [plan.md](plan.md) → Project Structure.

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Repo scaffolding, tooling config, and pinned dependency lock files.

- [X] T001 Create directory skeleton: `config/settings/`, `core/tests/`, `requirements/`,
  `.github/workflows/` (with `__init__.py` where needed) per [plan.md](plan.md) structure
- [X] T002 [P] Author `pyproject.toml` — project metadata + `[tool.ruff]` (lint+format) +
  `[tool.pytest.ini_options]` (`DJANGO_SETTINGS_MODULE=config.settings.dev`, testpaths)
- [X] T003 [P] Author `requirements/base.in`, `requirements/dev.in` (`-r base.in`),
  `requirements/prod.in` (`-r base.in`) with the exact pins verified in
  [research.md](research.md) (Django>=5.2,<5.3; DRF 3.17.1; psycopg 3.3.x; django-environ;
  gunicorn; whitenoise; python-json-logger; dev: pytest/pytest-django/factory_boy/ruff)
- [X] T004 Compile `requirements/base.txt`, `dev.txt`, `prod.txt` via `uv pip compile` and
  commit both `.in` and `.txt` (fully pinned transitive lock) — depends on T003

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: The shared Django skeleton both flavors build on — project package, base settings,
env loading, URL/WSGI entry, the `core` app shell, and the local database service.

**⚠️ CRITICAL**: No user story can be completed until this phase is done.

- [X] T005 [P] Create `manage.py` with default `DJANGO_SETTINGS_MODULE=config.settings.dev`
- [X] T006 [P] Create `config/__init__.py` (lazy Celery app import), `config/celery.py` (bare
  Celery app stub — no tasks/broker), `config/wsgi.py`, `config/asgi.py` (both defaulting env
  `DJANGO_SETTINGS_MODULE` to `config.settings.dev`)
- [X] T007 Implement `config/settings/base.py` — `django-environ` init; INSTALLED_APPS
  (contrib admin/auth/sessions/contenttypes/staticfiles + `rest_framework` + `core`); MIDDLEWARE;
  `DATABASES` via `env.db()`; env catalog (`SECRET_KEY`, `DATABASE_URL`, `ALLOWED_HOSTS`,
  `X_APP_KEY` declared-not-enforced, `DJANGO_LOG_LEVEL`); STATIC config; base LOGGING scaffold
  (depends on T004, T006)
- [X] T008 [P] Create `core/__init__.py`, `core/apps.py` (`CoreConfig`, no models), and a
  **stub `core/urls.py`** with empty `urlpatterns = []` (so the URLConf imports clean before
  US1 fills in the health routes — keeps Foundational bootable)
- [X] T009 Wire `config/urls.py` — include Django `admin/` and `include('core.urls')`
  (depends on T006, T008 — the stub `core/urls.py` from T008 makes this import-safe)
- [X] T010 [P] Author `.env.dev.example` and `.env.prod.example` covering the full env catalog
  (real `.env.dev`/`.env.prod` already git-ignored)
- [X] T011 [P] Author `docker-compose.yml` with a single Postgres 16 service (named volume,
  healthcheck, mapped port) — **no** Redis/cache/queue

**Checkpoint**: `python manage.py migrate` runs (contrib migrations) on the dev DB; skeleton
boots with no business logic. User stories can now proceed.

---

## Phase 3: User Story 1 — Developer runs on `dev` flavor + health (Priority: P1) 🎯 MVP

**Goal**: `runserver` on the `dev` flavor serves liveness `GET /health` (200) and readiness
`GET /health/ready` (200 when DB up, 503 when DB down).

**Independent Test**: Follow [quickstart.md](quickstart.md) "User Story 1" — curl both health
endpoints; stop the DB and confirm readiness→503 while liveness→200; `ls config/settings/`.

### Tests for User Story 1 ⚠️ (write first, ensure they fail before implementation)

- [X] T012 [P] [US1] Health tests in `core/tests/test_health.py` — liveness returns 200
  `{"status":"ok"}`; readiness returns 200 `{"status":"ready"}` with DB up; readiness returns
  503 `{"status":"unavailable"}` when the DB check is patched to raise (deterministic, no real
  outage) per [contracts/health-endpoints.md](contracts/health-endpoints.md)

### Implementation for User Story 1

- [X] T013 [US1] Implement `config/settings/dev.py` — `DEBUG=True`, open/localhost
  `ALLOWED_HOSTS`, relaxed security, verbose console logging, dev DB defaults pointing at the
  docker-compose Postgres (depends on T007)
- [X] T014 [P] [US1] Implement `core/views.py` — liveness view (always 200) and readiness view
  (runs `SELECT 1`, 200 on success / 503 on failure)
- [X] T015 [P] [US1] Populate `core/urls.py` — replace the Foundational stub's empty
  `urlpatterns` with routes `/health` and `/health/ready` to the views
- [X] T016 [US1] Run the US1 quickstart validation on `dev`; confirm T012 tests pass
  (depends on T013, T014, T015)

**Checkpoint**: MVP — a running local backend with working health endpoints on the `dev` flavor.

---

## Phase 4: User Story 2 — Operator boots the `prod` flavor (Priority: P2)

**Goal**: The `prod` flavor boots hardened (debug off, strict hosts, security headers, whitenoise
static, JSON logs), passes `manage.py check --deploy`, and fails fast on missing required config.

**Independent Test**: Follow [quickstart.md](quickstart.md) "User Story 2" — `check --deploy`
reports no critical issues; unsetting `SECRET_KEY`/`DATABASE_URL` on prod raises at startup.

### Tests for User Story 2 ⚠️

- [X] T017 [P] [US2] Prod settings tests in `core/tests/test_prod_settings.py` — importing prod
  settings yields `DEBUG=False` and the expected security flags; missing `SECRET_KEY` or
  `DATABASE_URL` raises `ImproperlyConfigured` (fail-fast, FR-011)

### Implementation for User Story 2

- [X] T018 [US2] Implement `config/settings/prod.py` — `DEBUG=False`; `ALLOWED_HOSTS` from env
  (required); `SECURE_SSL_REDIRECT`, `SECURE_HSTS_SECONDS`(+subdomains/preload),
  `SESSION_COOKIE_SECURE`, `CSRF_COOKIE_SECURE`, `SECURE_PROXY_SSL_HEADER`,
  `SECURE_CONTENT_TYPE_NOSNIFF`; `SECRET_KEY`/`DATABASE_URL` read with **no default**
  (depends on T007)
- [X] T019 [US2] Add whitenoise to MIDDLEWARE + `STORAGES`/`STATIC_ROOT` and JSON logging via
  `python-json-logger` in `config/settings/prod.py` (admin static served in prod)
- [X] T020 [US2] Validate on `prod`: `collectstatic --noinput` succeeds and
  `manage.py check --deploy` reports no critical issues (depends on T018, T019)

**Checkpoint**: Both flavors boot from configuration alone; prod is deploy-check clean.

---

## Phase 5: User Story 3 — Automated quality gates (Priority: P3)

**Goal**: CI runs lint, format-check, and tests on every push and fails on any violation; runtime
contributor guidance mirrors the constitution.

**Independent Test**: Push a branch — CI runs `ruff check`, `ruff format --check`, `pytest` and
reports pass/fail; a deliberate lint/format/test violation fails the pipeline.

### Implementation for User Story 3

- [X] T021 [US3] Author `.github/workflows/ci.yml` — Python 3.12, install `uv`, `uv pip sync
  requirements/dev.txt`, a Postgres service container, then `ruff check .`,
  `ruff format --check .`, `pytest`; pipeline fails if any step fails
- [X] T022 [P] [US3] Author `CLAUDE.md` mirroring the constitution's runtime rules (two-tier auth
  separation, structured-error catalog, two-flavor discipline, contract-sync procedure) and
  documenting how to create the initial internal-staff superuser via
  `python manage.py createsuperuser` (FR-019)

**Checkpoint**: All three stories independently functional; contributions are gated.

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Guardrails and end-to-end validation spanning both flavors.

- [X] T023 [P] Flavor-audit test in `core/tests/test_settings_flavors.py` — assert the
  `config.settings` package contains only `base`, `dev`, `prod` (+`__init__`); fail if any third
  flavor (e.g. `staging`) exists (SC-003) — depends on T013, T018
- [X] T024 Run the full [quickstart.md](quickstart.md) validation on both flavors (health, both
  flavors boot, `createsuperuser` + admin login reachable, ruff + pytest green) and confirm
  SC-001…SC-005, SC-007, SC-008 and FR-019
- [X] T025 [P] Verify secret hygiene: `git ls-files` shows only `.env.dev.example` /
  `.env.prod.example` (no real `.env.dev`/`.env.prod`) — SC-006

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (P1)**: no dependencies — start immediately. T004 depends on T003.
- **Foundational (P2)**: depends on Setup. Blocks all user stories. (T007 ⟵ T004,T006;
  T009 ⟵ T006,T008.)
- **US1 (P3)**: depends on Foundational. T013 ⟵ T007; T016 ⟵ T013,T014,T015.
- **US2 (P4)**: depends on Foundational. T018/T019 ⟵ T007. Independent of US1.
- **US3 (P5)**: depends on Foundational; CI meaningfully exercises US1/US2 tests, so run after
  them in practice. T022 independent.
- **Polish (P6)**: T023 depends on both `dev.py` (T013) and `prod.py` (T018); T024 after all.

### User Story Independence

- **US1** and **US2** are independent (dev-run+health vs prod-config-hardening) and can be built
  in parallel by different people once Foundational is done.
- **US3** (CI + guidance) is independent to author, but its value is realized once US1/US2 tests
  exist for CI to run.

### Parallel Opportunities

- Setup: T002, T003 in parallel.
- Foundational: T005, T006, T008, T010, T011 in parallel (T007, T009 gate on them).
- US1: T014, T015 in parallel; T012 (tests) authored in parallel up front.
- Cross-story: after Foundational, US1 and US2 can proceed simultaneously.
- Polish: T023, T025 in parallel.

---

## Parallel Example: Foundational Phase

```bash
# After Setup completes, launch independent foundational files together:
Task: "Create manage.py (T005)"
Task: "Create config package: __init__/celery/wsgi/asgi (T006)"
Task: "Create core app shell: __init__/apps.py (T008)"
Task: "Author .env.dev.example and .env.prod.example (T010)"
Task: "Author docker-compose.yml with Postgres only (T011)"
# Then: config/settings/base.py (T007) and config/urls.py (T009) once the above land.
```

## Parallel Example: User Story 1

```bash
# Health tests + the two independent implementation files:
Task: "Health tests in core/tests/test_health.py (T012)"
Task: "Implement core/views.py liveness+readiness (T014)"
Task: "Implement core/urls.py health routes (T015)"
```

---

## Implementation Strategy

### MVP First (User Story 1 only)

1. Phase 1 Setup → 2. Phase 2 Foundational (CRITICAL) → 3. Phase 3 US1 →
4. **STOP & VALIDATE**: health endpoints on `dev` (quickstart US1) → demo-able running backend.

### Incremental Delivery

1. Setup + Foundational → skeleton migrates & boots.
2. US1 → dev flavor + health working → **MVP**.
3. US2 → prod flavor hardened + deploy-check clean.
4. US3 → CI gates + runtime guidance.
5. Polish → flavor audit + full quickstart validation + secret-hygiene check.

### Parallel Team Strategy

After Foundational: Dev A → US1, Dev B → US2, Dev C → US3/CLAUDE.md. Converge at Polish.

---

## Notes

- [P] = different files, no incomplete-task dependency.
- Health readiness 503 path is unit-tested by patching the DB check to raise — no real outage.
- Constitution guardrails enforced here: exactly-two-flavor audit (T023), pinned reproducible
  deps (T004), secret hygiene (T025), health kept out of the product contract (design).
- Commit after each task or logical group; stop at any checkpoint to validate a story.
- Total: 25 tasks (Setup 4 · Foundational 7 · US1 5 · US2 4 · US3 2 · Polish 3).

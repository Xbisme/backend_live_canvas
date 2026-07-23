# Feature Specification: Project Bootstrap & 2-Flavor Setup

**Feature Branch**: `BE-001-project-bootstrap`

**Created**: 2026-07-23

**Status**: Draft

**Input**: User description: "BE-001 Project Bootstrap & 2-Flavor Setup — dựng khung project Django + DRF chạy được với đúng 2 flavor `dev` và `prod`, chưa có model/endpoint nghiệp vụ nào."

## Overview

This is the foundational spec for the LiveCanvas backend. It delivers a runnable
Django + DRF project skeleton that boots under **exactly two configuration
flavors — `dev` and `prod`** — with configuration sourced from the environment,
secrets kept out of version control, a health check to prove each flavor boots,
and automated quality gates in CI. It intentionally ships **no business
models or endpoints**; those arrive in BE-002 and later.

The "users" of this feature are the people who build and operate the backend:
**developers** (run it locally), **operators/deployers** (run it in production),
and **contributors** (whose changes are gated by CI).

## Clarifications

### Session 2026-07-23

- Q: Does the BE-001 skeleton keep Django's built-in admin + auth/sessions, or strip
  them? → A: Keep them. Django's built-in admin, `contrib.auth`, and `sessions` are
  retained as an **internal-staff** tool; a superuser is created via the standard
  management command. This does not conflict with the constitution's account-less rule,
  which governs **app end-users** only — internal staff authenticate. This is why the
  `prod` flavor uses whitenoise to serve the admin's static assets.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Developer runs the project locally on the `dev` flavor (Priority: P1)

A developer clones the repository, installs dependencies, starts a local database,
applies migrations, and starts the server on the `dev` flavor. They confirm the
service is alive by calling the health endpoint. This is the minimum viable
outcome: a project that runs.

**Why this priority**: Nothing else in the roadmap can proceed until the project
boots locally. Every subsequent spec (BE-002+) builds on this skeleton.

**Independent Test**: Fully testable by following the documented setup steps on a
clean machine and observing the liveness endpoint return success — delivers a
running local backend with zero business logic.

**Acceptance Scenarios**:

1. **Given** a clean clone and the documented prerequisites, **When** the developer
   installs dependencies, starts the local database, applies migrations, and starts
   the server on the `dev` flavor, **Then** the liveness health endpoint returns a
   success status.
2. **Given** the server running on `dev`, **When** the database is reachable, **Then**
   the readiness health endpoint returns success.
3. **Given** the server running on `dev`, **When** the database is unavailable, **Then**
   the readiness health endpoint returns a failure status (service-unavailable),
   while the liveness endpoint still returns success.
4. **Given** the repository, **When** the developer inspects available configuration
   flavors, **Then** exactly two exist (`dev`, `prod`) and no others.

---

### User Story 2 - Operator boots the project on the `prod` flavor (Priority: P2)

An operator prepares production configuration (via environment values), selects the
`prod` flavor, and verifies the project boots with production-hardened settings and
passes the framework's deployment safety checks.

**Why this priority**: Production readiness of the *configuration* must be proven
early so later specs deploy onto a known-good foundation, but it is not needed for
day-one local development.

**Independent Test**: Testable by selecting the `prod` flavor with a valid
production configuration and running the framework's deployment check with no
critical findings, without needing any business endpoints.

**Acceptance Scenarios**:

1. **Given** a valid production configuration, **When** the operator selects the
   `prod` flavor, **Then** the project boots with debug mode disabled, a restricted
   host allow-list, and security headers enabled.
2. **Given** the `prod` flavor selected, **When** the operator runs the framework's
   deployment safety check, **Then** it reports no critical issues.
3. **Given** the `prod` flavor, **When** a required production configuration value is
   missing, **Then** startup fails fast with a clear error rather than booting with
   an insecure default.

---

### User Story 3 - Contributor changes are gated by automated quality checks (Priority: P3)

A contributor opens a change. Automated CI runs linting, formatting verification,
and the test suite. The change cannot be considered mergeable unless all gates pass.

**Why this priority**: Quality gates protect the codebase from the first commit, but
the project can be developed locally before CI exists, so this trails P1/P2.

**Independent Test**: Testable by pushing a branch and observing CI run lint,
format-check, and tests, reporting pass/fail — verifiable independently of any
application behavior.

**Acceptance Scenarios**:

1. **Given** a pushed change, **When** CI runs, **Then** it executes lint,
   format-check, and the test suite and reports an overall pass/fail result.
2. **Given** a change that violates lint or formatting rules, **When** CI runs,
   **Then** the pipeline fails.
3. **Given** a change where the health check test passes and style is clean, **When**
   CI runs, **Then** the pipeline succeeds.

---

### Edge Cases

- **Third flavor attempted**: Any configuration flavor beyond `dev` and `prod` (e.g.
  a `staging` variant) MUST be treated as out of scope and MUST NOT exist in the
  repository. This is a hard constraint from the project constitution.
- **Database unreachable**: Readiness reports unavailable; liveness stays healthy so
  orchestration can distinguish "process alive" from "dependencies ready".
- **Missing/empty required environment value** (e.g. secret key, database URL on
  `prod`): startup fails fast with an actionable message; no insecure fallback.
- **Real secret files staged for commit**: The concrete environment files must be
  ignored by version control; only example templates may be committed.
- **Wrong flavor selected by default**: Local tooling defaults to the `dev` flavor so
  a developer never accidentally runs production settings locally.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST provide a runnable backend project skeleton that starts
  successfully with no business models or endpoints present.
- **FR-002**: The system MUST support **exactly two** configuration flavors, `dev` and
  `prod`, sharing a common base configuration. Introducing any additional flavor is
  FORBIDDEN.
- **FR-003**: The active flavor MUST be selectable at runtime via an environment
  setting, and local developer tooling MUST default to the `dev` flavor.
- **FR-004**: All environment-specific configuration and all secrets MUST be sourced
  from the environment, not hardcoded in source.
- **FR-005**: The repository MUST commit only example configuration templates for both
  flavors; the concrete per-flavor secret files MUST be excluded from version control.
- **FR-006**: The system MUST define a documented catalog of the environment values it
  reads, including at minimum: application secret key, active-flavor selector, database
  connection, allowed hosts, the app-tier key (declared for future use), and log level.
- **FR-007**: The system MUST expose a **liveness** health endpoint that returns success
  whenever the process is running.
- **FR-008**: The system MUST expose a **readiness** health endpoint that returns success
  only when its database dependency is reachable, and a service-unavailable status
  otherwise.
- **FR-009**: The `dev` flavor MUST run with debug mode enabled, an open/local host
  allow-list, security headers relaxed, and verbose console logging suitable for local
  development.
- **FR-010**: The `prod` flavor MUST run with debug mode disabled, a restricted host
  allow-list, transport/security headers enabled, the built-in admin's static assets
  served via a production-appropriate static handler (whitenoise), and structured logging.
- **FR-011**: On the `prod` flavor, startup MUST fail fast with a clear error when a
  required production configuration value is missing, rather than booting with an
  insecure default.
- **FR-012**: The project MUST pass the framework's built-in deployment safety check on
  the `prod` flavor with no critical findings.
- **FR-013**: Dependencies MUST be organized per flavor (base + dev + prod) with
  fully pinned, reproducible lock files committed, and MUST follow the constitution's
  Dependency Hygiene rules (verified latest stable versions, no guessed versions).
- **FR-014**: The project MUST provide a one-command way to start the local database
  dependency needed by the `dev` flavor. The local database MUST match the production
  database engine for parity. No other backing services are provisioned in this spec.
- **FR-015**: CI MUST run, on every pushed change, linting, formatting verification, and
  the test suite, and MUST fail the pipeline if any gate fails.
- **FR-016**: The repository MUST include runtime contributor guidance that mirrors the
  constitution's runtime-relevant rules (two-tier auth separation, structured-error
  catalog, two-flavor discipline, contract-sync procedure) without contradicting it.
- **FR-017**: The skeleton MUST NOT include the app-tier key middleware, the **custom
  admin Bearer-JWT tier**, the shared error handler/error-code catalog, business apps,
  object storage/CDN integration, or asynchronous workers — these are explicitly deferred
  to later specs. (Note: this exclusion is about the *custom* admin API auth; Django's
  built-in admin site is retained per FR-019.)
- **FR-018**: An automated test MUST cover the liveness and readiness endpoints
  (including the database-unavailable readiness case) so CI proves each flavor's health
  contract.
- **FR-019**: The skeleton MUST retain the framework's built-in admin site plus its
  authentication and session support as an **internal-staff** tool, with a documented way
  to create the initial staff superuser. This is distinct from the custom admin API tier
  (deferred per FR-017) and from the account-less handling of app end-users.

### Key Entities *(configuration artifacts, not business data)*

- **Configuration Flavor**: A named runtime configuration. Exactly two exist — `dev`
  and `prod` — each layered on a shared base. Attributes: debug mode, host allow-list,
  security-header posture, static-serving strategy, logging format, database source.
- **Environment Value Catalog**: The documented set of externally-provided values the
  system reads (secret key, active-flavor selector, database connection, allowed hosts,
  app-tier key [reserved for BE-002], log level). Each has a documented example.
- **Health Check**: Two operational signals — *liveness* (process is up) and *readiness*
  (database dependency reachable) — used by developers and orchestration to gauge state.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A developer following the documented setup on a clean machine gets the
  service running on the `dev` flavor and a successful liveness response in under 15
  minutes, with no manual source edits required.
- **SC-002**: The project boots successfully under **both** flavors from configuration
  alone (no code changes between flavors).
- **SC-003**: Exactly two configuration flavors exist in the repository; an audit finds
  zero additional flavors.
- **SC-004**: The readiness signal correctly reflects database availability in 100% of
  tested cases (healthy when reachable, unavailable when not).
- **SC-005**: On the `prod` flavor, the framework's deployment safety check reports zero
  critical findings.
- **SC-006**: No concrete secret/configuration file is present in version control; only
  example templates are committed (verified by inspecting tracked files).
- **SC-007**: CI passes on a clean baseline and fails when a deliberate lint, formatting,
  or test violation is introduced.
- **SC-008**: Dependency lock files are committed and reproducible — a fresh install
  resolves to identical pinned versions.

## Assumptions

- **Locked stack (pre-decided inputs, not open questions)**: Python 3.12; Django 5.2
  LTS; Django REST Framework 3.16; PostgreSQL via the psycopg 3 driver; `django-environ`
  for environment loading; gunicorn + whitenoise for production serving; `ruff` for
  lint/format; `pytest` + `pytest-django` (+ `factory_boy`) for tests; GitHub Actions for
  CI; `uv` as the dependency installer/compiler while retaining committed
  `requirements/*.{in,txt}` files. Exact patch versions are verified against the official
  registry at plan/implement time per constitution Principle XI.
- The framework's built-in admin site (with `auth`/`sessions`) is retained as an
  internal-staff tool in both flavors; the account-less rule in the constitution applies
  to app end-users, not internal staff (clarified 2026-07-23).
- The local `dev` database runs in a container started by a single command; the
  production database is an externally-provisioned managed instance addressed via
  configuration.
- Only the database backing service is provisioned in this spec; the cache/queue
  service is deferred to BE-004.
- This spec does not depend on the API contract (#000) and can be implemented
  independently and in parallel with contract freeze.
- Communication convention: Vietnamese between the user and Claude; English for code,
  comments, commit messages, and identifiers.
- Runtime guidance for the mobile repo and the API contract are unaffected by this spec.

## Dependencies

- **Constitution** (`.specify/memory/constitution.md`, v1.0.0) — this spec MUST comply,
  especially Principle VIII (Two-Flavor Configuration) and Principle XI (Dependency
  Hygiene).
- **No upstream spec dependency** — BE-001 is the first buildable backend spec.
- **Downstream**: BE-002 (Backend Foundation) builds directly on this skeleton and
  consumes the reserved app-tier key and flavor structure defined here.

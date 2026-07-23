# Implementation Plan: Backend Foundation (DRF + App Layer + Infra Config)

**Branch**: `BE-002-backend-foundation` | **Date**: 2026-07-23 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/BE-002-backend-foundation/spec.md`

## Summary

Extend the BE-001 skeleton into an API-serving foundation. Install and globally wire DRF; add a
**custom cursor pagination** class that emits the contract envelope `{ items, next_cursor, has_more }`;
add a **centralized DRF exception handler** that renders every error as
`{ error: { code, message } }` with `code` from the catalog; add an **app-tier `X-App-Key`
authentication + permission** pair (opt-in per tier, never global, strictly isolated from the future
admin Bearer tier); create three model-less feature apps `apps/{wallpapers,uploads,iap}`; wire
PostgreSQL for both flavors; and configure `django-storages` S3 + a CDN base URL per flavor (config
only, no upload logic). All cross-cutting machinery lives in `core/` per Constitution Principle V.

## Technical Context

**Language/Version**: Python 3.12 (repo venv; constitution floor 3.11+)

**Primary Dependencies**: Django 5.2 LTS, djangorestframework 3.17.1 (already pinned),
`django-storages[s3]` 1.14.6 + boto3 1.43.54 (NEW — verified on PyPI 2026-07-23), django-environ 0.14.0

**Storage**: PostgreSQL 16 (both flavors); S3-compatible object storage via django-storages
(config only — dev: local `FileSystemStorage` fallback / optional MinIO; prod: S3 + CDN from env)

**Testing**: pytest-django 4.12.0 (already pinned); boundary mocks; DB-backed for the flavor/migration
checks; no network to real S3/store

**Target Platform**: Linux server (containerized), served by gunicorn in prod

**Project Type**: Web service (Django + DRF), single backend at repo root

**Performance Goals**: N/A for this spec — no business endpoints; only foundation wiring. Pagination
defaults (limit 20, max 100) set the future ceiling.

**Constraints**: Exactly two settings flavors (dev, prod); prod fails fast on missing required config;
no secret logging; no cross-tier auth fallback; no offset pagination anywhere.

**Scale/Scope**: Foundation only — ~10 new source files under `core/` + `apps/*` shells, settings
edits to `base/dev/prod`, one contract-catalog patch bump, ~5 test modules.

## Constitution Check

*GATE: evaluated against constitution v1.0.0. Re-checked after Phase 1 design.*

| Principle | Relevance to BE-002 | Status |
|---|---|---|
| I. Contract-First & Dual-Repo Sync | Handler adds two foundation error codes (`SERVER_ERROR` 500, `METHOD_NOT_ALLOWED` 405) not yet in the catalog → **contract patch bump v0.3.0→v0.3.1** + sync to mobile repo. | ⚠ Requires contract update (planned; see research R7) |
| II. Two-Tier Auth Isolation | App-tier `X-App-Key` auth is **opt-in per tier** via base view classes, never a global default; admin Bearer tier absent here and must not be reachable/fallback. **Fail-closed**: an empty configured key never authenticates, and prod fails fast if `X_APP_KEY` is missing (FR-021). | ✅ By design |
| III. Entitlement at Download Edge | No download/entitlement logic in BE-002. | ✅ N/A |
| IV. Structured Errors & Catalog | Single centralized `EXCEPTION_HANDLER`; codes sourced from a `core.errors` catalog module mirroring `api-context.md`; no ad-hoc error bodies; no traceback leakage. | ✅ Core deliverable |
| V. Feature-First App Architecture | Cross-cutting code (auth, permission, pagination, handler, errors) lives in `core/`, not duplicated per app; three feature apps are cohesive shells; no cross-app imports. | ✅ By design |
| VI. Cursor Pagination & Envelopes | Custom `CursorPagination` emits `{items,next_cursor,has_more}`; default limit 20 / max 100; offset pagination forbidden. Invalid cursor → `VALIDATION_ERROR` 400. | ✅ Core deliverable |
| VII. Async Media Pipeline | Out of scope (BE-004); storage is **config only**, no processing. | ✅ N/A |
| VIII. Two-Flavor Config | All new config added to `base/dev/prod` only; flavor-audit test (BE-001 T023) stays green; prod fail-fast extended to storage vars. | ✅ Enforced |
| IX. Data Integrity & Migrations | No business models; `makemigrations --check` must stay clean; empty apps yield no migrations. | ✅ Enforced |
| X. Testing Discipline | Auth isolation, error-catalog mapping, and pagination-envelope are REQUIRED coverage — all exercised here via probe routes; deterministic (DB-down path patched, no real S3). | ✅ Core deliverable |
| XI. Code Quality & Dependency Hygiene | `django-storages`/`boto3` versions verified on PyPI (research R3); pinned in `*.in`, lock recompiled; ruff clean; no secret logging. | ✅ Enforced |

**Gate result**: PASS with one tracked contract action (Principle I patch bump + mobile sync). No
complexity-tracking violations — no new abstraction beyond what a second caller (every future
endpoint) already justifies.

## Project Structure

### Documentation (this feature)

```text
specs/BE-002-backend-foundation/
├── plan.md              # This file
├── research.md          # Phase 0 — decisions R1..R7
├── data-model.md        # Phase 1 — config/contract "entities" (no DB models)
├── quickstart.md        # Phase 1 — runnable validation for US1..US4
├── contracts/
│   └── foundation-contracts.md   # app-tier auth + error envelope + pagination envelope
└── tasks.md             # Phase 2 (/speckit-tasks — NOT created here)
```

### Source Code (repository root)

```text
config/
├── settings/
│   ├── base.py          # + REST_FRAMEWORK block (pagination, exception handler, no global app-key);
│   │                    #   + apps/* in INSTALLED_APPS; + django-storages base; + storage env catalog
│   ├── dev.py           # + local storage fallback (FileSystemStorage / optional MinIO); dev CDN base
│   └── prod.py          # + S3 backend + CDN base from env (required, fail-fast); no third flavor
└── urls.py              # + include app-tier probe route (temporary, see note)

core/
├── errors.py            # NEW — ErrorCode catalog (mirrors api-context.md) + custom APIExceptions
├── exception_handler.py # NEW — centralized DRF handler → { error: { code, message } }
├── pagination.py        # NEW — EnvelopeCursorPagination ({items,next_cursor,has_more}, 20/100)
├── authentication.py    # NEW — AppKeyAuthentication (X-App-Key, raises InvalidAppKey)
├── permissions.py       # NEW — IsAppAuthenticated (app-tier marker permission)
├── api.py               # NEW — AppTierAPIView base (auth+permission wired) for public/IAP views
├── views.py             # + temporary app-tier probe view(s) for foundation validation
├── urls.py              # + probe routes (guarded/temporary)
└── tests/
    ├── test_app_key_auth.py       # NEW — US1 (missing/wrong/valid; no cross-tier fallback; no secret log)
    ├── test_error_envelope.py     # NEW — US2 (404/400/500/app-key; no traceback; prod DEBUG=False)
    ├── test_drf_foundation.py     # NEW — US3 (apps registered/model-less; pagination+handler wired)
    └── test_storage_config.py     # NEW — US4 (dev fallback; prod resolves; prod fail-fast on missing)

apps/
├── __init__.py          # NEW — namespace package for feature apps
├── wallpapers/          # NEW — AppConfig only, name="apps.wallpapers"; migrations/; no models
├── uploads/             # NEW — AppConfig only; migrations/; no models
└── iap/                 # NEW — AppConfig only; migrations/; no models

requirements/
├── base.in / base.txt   # + django-storages[s3]==1.14.6 (boto3 locked transitively); recompiled
```

**Structure Decision**: Single backend service at repo root (matches BE-001). All cross-cutting
request machinery is centralized under `core/` (Principle V) and consumed by the future feature apps
via the `AppTierAPIView` base and DRF `DEFAULT_*` settings — no per-app duplication. Feature apps are
created now as empty shells so BE-003+ add models without re-scaffolding. The probe view/route added
to `core/` for validation is explicitly temporary foundation scaffolding (see research R6) and is
kept out of the product contract.

## Complexity Tracking

> No constitution violations requiring justification. The only deviations from "do nothing new" are
> the two foundation error codes (necessary for FR-018 and handled via the standard contract-bump
> ritual) and the temporary probe route (necessary to make US1/US2 independently testable without
> business endpoints). Neither introduces a new architectural pattern.

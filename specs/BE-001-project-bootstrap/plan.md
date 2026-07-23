# Implementation Plan: Project Bootstrap & 2-Flavor Setup

**Branch**: `BE-001-project-bootstrap` | **Date**: 2026-07-23 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/BE-001-project-bootstrap/spec.md`

## Summary

Stand up a runnable Django + DRF backend skeleton for LiveCanvas that boots under
**exactly two configuration flavors — `dev` and `prod`** — with configuration sourced
from the environment, secrets excluded from version control, liveness + readiness health
endpoints, Django's built-in admin retained for internal staff, and CI gates (lint,
format-check, tests). No business models or endpoints ship in this spec; the app-tier key
middleware, custom admin JWT tier, error-code catalog, business apps, object storage, and
async workers are explicitly deferred to BE-002/BE-004.

## Technical Context

**Language/Version**: Python 3.12

**Primary Dependencies** (versions verified on PyPI 2026-07-23 per Constitution XI):
- Django 5.2 LTS — pin `>=5.2,<5.3` (latest patch 5.2.16; LTS through Apr 2028)
- djangorestframework 3.17.1 (supports Django 5.2)
- psycopg 3.3.x (Django's recommended Postgres driver)
- django-environ 0.14.0 (env parsing incl. `DATABASE_URL` via `env.db()`)
- gunicorn 26.0.0 (prod WSGI server)
- whitenoise 6.12.0 (serve Django-admin static in prod)
- python-json-logger 4.1.0 (prod structured JSON logging)

**Dev/Test Dependencies**: pytest 9.1.x, pytest-django 4.12.0 (needs `pytest>=7` ✓),
factory_boy 3.3.3, ruff 0.15.x. Installer/compiler: `uv` (0.11.x).

**Storage**: PostgreSQL 16 — `dev` via Docker Compose (single command), `prod` via managed
instance addressed by `DATABASE_URL`.

**Testing**: `pytest` + `pytest-django`; health endpoint tests including the DB-unavailable
readiness path (FR-018).

**Target Platform**: Linux server (containerized), Python 3.12.

**Project Type**: Web service (backend REST API skeleton).

**Performance Goals**: None functional in this spec. Operational: health endpoints respond
< 100 ms; clean-machine setup to first successful liveness < 15 min (SC-001).

**Constraints**: Exactly two flavors (no third); no business logic; all secrets from env;
`prod` fails fast on missing required config; `manage.py check --deploy` clean on `prod`.

**Scale/Scope**: Skeleton only — one project package (`config/`) + one thin support app
(`core/`) hosting health. No custom persisted models.

## Constitution Check

*GATE: evaluated against constitution v1.0.0 before and after design. No violations.*

| Principle | Relevance to BE-001 | Status |
|---|---|---|
| I. Contract-First & Dual-Repo Sync | No product API shipped. Health endpoints are **operational**, intentionally NOT added to `contracts/openapi.yaml`. | ✅ Pass |
| II. Two-Tier Auth Isolation & Account-Less | App-tier key + custom admin JWT deferred (BE-002/003). Django built-in admin is an **internal-staff** session tool, separate from both API tiers and from account-less app end-users (clarified in spec). | ✅ Pass |
| III. Entitlement at Download Edge | N/A this spec. | ✅ N/A |
| IV. Structured Errors & Catalog | Error handler/catalog deferred (BE-002). Health returns simple status bodies; no error-catalog surface introduced. | ✅ Pass |
| V. Feature-First App Architecture | Only `config/` + `core/`; no cross-app internal imports; health logic lives in the `core` app, not in project urls. | ✅ Pass |
| VI. Cursor Pagination & Envelopes | N/A (no list endpoints). | ✅ N/A |
| VII. Async Media Pipeline Safety | `config/celery.py` is a bare app stub — no tasks, no worker, no broker required to run. | ✅ Pass |
| VIII. Two-Flavor Configuration | **Core deliverable.** `base` + exactly `dev`/`prod`; no `staging`. Enforced by FR-002 + test/audit. | ✅ Pass |
| IX. Data Integrity & Migrations | Only Django contrib migrations (auth/sessions/admin/contenttypes). No custom destructive migrations. | ✅ Pass |
| X. Testing Discipline | Health liveness/readiness tests required (FR-018); deterministic, DB-boundary controlled. | ✅ Pass |
| XI. Dependency Hygiene | Versions looked up on PyPI at plan time; Django 6.0-vs-5.2-LTS major decision documented in research.md; caret/compatible pins; lock files committed. | ✅ Pass |

**Result**: PASS (no deviations). Complexity Tracking table intentionally empty.

## Project Structure

### Documentation (this feature)

```text
specs/BE-001-project-bootstrap/
├── spec.md              # feature spec (+ Clarifications)
├── plan.md              # this file
├── research.md          # Phase 0 — version & pattern decisions
├── data-model.md        # Phase 1 — config artifacts (no custom DB models)
├── quickstart.md        # Phase 1 — runnable validation guide
├── contracts/
│   └── health-endpoints.md   # ops health contract (not product API)
└── checklists/
    └── requirements.md  # spec quality checklist (16/16)
```

### Source Code (repository root)

```text
config/                       # Django project package
├── __init__.py               # exposes the (stub) Celery app lazily
├── settings/
│   ├── __init__.py
│   ├── base.py               # shared settings; reads env via django-environ
│   ├── dev.py                # DEBUG=True, open hosts, relaxed security, console logs
│   └── prod.py               # DEBUG=False, strict hosts, security headers, JSON logs, whitenoise
├── urls.py                   # includes admin/ + core.health urls
├── wsgi.py                   # prod entrypoint (gunicorn config.wsgi:application)
├── asgi.py
└── celery.py                 # bare Celery app stub (no tasks/broker wired yet)

core/                         # thin support app (INSTALLED_APPS), no models
├── __init__.py
├── apps.py
├── urls.py                   # /health, /health/ready
├── views.py                  # liveness + readiness (DB ping)
└── tests/
    └── test_health.py        # liveness/readiness incl. DB-down case

requirements/
├── base.in   base.txt        # Django, DRF, psycopg, django-environ, gunicorn, whitenoise, json-logger
├── dev.in    dev.txt         # -r base + pytest(-django), factory_boy, ruff
└── prod.in   prod.txt        # -r base (prod extras if any)

.env.dev.example              # committed template
.env.prod.example             # committed template
docker-compose.yml            # Postgres only (Redis deferred to BE-004)
pyproject.toml                # ruff + pytest config, project metadata
.github/workflows/ci.yml      # uv → ruff check + ruff format --check + pytest (dev flavor)
manage.py                     # DJANGO_SETTINGS_MODULE default = config.settings.dev
CLAUDE.md                     # runtime guidance mirroring the constitution
```

**Structure Decision**: Single backend service. The project package is `config/` (settings
split into `base`/`dev`/`prod`). Health lives in a dedicated thin `core` app (satisfies
Principle V — logic in an app, not in project `urls.py`), which has **no models** so it adds
no migrations. Business apps (`wallpapers`/`uploads`/`iap`) are deliberately absent until
BE-002.

## Complexity Tracking

> No Constitution Check violations — table intentionally empty.

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| — | — | — |

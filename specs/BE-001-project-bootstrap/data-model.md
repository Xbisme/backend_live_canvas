# Phase 1 Data Model: Project Bootstrap & 2-Flavor Setup

This spec introduces **no custom persisted business models**. The only database tables that
exist after `migrate` come from Django's bundled contrib apps (retained per the spec
clarification: built-in admin as an internal-staff tool). The "entities" below are therefore
**configuration artifacts**, not application data.

## Persisted tables (from Django contrib migrations only)

| Source app | Tables (representative) | Purpose |
|---|---|---|
| `contenttypes` | `django_content_type` | framework bookkeeping |
| `auth` | `auth_user`, `auth_group`, `auth_permission` | internal-staff accounts for the built-in admin |
| `admin` | `django_admin_log` | admin action audit |
| `sessions` | `django_session` | admin session store |

No custom models, no custom migrations, no destructive operations. Business models
(`Category`, `Tag`, `Wallpaper`, `Collection`, IAP entities) arrive in later specs.

## Configuration artifacts (not DB rows)

### Configuration Flavor

Exactly two, layered on a shared `base`.

| Attribute | `dev` | `prod` |
|---|---|---|
| `DEBUG` | `True` | `False` |
| `ALLOWED_HOSTS` | open / localhost | strict, from env |
| Security headers (SSL redirect, HSTS, secure cookies) | off | on |
| Static serving | Django dev server | whitenoise + `collectstatic` |
| Logging | verbose console | structured JSON (stdout) |
| Database | Postgres via docker-compose | managed Postgres via `DATABASE_URL` |
| Missing required env value | tolerated (dev defaults) | **fail-fast** at startup |

**Invariant**: the settings package contains only `base`, `dev`, `prod` (+ `__init__`). Any
additional flavor module is a constitution violation (Principle VIII) and is asserted against
in tests (SC-003).

### Environment Value Catalog (read via `django-environ`)

| Key | Flavors | Required | Notes |
|---|---|---|---|
| `DJANGO_SETTINGS_MODULE` | both | yes (defaulted to `config.settings.dev` in entrypoints) | flavor selector |
| `SECRET_KEY` | both | **prod: yes (no default)**; dev: defaulted | fail-fast on prod if missing |
| `DATABASE_URL` | both | **prod: yes (no default)**; dev: defaulted to local docker DB | parsed by `env.db()` |
| `ALLOWED_HOSTS` | both | prod: yes | comma-separated list |
| `X_APP_KEY` | both | no (**declared, not enforced**) | reserved for BE-002 app-tier auth |
| `DJANGO_LOG_LEVEL` | both | no (defaulted) | dev→`DEBUG`, prod→`INFO` |

Only `.env.dev.example` and `.env.prod.example` are committed; real `.env.dev`/`.env.prod`
are git-ignored.

### Health Signals (in-memory/runtime, not persisted)

| Signal | Endpoint | Meaning | Success | Failure |
|---|---|---|---|---|
| Liveness | `GET /health` | process is serving | `200 {"status":"ok"}` | (process down → no response) |
| Readiness | `GET /health/ready` | DB dependency reachable | `200 {"status":"ready"}` | `503 {"status":"unavailable"}` |

See [contracts/health-endpoints.md](contracts/health-endpoints.md).

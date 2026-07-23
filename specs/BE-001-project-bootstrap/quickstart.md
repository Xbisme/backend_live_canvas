# Quickstart & Validation Guide: BE-001 Project Bootstrap

Runnable steps that prove the skeleton satisfies the spec's acceptance scenarios. This is a
**validation guide**, not an implementation guide — code lands via `tasks.md` / implementation.

## Prerequisites

- Python 3.12
- `uv` (dependency installer/compiler)
- Docker + Docker Compose (for the local `dev` Postgres)

## Setup (dev flavor)

```bash
# 1. Install dev dependencies (from committed pinned lock)
uv pip sync requirements/dev.txt          # into an active venv, or: uv venv && uv pip sync ...

# 2. Local config
cp .env.dev.example .env.dev              # adjust if needed; sane local defaults provided

# 3. Start the local database (Postgres only)
docker compose up -d db

# 4. Apply contrib migrations (auth/admin/sessions/contenttypes)
python manage.py migrate                  # defaults to config.settings.dev

# 5. (Optional) Create the initial internal-staff superuser for Django admin (FR-019)
python manage.py createsuperuser          # internal staff only — not an app end-user account

# 6. Run
python manage.py runserver
```

> The built-in admin is an **internal-staff** tool (`/admin/`). Creating a superuser here does
> not conflict with the account-less handling of app end-users (see spec Clarifications).

## Validate — User Story 1 (dev flavor)

```bash
curl -sS -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8000/health
#   expect: 200   (body {"status":"ok"})   → US1 scenario 1

curl -sS http://127.0.0.1:8000/health/ready
#   expect: {"status":"ready"} with 200    → US1 scenario 2 (DB up)
```

Simulate DB down (readiness fails, liveness stays up) → US1 scenario 3:

```bash
docker compose stop db
curl -sS -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8000/health/ready   # expect: 503
curl -sS -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8000/health         # expect: 200
docker compose start db
```

Flavor audit (exactly two) → US1 scenario 4 / SC-003:

```bash
ls config/settings/    # expect only: __init__.py base.py dev.py prod.py  (NO staging.py)
```

## Validate — User Story 2 (prod flavor)

```bash
cp .env.prod.example .env.prod
# edit .env.prod: set SECRET_KEY, DATABASE_URL, ALLOWED_HOSTS (required — no defaults on prod)

export DJANGO_SETTINGS_MODULE=config.settings.prod
python manage.py check --deploy
#   expect: no critical issues            → US2 scenario 2 / SC-005

python manage.py collectstatic --noinput  # admin static gathered for whitenoise
```

Fail-fast check → US2 scenario 3 / FR-011:

```bash
env DJANGO_SETTINGS_MODULE=config.settings.prod SECRET_KEY= DATABASE_URL= \
  python manage.py check
#   expect: startup error (ImproperlyConfigured) — does NOT boot with insecure defaults
```

## Validate — User Story 3 (quality gates)

```bash
ruff check .
ruff format --check .
pytest                                     # health tests incl. DB-down readiness (FR-018)
```

Expected: all three pass on a clean baseline (SC-007). CI (`.github/workflows/ci.yml`) runs the
same three on every push with a Postgres service container.

## Success-criteria coverage

| Criterion | Proven by |
|---|---|
| SC-001 (setup < 15 min, no source edits) | Setup section end-to-end |
| SC-002 (boots under both flavors) | US1 run + US2 `check --deploy` |
| SC-003 (exactly two flavors) | flavor audit `ls config/settings/` |
| SC-004 (readiness reflects DB state) | US1 scenario 2 + 3 |
| SC-005 (prod deploy check clean) | `manage.py check --deploy` |
| SC-006 (no real secrets committed) | only `.env.*.example` tracked (`git ls-files`) |
| SC-007 (CI passes clean / fails on violation) | ruff + pytest locally and in CI |
| SC-008 (reproducible pinned deps) | `uv pip sync requirements/*.txt` |

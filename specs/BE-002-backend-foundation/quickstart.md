# Quickstart Validation: BE-002 Backend Foundation

Runnable checks proving the foundation works end-to-end. Assumes BE-001 setup done and the local
Postgres reachable at `DATABASE_URL` (see [CLAUDE.md](../../CLAUDE.md) Common commands). Run from repo
root with the dev venv active.

## Prerequisites

```bash
uv pip sync requirements/dev.txt          # picks up django-storages[s3]==1.14.6 + boto3
cp .env.dev.example .env.dev              # if not already present
docker compose up -d db                   # local Postgres (or an equivalent reachable DB)
python manage.py migrate                  # contrib only — feature apps add no migrations
```

---

## User Story 1 — App-tier `X-App-Key` gate

```bash
python manage.py runserver

# no key → 401 INVALID_APP_KEY
curl -si localhost:8000/_probe/app-tier | head -n1
curl -s  localhost:8000/_probe/app-tier            # {"error":{"code":"INVALID_APP_KEY",...}}

# wrong key → 401 INVALID_APP_KEY
curl -s -H 'X-App-Key: nope' localhost:8000/_probe/app-tier

# only a Bearer token, no valid app key → still 401 INVALID_APP_KEY (no cross-tier fallback)
curl -s -H 'Authorization: Bearer whatever' localhost:8000/_probe/app-tier

# correct key (matches X_APP_KEY in .env.dev) → 200 {"ok": true}
curl -s -H "X-App-Key: $(grep '^X_APP_KEY=' .env.dev | cut -d= -f2)" localhost:8000/_probe/app-tier
```

**Expected**: first three return HTTP 401 with the `INVALID_APP_KEY` envelope; the last returns
`200 {"ok": true}`. Confirm the server log does **not** print the key value.

---

## User Story 2 — Structured error envelope

```bash
# 404 → NOT_FOUND
curl -s localhost:8000/_probe/does-not-exist          # {"error":{"code":"NOT_FOUND",...}}

# validation error probe → VALIDATION_ERROR (400)
curl -s -H "X-App-Key: $KEY" 'localhost:8000/_probe/validation'

# unhandled exception probe → SERVER_ERROR (500), NO traceback in body
curl -s -H "X-App-Key: $KEY" localhost:8000/_probe/boom
```

**Expected**: each body matches `{ "error": { "code", "message" } }` with the right code; the 500 body
contains **no** stack trace or Django debug page. Re-run the 500 probe under the prod flavor to confirm
identical safe behavior:

```bash
DJANGO_SETTINGS_MODULE=config.settings.prod \
  DATABASE_URL=... SECRET_KEY=... ALLOWED_HOSTS=testserver \
  AWS_STORAGE_BUCKET_NAME=... CDN_BASE_URL=... AWS_ACCESS_KEY_ID=... AWS_SECRET_ACCESS_KEY=... \
  python -c "import django,os; django.setup(); print('prod import OK')"
```

---

## User Story 3 — DRF + feature-app skeleton

```bash
# three feature apps registered and model-less
python manage.py shell -c "from django.apps import apps; print([a.label for a in apps.get_app_configs() if a.name.startswith('apps.')])"

# no missing migrations (empty apps produce none)
python manage.py makemigrations --check --dry-run

# pagination + exception handler are the configured defaults
python manage.py shell -c "from rest_framework.settings import api_settings as s; print(s.DEFAULT_PAGINATION_CLASS, s.DEFAULT_PAGINATION_CLASS().page_size); print(s.EXCEPTION_HANDLER)"
```

**Expected**: the three labels `wallpapers, uploads, iap`; "No changes detected"; the pagination class
is `EnvelopeCursorPagination` with `page_size=20`; the handler is `structured_exception_handler`.

---

## User Story 4 — Storage / CDN per flavor

```bash
# dev boots on the local storage fallback with no S3 creds
python manage.py shell -c "from django.core.files.storage import default_storage; print(default_storage.__class__.__name__)"

# prod resolves S3 storage when required vars are set (see US2 prod import block)

# prod fails fast when a required storage var is missing
DJANGO_SETTINGS_MODULE=config.settings.prod SECRET_KEY=x DATABASE_URL=postgres://u:p@h/db \
  ALLOWED_HOSTS=h python -c "import django; django.setup()"   # → ImproperlyConfigured (missing bucket/CDN)
```

**Expected**: dev prints `FileSystemStorage` (fallback); prod with full vars imports clean and uses
`S3Storage`; prod with a missing required storage var raises `ImproperlyConfigured` at setup.

---

## Full gate (pre-commit)

```bash
ruff check . && ruff format --check .
pytest
python manage.py makemigrations --check --dry-run
DJANGO_SETTINGS_MODULE=config.settings.prod python manage.py check --deploy   # with a valid prod env
```

**Expected**: ruff clean; all tests pass (incl. `test_app_key_auth`, `test_error_envelope`,
`test_drf_foundation`, `test_storage_config`, and BE-001's flavor-audit); no migration drift; deploy
check reports no critical issues.

---

## Success mapping

| Check | Spec criterion |
|---|---|
| US1 four curls | SC-001, SC-002, FR-012..FR-016 |
| US2 envelope + prod 500 | SC-003, FR-017..FR-019 |
| US3 apps + defaults + migrations | SC-005, FR-001..FR-005 |
| US4 dev fallback / prod resolve / prod fail-fast | SC-004, SC-007, FR-006..FR-011 |
| flavor-audit test | SC-006, FR-020 |
| ruff + pytest | SC-008 |

# Phase 0 Research: Project Bootstrap & 2-Flavor Setup

All versions looked up on PyPI on **2026-07-23** (Constitution Principle XI — Dependency
Hygiene). No versions guessed or carried from memory.

## D1. Django version — 5.2 LTS vs latest 6.0 (MAJOR-version review)

- **Decision**: Pin Django to the **5.2 LTS** line — `Django>=5.2,<5.3` (latest patch at
  lookup: **5.2.16**).
- **Rationale**: Latest stable on PyPI is **6.0.7**, but Django 6.0 is a *regular* release
  with mainstream support ending ~Dec 2026. **5.2 is the current LTS**, supported with
  security patches through **April 2028**. For a backend heading to production and expected
  to run for years, LTS minimizes forced upgrade churn. This matches the user's locked
  decision. psycopg 3 and DRF 3.17 both support 5.2.
- **Alternatives considered**:
  - *Django 6.0.7 (latest)*: newest features, but short support window → forced 6.x upgrade
    within months. Rejected: not worth the churn for a foundational skeleton.
  - *Django 4.2 LTS*: older LTS (EOL Apr 2026) — already near end of life. Rejected.
- **Constraint**: pin `>=5.2,<5.3` so `uv pip compile` tracks the latest 5.2 security patch
  without jumping to 6.x.

## D2. REST framework — DRF 3.17.1

- **Decision**: `djangorestframework==3.17.1` (latest).
- **Rationale**: PyPI classifiers confirm support for Django 4.2/5.0/5.1/5.2/6.0 — compatible
  with our 5.2 LTS pin and forward-compatible if we later move to 6.x. Supersedes the earlier
  "3.16" note (3.17 is now latest).
- **Note**: DRF is added at bootstrap so `core` health views can use DRF conventions, but no
  serializers/viewsets/auth classes are configured yet (deferred to BE-002).

## D3. Postgres driver — psycopg 3

- **Decision**: `psycopg[binary]` 3.3.x for dev convenience; plain `psycopg` (C build) an
  option for prod images.
- **Rationale**: psycopg 3 is Django's recommended driver since 4.2. `[binary]` avoids local
  build toolchain in dev; prod containers may prefer the non-binary build.
- **Alternatives**: `psycopg2-binary` — legacy, rejected (psycopg 3 is current, better async
  story for any future needs).

## D4. Settings split & flavor selection

- **Decision**: `config/settings/{base,dev,prod}.py`. Flavor chosen via
  `DJANGO_SETTINGS_MODULE`; `manage.py`, `wsgi.py`, `asgi.py` default to
  `config.settings.dev`. Exactly two flavor modules exist — **no `staging.py`**.
- **Rationale**: Standard, reviewable split (Principle VIII). Defaulting local entrypoints to
  `dev` prevents accidentally running prod settings locally (edge case in spec).
- **Enforcement**: a test/audit asserts the settings package contains only
  `base/dev/prod` (+`__init__`) — catches a stray third flavor (SC-003).

## D5. Environment loading & the env catalog

- **Decision**: `django-environ`. `base.py` reads env; each flavor loads its `.env.<flavor>`
  file when present (real files git-ignored; only `.env.*.example` committed).
- **Env catalog** (FR-006): `DJANGO_SETTINGS_MODULE`, `SECRET_KEY`, `DATABASE_URL`,
  `ALLOWED_HOSTS`, `X_APP_KEY` (declared, **not enforced** yet — reserved for BE-002),
  `DJANGO_LOG_LEVEL`.
- **Fail-fast (FR-011)**: on `prod`, `SECRET_KEY` and `DATABASE_URL` are read with **no
  default** so a missing value raises at import time (`ImproperlyConfigured`), never boots
  insecure. On `dev`, sane local defaults are allowed.
- **DATABASE_URL**: parsed by `env.db()` — no extra `dj-database-url` dependency needed.

## D6. Health checks — liveness vs readiness

- **Decision**: Two endpoints in the `core` app:
  - `GET /health` (liveness) — always `200 {"status": "ok"}` if the process serves.
  - `GET /health/ready` (readiness) — runs a trivial DB query
    (`connection.cursor().execute("SELECT 1")`); `200 {"status": "ready"}` on success,
    `503 {"status": "unavailable"}` on DB error.
- **Rationale**: Distinguishing liveness from readiness is the standard orchestration pattern
  (k8s/other) and directly satisfies the spec's DB-down edge case. Kept dependency-light —
  only the DB is checked (the only backing service this spec provisions).
- **Auth**: unauthenticated in this spec (app-tier key middleware doesn't exist yet). When
  BE-002 adds `X-App-Key`, health paths will be exempted — noted as a BE-002 follow-up.
- **Not in product contract**: these are ops endpoints; they are **not** added to
  `contracts/openapi.yaml` (Principle I keeps the product contract screen-driven).

## D7. Production hardening (prod flavor)

- **Decision**: `prod.py` sets `DEBUG=False`; `ALLOWED_HOSTS` from env; `SECURE_SSL_REDIRECT`,
  `SECURE_HSTS_SECONDS` (+ include-subdomains/preload), `SESSION_COOKIE_SECURE`,
  `CSRF_COOKIE_SECURE`, `SECURE_PROXY_SSL_HEADER` (TLS terminated upstream);
  `SECURE_CONTENT_TYPE_NOSNIFF`. whitenoise middleware + `STATIC_ROOT` + `collectstatic` for
  admin static. Structured JSON logging via `python-json-logger`.
- **Rationale**: Passes `manage.py check --deploy` with no critical findings (FR-012/SC-005).
  whitenoise is needed only because Django's built-in admin (retained per clarification) ships
  static assets.
- **Alternatives**: serving static via CDN/S3 — deferred to BE-002 (django-storages). For a
  bootstrap, whitenoise is the simplest correct choice.

## D8. Logging

- **Decision**: `dev` → verbose human-readable console handler at `DJANGO_LOG_LEVEL`
  (default `DEBUG`). `prod` → JSON formatter (`python-json-logger`) to stdout at default
  `INFO`. No secrets/credentials logged (Constitution XI).
- **Rationale**: JSON logs are ingestible by prod log pipelines; console logs aid local dev.

## D9. Dependency workflow — uv + committed requirements

- **Decision**: Author top-level, loosely-constrained deps in `requirements/{base,dev,prod}.in`;
  compile to fully-pinned `requirements/{base,dev,prod}.txt` via `uv pip compile`. Commit both
  `.in` and `.txt`. `dev.in`/`prod.in` start with `-r base.in`.
- **Rationale**: Satisfies Constitution XI (pinned, reproducible, committed lock state) and the
  mandated `requirements/*.txt` structure, while using uv for speed. `uv pip compile` records
  full transitive pins.
- **Alternatives**: plain pip (no transitive pinning — rejected); Poetry/uv-native
  `pyproject`+`uv.lock` (diverges from the constitution's required `requirements/*.txt`
  structure — rejected).

## D10. Local services — Docker Compose (Postgres only)

- **Decision**: `docker-compose.yml` defines **only** a Postgres 16 service (named volume,
  healthcheck, port mapped for local access). Redis/cache/queue **not** included.
- **Rationale**: `dev` needs DB parity with prod (Principle VIII / spec parity goal). Redis is
  only needed once Celery lands in BE-004; adding it now would be premature (Simplicity).

## D11. Testing setup

- **Decision**: `pytest` + `pytest-django` (`DJANGO_SETTINGS_MODULE=config.settings.dev` for
  the suite), config in `pyproject.toml`. `factory_boy` available for later specs. Health tests
  cover: liveness 200; readiness 200 (DB up); readiness 503 (DB down, simulated by patching the
  DB check to raise).
- **Rationale**: Meets FR-018/SC-004 deterministically without needing a real DB outage — the
  readiness failure path is unit-tested by forcing the connection check to raise.
- **Compat check**: pytest-django 4.12.0 requires `pytest>=7`; pytest 9.1.x satisfies it.

## D12. CI — GitHub Actions

- **Decision**: `.github/workflows/ci.yml` on push/PR: set up Python 3.12, install `uv`, sync
  `requirements/dev.txt`, spin a Postgres service container, then run
  `ruff check .`, `ruff format --check .`, `pytest`. Pipeline fails if any gate fails.
- **Rationale**: Matches the constitution's Testing Gates. Runs on the `dev` flavor (tests use
  dev settings). Postgres service container lets readiness "DB up" test pass in CI.

# CLAUDE.md — Runtime guidance for the LiveCanvas backend

Runtime rules for working in this repo. This mirrors the authoritative constitution at
[.specify/memory/constitution.md](.specify/memory/constitution.md) — when in doubt, the
constitution wins. Planning state lives in [.claude/](.claude/).

## What this backend is

Django + DRF API for the LiveCanvas live-wallpaper app. Serves public content, admin
content management + upload pipeline, and self-hosted IAP verification. **No app user/account
system** — premium entitlement is resolved per store `transaction_id`.

## Non-negotiable runtime rules

1. **Two-tier auth isolation.** `X-App-Key` authenticates the *app* (public + IAP endpoints);
   `Authorization: Bearer <jwt>` authenticates an *admin* (`/admin/*` custom API). Never mix
   the two tiers on one endpoint or let one fall back to the other. Webhooks are authenticated
   only by verifying their signature. (App-tier `X-App-Key` auth landed in BE-002 via
   `core.api.AppTierAPIView` + `core.authentication.AppKeyAuthentication`, opt-in per tier —
   never a global default; admin Bearer JWT arrives in BE-004. Webhooks: BE-005.)
   - Django's built-in admin (`/admin/`) is a **separate internal-staff** tool (session auth).
     It is distinct from both API tiers and from the account-less handling of app end-users.

2. **Account-less entitlement.** Premium access is derived from a verified store
   `transaction_id`, never from a user record or session. Enforce entitlement at the
   `download-url` edge (short-lived presigned URLs), not merely at list time.

3. **Structured errors & the error-code catalog.** Every error response is
   `{ "error": { "code": "<CODE>", "message": "..." } }` with `code` from the catalog in
   `.claude/api-context.md`. Produce errors via the centralized DRF exception handler — never
   ad-hoc error bodies, never raw exceptions/tracebacks to clients. (Handler landed in BE-002:
   `core.exception_handler.structured_exception_handler` + catalog in `core.errors`.)

4. **Two-flavor discipline.** Exactly two settings flavors exist: `dev` and `prod`
   (`config/settings/{base,dev,prod}.py`). **Never** add a `staging.py` or any third flavor.
   Select via `DJANGO_SETTINGS_MODULE`; `manage.py` defaults to dev. All config/secrets come
   from the environment (`.env.dev` / `.env.prod`, git-ignored; only `*.example` committed).

5. **Contract-first, dual-repo sync.** API changes flow `docs/screen-inventory.md` →
   `contracts/openapi.yaml` + `.claude/api-context.md` (bump version) → code, then copy both
   contract files verbatim to `livecanvas-mobile`. Health endpoints are operational and are
   **not** part of that product contract.

6. **Dependency hygiene.** Look up the latest stable version on PyPI before adding/upgrading a
   package; never guess versions. Pin in `requirements/*.in`, compile with
   `uv pip compile` to `requirements/*.txt`, commit both. Review CHANGELOG for major bumps.

7. **Secrets.** Never log secrets, `X-App-Key`, admin tokens, receipts, or signed payloads.

## Common commands

```bash
# Setup (dev)
uv venv && uv pip sync requirements/dev.txt
cp .env.dev.example .env.dev
docker compose up -d db
python manage.py migrate

# Create the initial internal-staff superuser for Django admin (FR-019)
python manage.py createsuperuser

# Run
python manage.py runserver          # dev flavor (default)

# Prod flavor checks
export DJANGO_SETTINGS_MODULE=config.settings.prod   # requires a valid .env.prod
python manage.py check --deploy

# Quality gates (run before every commit)
ruff check . && ruff format --check .
pytest
python manage.py makemigrations --check --dry-run
```

## Layout

- `config/` — project package (`settings/{base,dev,prod}`, `urls`, `wsgi`, `asgi`,
  `celery` placeholder for BE-004)
- `core/` — thin support app (operational health endpoints; no models)
- `requirements/` — `*.in` (authored) + `*.txt` (uv-compiled locks); both committed
- `specs/` — speckit SDD output per `BE-NNN-*`
- `.claude/` — planning docs (roadmap, contexts, api-context)

## Communication

Vietnamese between the user and Claude; English for code, comments, commits, and identifiers.

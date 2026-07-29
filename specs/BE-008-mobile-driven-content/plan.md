# Implementation Plan: Mobile-Driven Content — Browse Sections & Wallpaper Description (BE-008)

**Branch**: `BE-008-mobile-driven-content` | **Date**: 2026-07-27 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/BE-008-mobile-driven-content/spec.md`

## Summary

Two mobile-driven gaps in one release, both inside `apps/wallpapers`:

**(A)** Make `Wallpaper.description` real — the contract has declared it `nullable` since
v0.6.0 while the backend returns nothing. Adds the field, exposes it on every public wallpaper
payload, and lets an operator write it at registration **and** edit it afterwards (the entire
397-wallpaper seeded catalogue predates the field, so without an edit path the feature would be
invisible on real data).

**(B)** Give the app's Browse screen the titled, curated sections its design calls for, by
letting an operator flag existing `Collection`s onto the home screen with an order, and serving
the whole screen from one new `GET /home`. **No new model** — a section *is* a collection with
`show_on_home=True`; collections already carry title, cover, accent colour, premium flag, and
ordered membership.

Technical approach: two new `Collection` fields + one new `Wallpaper` field in a single additive
migration; one new read service that assembles the screen in a **constant** number of queries
(prefetch, then cap/skip in Python); one new app-tier view; a one-field admin PATCH. Contract
bumps **v0.6.0 → v0.7.0** — and unlike the last two bumps this one changes path + schema, so the
mobile client must be regenerated.

## Technical Context

**Language/Version**: Python 3.11 (locks compiled `--python-version 3.11`)

**Primary Dependencies**: Django 5.2 + DRF 3.17.1 — **no new dependency** (research D8). Uses
`django.db.models.Prefetch` and `pytest-django`'s `django_assert_num_queries`, both already
present.

**Storage**: PostgreSQL. One additive migration on existing `apps/wallpapers` tables — no new
table (see [data-model.md](data-model.md)). No object-storage change; `/home` returns no
download URLs.

**Testing**: `pytest-django` with the existing `apps/wallpapers/tests/conftest.py` fixtures
(`api` = X-App-Key client, `anon`, `admin_client`). New `test_home.py`, plus cases added to
`test_admin_curated.py` and `test_admin_wallpapers.py` (research D10).

**Target Platform**: Linux server (Django API), two flavors dev/prod.

**Project Type**: Web service (Django + DRF API), single backend project.

**Performance Goals**: `GET /home` p95 < 300 ms measured at the API boundary on a full screen
(10 sections × 10 items) against the 397-wallpaper catalogue, **without any cache** (spec
SC-005, clarified 2026-07-27). Query count constant regardless of result size (SC-004).

**Constraints**: response bounded hard at 10 sections × 10 wallpapers, enforced on read, never
rejecting an operator write (spec FR-006/FR-007). No new error codes. No entitlement logic —
`/home` neither accepts nor consults `transaction_id`.

**Scale/Scope**: 1 new public endpoint, 1 new admin verb on an existing route, 2 modified admin
bodies, 3 new model fields, 1 migration, 0 new dependencies. Catalogue unchanged (397
wallpapers / 5 collections).

## Constitution Check

*GATE: evaluated pre-Phase 0 and re-checked post-Phase 1 design.*

| Principle | Gate | Status |
|---|---|---|
| I. Contract-First & Dual-Repo Sync | Screen inventory → contract → code; version bumped; synced to mobile | ✅ Delta drafted in [contracts/home-contract-delta.md](contracts/home-contract-delta.md) with an explicit edit order; contract tasks precede code tasks; sync + mobile changelog are explicit tasks. Bump **v0.7.0** flagged as shape-changing (regeneration mandatory). |
| II. Two-Tier Auth Isolation & Account-Less | `/home` app-tier only; admin PATCH admin-tier only; no mixing | ✅ `HomeView(AppTierAPIView)`; PATCH added to the existing `AdminWallpaperDetailView(AdminTierAPIView)`. No shared base, no fallback. `/home` consults no user and no `transaction_id`. |
| III. Entitlement at Download Edge | Gate stays exclusively at `download-url` | ✅ `/home` returns metadata only — no download URLs, no presigning, no entitlement check. `is_premium` is display data, as on `/collections` today. `build_download_url` untouched. |
| IV. Structured Errors & Catalog | Centralized handler, catalog codes only | ✅ No new codes (FR-022). `/home` has no failure mode of its own — empty is `{"sections": []}` + 200. PATCH reuses `Http404` and the existing admin auth errors through the existing handler. |
| V. Feature-First App Architecture | Logic in services; thin views; no cross-app internals | ✅ `services.build_home_sections()` + `admin_services.update_wallpaper_description()`; views stay 3–5 lines like their neighbours. Audit written via the public `apps.audit.services.record`. No new app — this is squarely the content domain. |
| VI. Cursor Pagination & Envelopes | Large lists cursor-paginated; curated lists whole | ✅ `/home` is a **bounded curated** surface (≤10×10, hard-capped on read) returned whole, exactly like `/categories`, `/tags`, `/collections`, `/collections/{id}`. No offset paging anywhere; existing cursor endpoints untouched. |
| VII. Async Media Pipeline Safety | Heavy work async | ✅ N/A — no file handling, no upload, no transcode. Both new paths are pure DB reads/writes. |
| VIII. Two-Flavor Config | dev/prod only; config from env | ✅ No new settings. Caps are module constants so dev and prod cannot serve a different number than the contract advertises (research D6). |
| IX. Data Integrity & Migrations | Non-destructive, reversible; curated integrity preserved | ✅ Single additive migration with safe defaults (`NULL` / `False` / `0`) so every existing row is valid on apply. Ordered `CollectionItem` membership untouched. The description edit path is structurally incapable of touching curated relationships (research D2). |
| X. Testing Discipline | Auth isolation, contract shape, curated integrity covered | ✅ Matrix in [quickstart.md](quickstart.md): ordering + tie-break, caps, empty-section skipping, hidden-item exclusion, premium visibility, tier isolation, query-count assertion, description invariants, audit. |
| XI. Code Quality & Dependency Hygiene | ruff clean; deps verified; no secret logging | ✅ No new dependency to verify. Type hints on new functions. Description text is content rather than a secret — but it is deliberately kept out of audit metadata anyway (data-model §4). |

**Result**: PASS, no violations. Complexity Tracking table below intentionally empty.

**Post-Phase 1 re-check**: still PASS. The design added no model, no app, no dependency, no
settings key, and no error code. The one judgement call worth naming — capping in Python after a
prefetch rather than in SQL — is recorded with its escape hatch in research D4 and touches no
principle.

## Project Structure

### Documentation (this feature)

```text
specs/BE-008-mobile-driven-content/
├── plan.md                          # This file
├── spec.md                          # Feature spec (3 clarifications integrated)
├── research.md                      # Phase 0 — D1..D10
├── data-model.md                    # Phase 1 — field-level changes + selection rules
├── quickstart.md                    # Phase 1 — run/validate guide + test matrix
├── contracts/
│   └── home-contract-delta.md       # Phase 1 — exact v0.6.0 → v0.7.0 edits
├── checklists/
│   └── requirements.md              # Spec quality checklist (16/16)
└── tasks.md                         # Phase 2 output (/speckit-tasks — NOT created here)
```

### Source Code (repository root)

Existing layout; this feature touches one app plus the contract files.

```text
apps/wallpapers/
├── models.py                 # + Wallpaper.description, Collection.show_on_home/home_position, coll_home_idx
├── migrations/
│   └── 0004_home_sections_and_description.py   # NEW — additive, reversible
├── services.py               # + HOME_MAX_SECTIONS / HOME_MAX_ITEMS_PER_SECTION, build_home_sections()
├── serializers.py            # + "description" in WallpaperSerializer.Meta.fields; + HomeSectionSerializer
├── views.py                  # + HomeView(AppTierAPIView)
├── urls.py                   # + path("home", …)
├── admin_serializers.py      # + description on create; + AdminWallpaperUpdateSerializer; + home fields on AdminCollectionSerializer
├── admin_services.py         # + update_wallpaper_description()
├── admin_views.py            # + AdminWallpaperDetailView.patch; create passes description
├── admin.py                  # Django-admin: surface the new fields for internal staff
└── tests/
    ├── test_home.py                 # NEW
    ├── test_admin_curated.py        # + home flag/order/audit cases
    ├── test_admin_wallpapers.py     # + description create/edit/clear cases
    └── factories.py                 # + description / home-flag support

core/tests/test_tier_isolation.py    # + /home (app tier) and PATCH /admin/wallpapers/{id} (admin tier)

.claude/screen-inventory.md          # edited FIRST (Constitution I)
.claude/openapi.yaml                 # + /home, + PATCH verb, + Collection fields, version 0.7.0
.claude/api-context.md               # mirror of the above, human-readable
```

**Structure Decision**: no new app and no new module layer. Part B is a read projection over the
existing content domain and part A is a field on an existing model, so both belong in
`apps/wallpapers` alongside the collection code they extend. Introducing an `apps/home` would
split one domain across two apps and force a cross-app import of `Collection` — the exact
coupling Constitution V exists to prevent.

## Implementation Sequence

Ordered so the contract leads, then the smallest independent slice, then the riskiest one.
`/speckit-tasks` expands this into tasks.

1. **Contract first** — screen-inventory → `openapi.yaml` + `api-context.md` to v0.7.0 per the
   delta doc. Nothing below starts until this lands.
2. **Migration + model** — three fields, one index, one migration; `makemigrations --check`
   clean.
3. **US3 (description — P3, but smallest)** — public serializer field, create-path support,
   `AdminWallpaperUpdateSerializer` + `PATCH` verb + `update_wallpaper_description()` + audit.
   Ships independently and proves the migration end-to-end.
4. **US1 (`GET /home` — P1)** — caps as constants, `build_home_sections()`, section serializers,
   `HomeView`, route. Query-count test written alongside, not after.
5. **US2 (operator curation — P2)** — `show_on_home` / `home_position` accepted on
   `POST|PATCH /admin/collections`, audited; Django-admin fields for internal staff.
6. **Tier isolation + full suite** — extend `core/tests/test_tier_isolation.py`, run the three
   pre-commit gates.
7. **Contract sync** — copy three files into `livecanvas-mobile` (+ its
   `contracts/openapi.yaml`), changelog entry stating **regeneration is mandatory this time**.
8. **Roadmap/context update** — mark BE-008 shipped in `.claude/sdd-roadmap.md` and
   `.claude/project-context.md`; note BE-006 Security is next.

Steps 3, 4, and 5 are independently demoable, matching the spec's P3 / P1 / P2 user stories.
Step 4 does not depend on step 5 — `/home` can be validated with flags set directly in a
fixture.

## Complexity Tracking

> Fill ONLY if Constitution Check has violations that must be justified.

No violations — table intentionally empty.

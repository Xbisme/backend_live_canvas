# Quickstart — BE-008 Mobile-Driven Content

How to run and validate this feature end-to-end. Shapes live in
[contracts/home-contract-delta.md](contracts/home-contract-delta.md), field-level rules in
[data-model.md](data-model.md) — not repeated here.

## Prerequisites

```bash
docker compose up -d db redis minio      # minio-init creates both buckets
uv pip sync requirements/dev.txt
python manage.py migrate                 # includes this feature's additive migration
python manage.py seed_content            # 397 wallpapers, 5 collections
python manage.py createsuperuser         # if you have no staff account yet
python manage.py runserver
```

Dev app key is `dev-app-key` (`.env.dev`). Admin JWT:

```bash
curl -s -X POST localhost:8000/admin/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"username":"<staff>","password":"<pw>"}' | python3 -m json.tool
```

## Scenario A — Home screen renders curated sections (US1)

1. Flag two seeded collections, in a deliberate order:

```bash
curl -s -X PATCH localhost:8000/admin/collections/1 \
  -H "Authorization: Bearer $ADMIN_ACCESS" -H 'Content-Type: application/json' \
  -d '{"show_on_home": true, "home_position": 1}'

curl -s -X PATCH localhost:8000/admin/collections/2 \
  -H "Authorization: Bearer $ADMIN_ACCESS" -H 'Content-Type: application/json' \
  -d '{"show_on_home": true, "home_position": 0}'
```

2. Fetch the screen:

```bash
curl -s localhost:8000/home -H 'X-App-Key: dev-app-key' | python3 -m json.tool
```

**Expect**: collection 2 first (position 0), then collection 1. Each section carries `key`
(slug), `title`, `collection_id`, `cover_url`, `accent_color`, `is_premium`, and **≤10**
`items` in curated `position` order. No `download_url` anywhere in the payload.

3. Unflag one → it disappears from `sections` on the next call, and its own
   `GET /collections/{id}` page still works unchanged.

**Expect on the empty case**: with nothing flagged, `{"sections": []}` and HTTP 200 — not 404.

**Expect without the app key**: `curl -s localhost:8000/home` → 401 `INVALID_APP_KEY` in the
standard error envelope.

## Scenario B — Caps and skipping hold under abuse (US1 edge cases)

1. Flag more than 10 collections → response still contains exactly 10 sections, taken in
   `home_position` order, no error.
2. Give two collections the same `home_position` → their relative order is identical across
   repeated calls (tie-break by id).
3. Flag a collection whose wallpapers are all soft-deleted or still `processing` → that section
   is **absent** from the response, and the next flagged collection takes its slot (the
   response still holds up to 10 sections).
4. Flag a collection holding more than 10 published wallpapers → exactly 10 items, the first 10
   by curated position, and `collection_id` still points at the full collection.

## Scenario C — Wallpaper description end-to-end (US3)

```bash
# set
curl -s -X PATCH localhost:8000/admin/wallpapers/1 \
  -H "Authorization: Bearer $ADMIN_ACCESS" -H 'Content-Type: application/json' \
  -d '{"description": "Đèn neon phản chiếu trên mặt đường sau mưa."}'

# read back on the public tier
curl -s localhost:8000/wallpapers/1 -H 'X-App-Key: dev-app-key' | python3 -m json.tool
```

**Expect**: `description` carries the text on detail, list, batch, and inside home-screen
`items`. Then:

- `{"description": "   "}` → stored as `null` (whitespace normalized).
- `{"description": null}` → cleared, wallpaper reports `null`.
- Any untouched seeded wallpaper → `"description": null`.
- `{"description": "x", "is_premium": true}` → `is_premium` is **ignored**; only the
  description changes. Verify with a follow-up `GET /admin/wallpapers`.
- Same PATCH with `X-App-Key` instead of the admin bearer → 401 `UNAUTHORIZED_ADMIN`.

## Automated validation

```bash
pytest apps/wallpapers/tests/test_home.py            # US1 + US2 read paths
pytest apps/wallpapers/tests/test_admin_curated.py   # home flags + audit
pytest apps/wallpapers/tests/test_admin_wallpapers.py # description create/edit/clear + audit
pytest core/tests/test_tier_isolation.py             # /home is app-tier, PATCH is admin-tier
pytest                                               # full suite must stay green
```

### Test matrix (maps to spec criteria)

| Area | Cases | Covers |
|---|---|---|
| Ordering | distinct positions · colliding positions repeated N× · default `Meta.ordering` not leaking | FR-002, FR-012, SC-007 |
| Caps | >10 flagged → exactly 10 · >10 items → exactly 10 · flagging an 11th still succeeds (2xx) | FR-006, FR-007, SC-006 |
| Skipping | empty collection · all-items-hidden collection → absent, slot reused | FR-008 |
| Visibility | processing / failed / soft-deleted items excluded | FR-008, SC-008 |
| Premium | premium section fully browsable, no download URL, no entitlement input accepted | FR-010 |
| Auth | `/home` without app key → 401 · with admin JWT only → 401 · `?transaction_id=` changes nothing | FR-009 |
| Empty state | nothing flagged → `{"sections": []}` + 200 | FR-011 |
| Query count | `django_assert_num_queries` constant across 1 vs 10 sections | SC-004 |
| Description | set · change · clear · whitespace → null · untouched rows null · other fields immutable · works on a pre-existing wallpaper | FR-014–FR-018, SC-009, SC-010 |
| Audit | collection home-flag change · wallpaper description change | FR-013, FR-015 |
| Contract | exact response keys · items match the `/wallpapers` shape · `/collections` unchanged · existing contract tests unmodified | FR-005, FR-019–FR-023, SC-011, SC-012 |

## Latency check (SC-005)

Not a pytest gate — measure once on a full screen (10 sections × 10 items) against the seeded
catalogue:

```bash
curl -s -o /dev/null -w '%{time_total}\n' localhost:8000/home -H 'X-App-Key: dev-app-key'
```

Run ~20 times; p95 must be under 300 ms with no cache. If it misses, do **not** add caching
here — record the number and hand it to BE-006 (research D4 notes the window-function escape
hatch if the prefetch turns out to be the cause).

## Pre-commit gates (constitution)

```bash
ruff check . && ruff format --check .
pytest
python manage.py makemigrations --check --dry-run
```

## Definition of done beyond code

- Contract bumped to v0.7.0 in screen-inventory → openapi + api-context order (research D7).
- All three files copied verbatim into `livecanvas-mobile` (+ its `contracts/openapi.yaml`),
  changelog entry added there stating **regeneration is mandatory this time**.
- `.claude/sdd-roadmap.md` + `.claude/project-context.md` updated to reflect BE-008 shipped.

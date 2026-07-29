# Research — BE-008 Mobile-Driven Content

Phase 0 output. Resolves every open decision the spec deliberately deferred to planning, plus
the ones the existing codebase forces. Format per decision: **Decision → Rationale →
Alternatives rejected**.

Codebase facts this builds on (verified 2026-07-27, branch `BE-005-iap-verify-entitlement`):

- `Wallpaper` (`apps/wallpapers/models.py:76`) already uses `null=True` + `# noqa: DJ001` for
  every **contract-nullable** field (`thumbnail_url`, `preview_video_url`, `resolution`,
  `failure_reason`), with an explicit comment that a real NULL is intentional there.
- `Collection` (`:138`) uses the opposite convention for its own `description`
  (`TextField(blank=True)` → `""`), because the contract types it as a plain string.
- `CollectionItem` (`:157`) carries `position` with a `uniq_collection_position` constraint;
  `Collection.Meta.ordering = ["-created_at", "-id"]`.
- Public reads live in `services.py` behind thin views (`views.py`), admin writes in
  `admin_services.py` + `admin_views.py`, every admin mutation wrapped in
  `transaction.atomic()` with `audit.record(...)` inside the same transaction.
- `apps/wallpapers/tests/` holds 10 test modules with shared `conftest.py` fixtures.

---

## D1 — How to store `description` so "absent" survives to the client

**Decision**: `description = models.TextField(null=True, blank=True)  # noqa: DJ001 — contract-nullable`
on `Wallpaper`, default `NULL`. Whitespace-only input is normalized to `None` at the
serializer boundary (a single `_normalize_description` helper used by both the create and the
new edit path), so the database never holds `""` or `"   "`.

**Rationale**: FR-017 requires `null`, never `""` — and the contract (v0.6.0, already published
to mobile) types it `nullable: true`. `Wallpaper` already has an established, commented
convention for exactly this case, so this matches the four neighbouring fields rather than
inventing a third style. Normalizing at the boundary (not in the model) keeps the invariant in
one place and leaves the model dumb.

**Alternatives rejected**:

- `TextField(blank=True, default="")` + map `""` → `None` in the serializer: two
  representations of the same state, and every future queryset/admin/fixture writer has to
  remember the mapping. The first person to add a new serializer leaks `""` to the client.
- `null=True` without normalization: an operator submitting `"  "` writes whitespace that the
  client would render as an empty description block — the exact failure FR-017 forbids.

## D2 — Shape of the wallpaper edit surface

**Decision**: `PATCH /admin/wallpapers/{id}` accepting **only** `description`, added to the
existing `AdminWallpaperDetailView` (which currently holds just `delete`). New
`AdminWallpaperUpdateSerializer` with a single field; unknown fields are ignored by DRF as
usual, and no other model attribute is assignable through this path. Audited as
`wallpaper.update` with `field="description"` metadata (never the text itself — no reason to
duplicate content into the audit trail). Responds with `AdminWallpaperSerializer`.

**Rationale**: FR-015 requires the edit to be incapable of altering anything else; a serializer
with exactly one field makes that structurally true rather than a review promise. `PATCH` on
the existing detail route matches how collections are already edited
(`AdminCollectionDetailView.patch`), so the admin surface stays uniform. Reusing the existing
view class means no new URL and no new tier wiring.

**Alternatives rejected**:

- A general "update wallpaper" serializer mirroring the create body: turns a 1-field ask into a
  surface that can rewrite `category_id`, `is_premium`, `source_url`, and `orientation` with no
  spec, no tests, and real revenue implications (`is_premium`).
- A dedicated `POST /admin/wallpapers/{id}/description`: a verb-in-path endpoint inconsistent
  with the rest of the admin API for no gain.
- Management command only (no API): fails SC-009 — an operator would need shell access to fill
  in descriptions for the 397 seeded wallpapers.

## D3 — Deterministic section ordering (tie-break)

**Decision**: `.order_by("home_position", "id")`, set explicitly on the queryset. Collections
flagged for home are never ordered by the model's default `Meta.ordering`.

**Rationale**: FR-012 requires stability including when positions collide. `home_position`
alone leaves the tie to the database's physical row order, which is genuinely unstable across
vacuum/updates in Postgres. `id` is immutable, unique, and already indexed as the primary key,
so the composite ordering is total and free. Explicit `order_by` is also mandatory here because
`Collection.Meta.ordering` is `["-created_at", "-id"]` — inheriting it would silently produce
the wrong order.

**Alternatives rejected**:

- Unique constraint on `home_position`: forces the operator into swap dances to reorder (the
  same problem `CollectionItem.uniq_collection_position` already causes internally, which
  `_set_collection_items` works around by deleting and re-creating the whole set). Not worth
  imposing on a hand-curated list of ~10.
- Tie-break on `created_at`: not guaranteed unique, so it only shrinks the ambiguity window.
- Tie-break on `slug`: stable, but makes the visible order depend on a string an operator may
  rename, which surprises them.

## D4 — Assembling the home screen in a constant number of queries

**Decision**: three queries, independent of how many sections or wallpapers come back:

1. flagged collections — `Collection.objects.filter(show_on_home=True).order_by("home_position", "id")`
2. a `Prefetch` of `items` filtered to publicly visible wallpapers, ordered by `position`, with
   `select_related("wallpaper__category")`
3. the tag prefetch for those wallpapers (`prefetch_related("wallpaper__tags")`)

Slicing to ≤10 items per section, dropping now-empty sections, and stopping at 10 sections all
happen **in Python** over the already-fetched rows.

**Rationale**: SC-004 asks for a query count that does not grow with result size, which is
exactly what prefetching plus in-memory slicing gives. Doing the caps in Python is also what
makes FR-008 expressible at all: "an empty section does not consume a slot" requires knowing a
section is empty *before* deciding whether it counts, which a SQL `LIMIT` on the outer query
cannot express. The candidate set is operator-curated and bounded in practice (the same
assumption `/collections` and `/tags` already run on), and each collection carries a soft cap
of ≤100 items, so the worst realistic fetch is small.

**Alternatives rejected**:

- Per-section query (loop over collections, query items each): the N+1 the spec explicitly
  guards against; query count grows with section count.
- Window function (`ROW_NUMBER() OVER (PARTITION BY collection_id ORDER BY position)`) to cap
  items in SQL: correct and it would bound the fetch, but it needs a raw/`FilteredRelation`
  construct that no other query in this codebase uses, for a payload that is already small.
  Recorded as the escape hatch if profiling ever shows the prefetch is too wide.
- Caching the assembled response: explicitly out of scope per the spec's clarification — cache
  belongs to BE-006 if the measured p95 misses 300 ms.

## D5 — Section payload shape and the `key` field

**Decision**: `GET /home` returns `{"sections": [...]}` where each section is
`{key, title, collection_id, cover_url, accent_color, is_premium, items}`. `key` is the
collection's **slug**. `items` uses the existing `WallpaperListSerializer` (so
`collections: []`, matching every other list surface).

**Rationale**: the client needs a stable identifier for analytics and scroll-state keying that
does not change when an operator renames a section title; `slug` is already unique, already
curated, and already how collections are addressed conceptually. Wrapping the array in an
object (rather than returning a bare array) leaves room to add screen-level metadata later
without a breaking change — the same reason paginated endpoints use an envelope. Reusing
`WallpaperListSerializer` keeps one wallpaper shape across the API (FR-005) and avoids sending
`collections` refs that would be redundant inside a section that *is* a collection.

**Alternatives rejected**:

- Bare top-level array: no room to grow, and inconsistent with the enveloped responses
  elsewhere.
- `key` = collection id: duplicates `collection_id` and carries no meaning in logs/analytics.
- A section-specific slim wallpaper shape: a second wallpaper model for the mobile client to
  maintain, contradicting FR-005.

## D6 — Where the section caps live

**Decision**: two module-level constants in `apps/wallpapers/services.py` —
`HOME_MAX_SECTIONS = 10`, `HOME_MAX_ITEMS_PER_SECTION = 10` — applied at read time only. No
write-time validation, no settings/env knob. Both numbers are stated in the contract (FR-020).

**Rationale**: matches the clarified decision (cap on read, never reject a flag) and the
existing precedent — `DOWNLOAD_URL_TTL` and `VIRTUAL_ALL_TAG_ID` are module constants in the
same file, not settings. Keeping them out of settings means dev and prod cannot drift, so the
number the contract advertises is the number every flavor serves.

**Alternatives rejected**:

- Django setting / env var: two flavors could serve different caps than the contract documents,
  and the client sizes its UI from the contract.
- Write-time rejection when flagging an 11th collection: the clarification explicitly chose not
  to block the operator; it also makes reordering hostile (you would have to unflag before you
  can flag).

## D7 — Contract sequencing and version

**Decision**: bump to **v0.7.0** in one pass, in constitution order —
`.claude/screen-inventory.md` (screen #1 Browse gains sections; screen #11 admin gains
description editing) → `.claude/openapi.yaml` + `.claude/api-context.md` together → code →
verbatim copy of all three into `livecanvas-mobile` (+ its `contracts/openapi.yaml`) with a
changelog entry. The contract delta is drafted in
[contracts/home-contract-delta.md](contracts/home-contract-delta.md) before any code lands.

**Rationale**: Constitution I forbids code that leads the contract, and this bump *adds a path
and changes a schema* — unlike v0.5.0/v0.6.0 which the mobile client absorbed without
regenerating. Flagging that difference in the sync note is what stops the mobile side from
assuming another no-op regenerate.

**Alternatives rejected**:

- Two bumps (v0.7.0 for description edit, v0.8.0 for `/home`): two cross-repo syncs and two
  client regenerations for one release — the whole reason these asks were merged into one spec.
- Reusing v0.6.0: it is already published to mobile as a description-only, shape-compatible
  bump; silently redefining a released version breaks the one guarantee the version carries.

## D8 — Dependencies

**Decision**: none added. Everything needed (Django ORM `Prefetch`, DRF serializers,
`pytest-django`'s `django_assert_num_queries`) is already present.

**Rationale**: Constitution XI requires version-verifying anything new; nothing here needs a
library. `django_assert_num_queries` ships with `pytest-django` (already a dev dependency) and
is what makes SC-004 testable.

**Alternatives rejected**: `django-cachalot`/Redis response cache — out of scope per the
latency clarification.

## D9 — Migration

**Decision**: one additive migration in `apps/wallpapers/migrations/` adding
`Wallpaper.description`, `Collection.show_on_home` (default `False`), `Collection.home_position`
(default `0`), and an index on `(show_on_home, home_position, id)`. No data migration, no
backfill, fully reversible.

**Rationale**: Constitution IX wants non-destructive, reversible migrations. Defaults chosen so
every existing row is valid the moment the migration applies: existing wallpapers get `NULL`
(FR-018 — they report no description), existing collections stay off the home screen (FR-001).
The composite index covers the exact filter+sort of the only query that reads these columns.

**Alternatives rejected**:

- Separate migrations per part: they land in the same release and the same app; splitting adds
  churn without buying independent rollback (part A and part B are shipped together).
- Backfilling sample descriptions into the seeded catalogue: would make the "no description"
  path untested against real data and is content work, not schema work.

## D10 — Test strategy

**Decision**: extend `apps/wallpapers/tests/` with `test_home.py` (public read: ordering,
tie-break, caps, empty-section skipping, hidden-wallpaper exclusion, premium visibility,
app-tier auth, `django_assert_num_queries` for SC-004) and add cases to
`test_admin_curated.py` (flagging/reordering/unflagging + audit) and `test_admin_wallpapers.py`
(description create/edit/clear, whitespace normalization, audit, tier refusal). Contract-shape
assertions follow the existing pattern of asserting exact response keys.

**Rationale**: Constitution X names auth isolation, contract shape, and curated integrity as
required coverage — all three are touched here. Reusing the existing test modules and
`conftest.py` fixtures (`api`, `anon`, `admin_client`) keeps the suite navigable instead of
scattering a new fixture set.

**Alternatives rejected**: a separate `tests/home/` package — 10 flat modules is the established
layout in this app; one more fits.

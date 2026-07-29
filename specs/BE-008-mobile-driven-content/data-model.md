# Data Model — BE-008 Mobile-Driven Content

Phase 1 output. Two existing models gain fields; **no new model, no new table**. The "home
section" is a read-time projection, not storage (spec Key Entities).

## 1. `Wallpaper` (`apps/wallpapers/models.py`) — one new field

| Field | Type | Null | Default | Notes |
|---|---|---|---|---|
| `description` | `TextField` | **yes** | `NULL` | Contract-nullable (v0.6.0 already published as `string, nullable`). Follows the existing `# noqa: DJ001 — contract-nullable` convention used by `thumbnail_url`, `preview_video_url`, `resolution`, `failure_reason`. |

**Invariant (FR-017)**: the column holds either meaningful text or `NULL` — never `""`, never
whitespace-only. Enforced at the serializer boundary by a single `_normalize_description`
helper shared by the create and edit paths (research D1), so there is exactly one place that
can violate it.

**Visibility**: public read on every wallpaper surface (list, detail, batch, and section items)
via `WallpaperSerializer.Meta.fields`; writable only through the admin tier.

**Existing rows**: unaffected — the migration default is `NULL`, so all 397 seeded wallpapers
report no description until an operator writes one (FR-018).

## 2. `Collection` (`apps/wallpapers/models.py`) — two new fields

| Field | Type | Null | Default | Notes |
|---|---|---|---|---|
| `show_on_home` | `BooleanField` | no | `False` | Whether this collection renders as a section on the app's home screen. Off by default for every existing and new collection (FR-001). |
| `home_position` | `PositiveIntegerField` | no | `0` | Operator-chosen slot in the stack, ascending. **Not unique** — ties are legal and broken deterministically by `id` (research D3). Meaningless while `show_on_home=False`. |

**Index**: `models.Index(fields=["show_on_home", "home_position", "id"], name="coll_home_idx")`
— covers the filter + sort of the only query that reads these columns.

**Ordering caution**: `Collection.Meta.ordering` is `["-created_at", "-id"]`. The home query
**must** call `.order_by("home_position", "id")` explicitly; inheriting the default silently
produces newest-first, which is not the operator's order.

**Unchanged**: `slug`, `title`, `author`, `description`, `cover_url`, `accent_color`,
`is_premium`, and the ordered `CollectionItem` membership all keep their current meaning. A
collection on the home screen is the same collection the collections tab already shows.

## 3. Home section — derived projection (not persisted)

Assembled per request by `services.build_home_sections()` from flagged collections. One section
per qualifying collection:

| Key | Source | Notes |
|---|---|---|
| `key` | `collection.slug` | Stable client-side identity; survives a title rename (research D5). |
| `title` | `collection.title` | |
| `collection_id` | `collection.id` | Client's "see all" target → existing `GET /collections/{id}`. |
| `cover_url` | `collection.cover_url` | |
| `accent_color` | `collection.accent_color` | Nullable, as elsewhere. |
| `is_premium` | `collection.is_premium` | Display only — never a gate (FR-010). |
| `items` | ≤10 published member wallpapers, curated `position` order | Serialized with the existing `WallpaperListSerializer`. |

### Selection rules (the whole of FR-002 / FR-007 / FR-008 / FR-012)

Applied in this exact order:

1. **Candidates**: `show_on_home=True`, ordered `("home_position", "id")`.
2. **Item visibility**: within each candidate, keep only members with
   `status=published` **and** `deleted_at IS NULL` — the same predicate
   `WallpaperQuerySet.published()` already uses — in `position` order.
3. **Item cap**: keep the first `HOME_MAX_ITEMS_PER_SECTION` (10).
4. **Drop empties**: a candidate with zero visible items is skipped and **does not consume a
   slot** — the next candidate takes it.
5. **Section cap**: stop after `HOME_MAX_SECTIONS` (10) surviving sections; remaining
   candidates are silently ignored, with no error on either read or write.

Steps 2–5 run in Python over prefetched rows so the query count stays constant (research D4).

### State transitions

None. Neither new `Collection` field participates in a lifecycle — they are curation switches
an operator flips, with no derived state and nothing to reconcile. `Wallpaper.description` is
free text with no state machine. The existing `WallpaperStatus` machine
(`processing → published | failed`) is untouched; the home screen merely reads its terminal
state as a visibility filter.

## 4. Audit records (`apps/audit`)

Written through `audit.services.record(...)` inside the same transaction as the mutation, as
every other admin write already does:

| Action | When | Metadata |
|---|---|---|
| `collection.create` / `collection.update` | existing actions, now also cover home flags | existing `slug` (+ `item_count` on create) |
| `wallpaper.update` | **new** — description set/changed/cleared | `field="description"` only |

The description text itself is deliberately **not** written to the audit trail: it is content,
not a security-relevant value, and the trail's sanitize guard exists to keep payload data out.

## 5. Migration

One additive migration in `apps/wallpapers/migrations/` (next number after `0003_…`):

- add `Wallpaper.description` (`null=True`)
- add `Collection.show_on_home` (`default=False`), `Collection.home_position` (`default=0`)
- add index `coll_home_idx`

Non-destructive, reversible, no data migration. `python manage.py makemigrations --check
--dry-run` must be clean afterwards (constitution pre-commit gate).

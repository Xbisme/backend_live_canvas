---
description: "Task list for BE-008 Mobile-Driven Content — Browse Sections & Wallpaper Description"
---

# Tasks: Mobile-Driven Content — Browse Sections & Wallpaper Description (BE-008)

**Input**: Design documents from `specs/BE-008-mobile-driven-content/`

**Prerequisites**: [plan.md](plan.md), [spec.md](spec.md), [research.md](research.md), [data-model.md](data-model.md), [contracts/home-contract-delta.md](contracts/home-contract-delta.md), [quickstart.md](quickstart.md)

**Tests**: INCLUDED — Constitution X mandates coverage for two-tier auth isolation, contract
shape, and curated integrity, all three of which this feature touches. No external service is
involved, so nothing needs mocking.

**Organization**: grouped by user story. Phases are numbered in **spec priority order**
(US1 = P1 → US2 = P2 → US3 = P3). The build order suggested in plan.md pulls **US3 forward**
because it is the smallest slice and exercises the shared migration end-to-end — both orders
are valid, the story phases are independent of each other.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: parallelizable — **different files** and no dependency on an incomplete task. Tasks
  that share a file are deliberately left unmarked even when their content is independent, so
  `[P]` never means "safe to edit the same file simultaneously".
- **[Story]**: US1 / US2 / US3 (setup, foundational, polish have no story label)

## Path Conventions

Single Django web-service project. The feature lives almost entirely in `apps/wallpapers/`,
plus the contract files in `.claude/` and one shared test module in `core/tests/`. Tests are
colocated per app (`apps/wallpapers/tests/`).

---

## Phase 1: Setup (Contract First)

**Purpose**: the contract leads the code (Constitution I). Nothing below Phase 1 starts until
both tasks land.

- [X] T001 Update `.claude/screen-inventory.md` per [contracts/home-contract-delta.md](contracts/home-contract-delta.md) §1: row #1 Browse gains curated sections + `GET /home`, row #11 gains description editing + `PATCH /admin/wallpapers/{id}`, row #13 gains home-flag/order actions, plus the new "Browse sections (v0.7.0)" bullet under "Quyết định đã chốt"
- [X] T002 Bump the contract to **v0.7.0** by editing `.claude/openapi.yaml` and `.claude/api-context.md` **together** (editing one without the other is forbidden): `info.version` + v0.7.0 description note, new `GET /home` path, new `HomeResponse` + `HomeSection` schemas, `show_on_home`/`home_position` **only in the `POST|PATCH /admin/collections` request bodies — NOT in the shared `Collection` schema** (it backs public `GET /collections`; see delta §2.4), new `PATCH /admin/wallpapers/{id}` verb using `security: [{ AdminBearer: [] }]` and responding with the existing `Wallpaper` schema, `description` on the `POST /admin/wallpapers` body — all per [contracts/home-contract-delta.md](contracts/home-contract-delta.md) §2–§3. State both caps (10 sections × 10 wallpapers) explicitly in the openapi `maxItems` **and** in the api-context prose so client authors can size their UI (spec FR-020). No new error codes.

**Checkpoint**: contract frozen at v0.7.0; implementation may now begin against it.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: the schema every story reads or writes. **⚠️ No user story can begin until these are done.**

- [X] T003 Add the three fields in `apps/wallpapers/models.py` per [data-model.md](data-model.md) §1–§2: `Wallpaper.description = models.TextField(null=True, blank=True)` with the existing `# noqa: DJ001 — contract-nullable` convention (matching `thumbnail_url`/`resolution` at lines 87-89), `Collection.show_on_home = models.BooleanField(default=False)`, `Collection.home_position = models.PositiveIntegerField(default=0)`, and `models.Index(fields=["show_on_home", "home_position", "id"], name="coll_home_idx")` in `Collection.Meta`
- [X] T004 Generate the migration `apps/wallpapers/migrations/0004_home_sections_and_description.py` (`python manage.py makemigrations wallpapers`); confirm it is additive + reversible with defaults `NULL`/`False`/`0`, then verify `python manage.py makemigrations --check --dry-run` is clean
- [X] T005 Extend `apps/wallpapers/tests/factories.py` so tests can build wallpapers with/without a `description` and collections with `show_on_home`/`home_position`, without changing existing factory defaults (every current test must keep passing untouched). **Depends on T003** — the factory cannot set fields the model does not have yet

**Checkpoint**: schema in place — US1, US2, and US3 can proceed in any order.

---

## Phase 3: User Story 1 — App renders a curated, sectioned home screen (Priority: P1) 🎯 MVP

**Goal**: `GET /home` returns up to 10 curated sections in the operator's order, each with up to
10 published wallpapers in curated position order, in a constant number of queries.

**Independent Test**: flag two collections with explicit positions via fixture/factory (no admin
API needed), fetch `/home` once → both sections in the operator's order with correctly ordered
items; unflag one → it disappears. See [quickstart.md](quickstart.md) Scenario A.

### Tests for User Story 1

> T006–T010 all write `apps/wallpapers/tests/test_home.py`, so none is marked `[P]` — the cases
> are independent but the file is shared. One person takes the module, or they land in order.

- [X] T006 [US1] Create `apps/wallpapers/tests/test_home.py` with the ordering cases: distinct `home_position` values order ascending; **colliding positions produce the same order across repeated requests** (tie-break by id); the response never falls back to `Collection.Meta.ordering` (`-created_at`) — see [research.md](research.md) D3
- [X] T007 [US1] Add cap cases to `apps/wallpapers/tests/test_home.py`: >10 flagged collections → exactly 10 sections taken in operator order with no error; a collection with >10 published items → exactly 10 items, first-by-position, `collection_id` still pointing at the full collection; **and the write side of spec FR-007** — flagging an 11th collection through `PATCH /admin/collections/{id}` succeeds (2xx, never a validation error), the cap is read-only
- [X] T008 [US1] Add visibility + skipping cases to `apps/wallpapers/tests/test_home.py`: items that are `processing`, `failed`, or soft-deleted are excluded; a flagged collection left with zero visible items is **absent from the response and does not consume a slot** (the next flagged collection takes it) — spec FR-008
- [X] T009 [US1] Add contract/auth/empty cases to `apps/wallpapers/tests/test_home.py`: response keys exactly `{key, title, collection_id, cover_url, accent_color, is_premium, items}` per section; **`items[0].keys()` identical to a `GET /wallpapers` item's keys** (spec FR-005 — one wallpaper shape across the API); premium section fully browsable with **no download URL anywhere** in the payload; **`GET /home?transaction_id=<anything>` returns byte-identical output to the plain call** (spec FR-009 — the endpoint neither accepts nor consults a purchase identifier); no `X-App-Key` → 401 `INVALID_APP_KEY` in the standard error envelope; nothing flagged → `{"sections": []}` + 200 (never 404)
- [X] T010 [US1] Add the performance-shape test to `apps/wallpapers/tests/test_home.py`: `django_assert_num_queries` asserts the **same** query count for 1 section and for 10 full sections (spec SC-004)

### Implementation for User Story 1

- [X] T011 [US1] Add `HOME_MAX_SECTIONS = 10` and `HOME_MAX_ITEMS_PER_SECTION = 10` as module constants in `apps/wallpapers/services.py` (alongside `DOWNLOAD_URL_TTL`), with a comment that both numbers are published in the contract and must not become settings — [research.md](research.md) D6
- [X] T012 [US1] Implement `build_home_sections()` in `apps/wallpapers/services.py` per [data-model.md](data-model.md) §3: filter `show_on_home=True`, **explicit** `.order_by("home_position", "id")`, `Prefetch` the `items` filtered to published + not-soft-deleted ordered by `position` with `select_related("wallpaper__category")` and `prefetch_related("wallpaper__tags")`, then cap items / drop empty sections / cap sections **in Python** over the prefetched rows ([research.md](research.md) D4)
- [X] T013 [US1] Add `HomeSectionSerializer` (and the `{"sections": [...]}` envelope) to `apps/wallpapers/serializers.py` with `key` sourced from `collection.slug`, reusing `WallpaperListSerializer` for `items` so the wallpaper shape stays identical to every other list surface ([research.md](research.md) D5)
- [X] T014 [US1] Add `HomeView(AppTierAPIView)` to `apps/wallpapers/views.py`, thin like its neighbours — call the service, serialize, return
- [X] T015 [US1] Register `path("home", HomeView.as_view(), name="home")` in `apps/wallpapers/urls.py` (already mounted at the API root in `config/urls.py`, ahead of the Django-admin catch-all)

**Checkpoint**: `GET /home` is fully functional and independently demoable using seeded flags — MVP delivered.

---

## Phase 4: User Story 2 — Operator curates what appears on the home screen (Priority: P2)

**Goal**: an operator can flag, reorder, and unflag home-screen collections through the admin
API, with every change audited.

**Independent Test**: `PATCH /admin/collections/{id}` with `show_on_home` + `home_position` →
the public `/home` reflects it immediately; unflag → it disappears; each change leaves an audit
record. See [quickstart.md](quickstart.md) Scenario A step 1.

**⚠️ Ordering constraint**: this story's acceptance runs **through `/home`**, so it is the one
story that is not independent — US1 (at least T012–T015) must land first. Asserting on the
model instead would test Django, not the feature.

### Tests for User Story 2

- [X] T016 [US2] Add home-curation cases to `apps/wallpapers/tests/test_admin_curated.py`: create a collection with `show_on_home`/`home_position`; PATCH to change position; PATCH to unflag — asserting the public `/home` result changes accordingly and the collection's own `GET /collections/{id}` page is untouched
- [X] T017 [US2] Add default + audit + contract cases to `apps/wallpapers/tests/test_admin_curated.py`: a collection created without any home instruction defaults to off (spec FR-001); every home-flag change writes a `collection.create`/`collection.update` audit entry attributed to the acting operator (spec FR-013); **`GET /collections` does not grow `show_on_home`/`home_position`** — they are admin-input only (contract delta §2.4)

### Implementation for User Story 2

- [X] T018 [US2] Add `show_on_home` (`BooleanField`, `required=False`, default `False`) and `home_position` (`IntegerField`, `required=False`, `min_value=0`, default `0`) to `AdminCollectionSerializer` in `apps/wallpapers/admin_serializers.py` — both optional so `partial=True` PATCH keeps working unchanged
- [X] T019 [US2] Verify the create/update flow in `apps/wallpapers/admin_views.py` + `admin_services.py` carries the two new fields through (`create_collection(**fields)` and `update_collection`'s `setattr` loop already pass arbitrary validated fields — confirm with a test rather than adding plumbing), and that the mutation + `audit.record` stay inside the one existing `transaction.atomic()` block
- [X] T020 [P] [US2] Surface `show_on_home` and `home_position` in the Django-admin `Collection` registration in `apps/wallpapers/admin.py` (list display + editable fields) so internal staff can curate without the API

**Checkpoint**: the home screen is operable end-to-end without database access (spec SC-002).

---

## Phase 5: User Story 3 — Wallpaper carries a human description (Priority: P3)

**Goal**: operators can set, change, and clear a wallpaper's description — including on the 397
pre-existing wallpapers — and it appears on every public wallpaper payload, with "no
description" always expressed as `null`.

**Independent Test**: PATCH a description onto a seeded wallpaper → it appears on the public
detail/list/batch payloads; a second wallpaper left alone reports `null`. See
[quickstart.md](quickstart.md) Scenario C.

### Tests for User Story 3

- [X] T021 [US3] Add public-read cases to `apps/wallpapers/tests/test_wallpaper_detail.py` (and one list assertion in `test_wallpapers_list.py`): `description` is present on detail, list, and batch payloads; an untouched wallpaper reports `null`, never `""` (spec FR-016/FR-017/FR-018)
- [X] T022 [US3] Add write cases to `apps/wallpapers/tests/test_admin_wallpapers.py`: `POST /admin/wallpapers` with and without `description`; `PATCH /admin/wallpapers/{id}` sets, changes, and clears it (`null`); whitespace-only input is stored as `null` (spec FR-017). **Include one case that patches a wallpaper created without any description and never touched by the create path** — the pre-existing-catalogue scenario is the whole reason this story exists (spec SC-010)
- [X] T023 [US3] Add immutability + audit cases to `apps/wallpapers/tests/test_admin_wallpapers.py`: a PATCH carrying extra keys (e.g. `is_premium`, `category_id`, `title`) changes **only** the description; each description change writes a `wallpaper.update` audit entry whose metadata contains `field="description"` and **not** the description text (spec FR-015, [data-model.md](data-model.md) §4)

### Implementation for User Story 3

- [X] T024 [US3] Add `"description"` to `WallpaperSerializer.Meta.fields` in `apps/wallpapers/serializers.py` (after `"title"`, matching the contract example ordering) so it flows to the list, detail, batch, admin, and home-section payloads through the existing subclasses
- [X] T025 [US3] Add the `_normalize_description` helper to `apps/wallpapers/admin_serializers.py` (strip → `None` when empty) and wire it into `AdminWallpaperCreateSerializer` as an optional `description` field ([research.md](research.md) D1)
- [X] T026 [US3] Add `AdminWallpaperUpdateSerializer` to `apps/wallpapers/admin_serializers.py` with **exactly one** field — `description` (`allow_null=True`, `allow_blank=True`, `required=True`) reusing `_normalize_description` — so the edit path is structurally incapable of touching any other attribute ([research.md](research.md) D2)
- [X] T027 [US3] Add `update_wallpaper_description(pk, description)` to `apps/wallpapers/admin_services.py`: fetch a non-soft-deleted wallpaper or raise `Http404`, `save(update_fields=["description"])` (mirroring `soft_delete_wallpaper`'s narrow write)
- [X] T028 [US3] Add the `patch` method to `AdminWallpaperDetailView` in `apps/wallpapers/admin_views.py` — validate, call the service and `audit.record(request.user, "wallpaper.update", wallpaper, field="description")` inside one `transaction.atomic()`, respond with `AdminWallpaperSerializer` — and pass `description` through in `AdminWallpaperListCreateView.post`'s `Wallpaper.objects.create(...)`
- [X] T029 [P] [US3] Add `description` to the Django-admin `Wallpaper` registration in `apps/wallpapers/admin.py` so internal staff can edit it there too

**Checkpoint**: the description is writable, editable, clearable, and visible everywhere the contract promises.

---

## Phase 6: Polish & Cross-Cutting Concerns

- [X] T030 [P] Extend `core/tests/test_tier_isolation.py`: `GET /home` accepts the app key and refuses an admin JWT alone; `PATCH /admin/wallpapers/{id}` accepts the admin JWT and refuses an app key (401 `UNAUTHORIZED_ADMIN`) — Constitution II
- [X] T031 [P] Verify the seed path still works after the migration: `python manage.py seed_content` loads the committed fixture (which carries no `description` key) without error and the 397 wallpapers report `description: null`
- [X] T032 Run the three constitution pre-commit gates and fix anything they surface: `ruff check . && ruff format --check .`, `pytest`, `python manage.py makemigrations --check --dry-run`. Then verify backward compatibility explicitly (spec FR-023 / SC-011): `git diff --stat` must show **no modification to any pre-existing contract/API test file** — a green suite achieved by editing old assertions is a contract break, not a pass
- [X] T033 Measure SC-005 manually per [quickstart.md](quickstart.md) §Latency: ~20 requests against a full home screen (10 sections × 10 items), confirm p95 < 300 ms with no cache. If it misses, record the number and hand it to BE-006 — **do not** add caching in this spec
- [X] T034 Contract sync: copy `.claude/openapi.yaml` (→ mobile `.claude/` **and** `contracts/`), `.claude/api-context.md`, and `.claude/screen-inventory.md` verbatim into `livecanvas-mobile`, then add a changelog entry there stating explicitly that **v0.7.0 changes path + schema so `scripts/generate_api.sh` regeneration is mandatory this time** (unlike v0.5.0/v0.6.0) — spec FR-021, SC-012
- [X] T035 Update `.claude/sdd-roadmap.md` (mark BE-008 shipped, next up BE-006 Security) and `.claude/project-context.md` (contract version → v0.7.0, status snapshot, sync record)

---

## Dependencies & Execution Order

### Phase dependencies

- **Phase 1 (Setup / contract)** → blocks everything. Constitution I: no code before the contract.
- **Phase 2 (Foundational / schema)** → blocks all three stories.
- **Phase 3 (US1)** and **Phase 5 (US3)** → independent of each other and of US2 once Phase 2 is done. US1 is testable without US2 (flags set straight into a fixture); US3 shares only the migration with the other two — zero code overlap.
- **Phase 4 (US2) depends on US1** — not just for value but for verification: its acceptance criteria are expressed through `GET /home`, so T016/T017 cannot go green until T012–T015 exist. US2 is the one story that is **not** independently testable, and the spec's own US2 scenarios say so ("reflected on the public home screen").
- **Phase 6 (Polish)** → after whichever stories are being shipped.

### Task dependencies inside stories

- **US1**: T011 → T012 → T013 → T014 → T015 (constants → service → serializer → view → route). Tests T006–T010 are written against the intended behaviour and go red until T012–T015 land.
- **US2**: T018 → T019; T020 independent.
- **US3**: T025/T026 → T027 → T028; T024 and T029 independent of the write path.

### Parallel opportunities

Genuinely parallel (different files, no incomplete dependency):

- **Across stories**: after Phase 2, one person takes US1 (`services.py` / `serializers.py` / `views.py` / `urls.py`), another takes US3 (`admin_serializers.py` / `admin_services.py` / `admin_views.py`) — no file overlap. US2 also touches `admin_serializers.py` (a different class), so sequence US2 after US3 or expect a trivial merge — and remember US2 needs US1 done anyway.
- **Within US3**: T029 (Django admin) and T024 (public serializer field) touch files the write path does not.
- **Within US2**: T020 (Django admin) is independent of T018/T019.
- **Phase 6**: T030 and T031 touch different files; T034/T035 are documentation and can be drafted while T032/T033 run.

Deliberately **not** parallel despite looking independent: T006–T010 (one shared `test_home.py`), T016–T017 (`test_admin_curated.py`), T022–T023 (`test_admin_wallpapers.py`), T005 (needs T003's fields).

---

## Implementation Strategy

### MVP scope

**Phase 1 + Phase 2 + Phase 3 (US1)** — `GET /home` serving curated sections. This is the whole
reason the ask exists (the app cannot match its own Browse design today) and is demoable with
flags set directly in a fixture.

### Suggested build order (from plan.md)

Slightly different from the phase numbering, and deliberately so:

1. Phase 1 (contract) → Phase 2 (schema)
2. **US3 first** — smallest slice, and it proves the shared migration end-to-end against real
   data before the larger read surface is built on top of it
3. **US1** — the MVP read surface, with the query-count test written alongside the service, not after
4. **US2** — makes the screen operable without database access
5. Phase 6 — isolation tests, gates, latency measurement, cross-repo sync

### Incremental delivery

Each story phase ends at a checkpoint that is independently demoable and shippable. If the
release has to be cut short, US1 alone is a coherent deliverable (operator curates via Django
admin, which T020 provides in US2 — so pair US1 with T020 if US2 as a whole is dropped).

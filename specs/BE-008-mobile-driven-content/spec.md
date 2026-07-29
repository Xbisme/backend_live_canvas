# Feature Specification: Mobile-Driven Content — Browse Sections & Wallpaper Description

**Feature Branch**: `BE-008-mobile-driven-content`

**Created**: 2026-07-27

**Status**: Draft

**Input**: User description: "BE-008 Mobile-Driven Content — Browse Sections + Wallpaper Description. Hai ask từ repo mobile (design pass MO-004, 2026-07-27), gộp 1 spec vì cùng chạm apps/wallpapers, cùng một lần bump contract và một lần Contract Sync. (A) `Wallpaper.description` — contract đã khai báo trước ở v0.6.0 (string, nullable), backend đang trả null. (B) Browse curated sections — tái dùng model `Collection` (thêm `show_on_home` + `home_position`), endpoint public mới `GET /home`, bounded ≤10 wallpaper/section, không phân trang; bump contract v0.7.0."

## Overview

Two gaps the mobile team hit while building screens against the existing API, batched into one release because they touch the same domain and share a single contract bump + cross-repo sync.

**(A) Wallpaper description.** The Wallpaper Detail screen has a "Mô tả" block in its design, but a wallpaper record carries no descriptive text — only a title. The contract already *declares* the field (v0.6.0, nullable) so the client could ship against it; the backend currently returns nothing for it. This feature makes the field real: operators can write it, the public API returns it.

**(B) Browse sections.** The Browse screen's design is a stack of titled, curated rows ("Neon Nights", "Thư giãn", …), each showing a handful of wallpapers. The API only offers one flat, newest-first, infinitely-scrolling grid, so the client shipped a flat grid that does not match the design. This feature lets an operator decide *which* curated collections appear on the home screen and *in what order*, and serves that whole screen in one call.

Crucially, (B) introduces **no new curation concept**. A "section" is an existing curated Collection that an operator has flagged for the home screen. Collections already carry a title, an author, a cover image, an accent colour, a premium flag, and an explicitly ordered list of wallpapers — everything a section needs. Adding a parallel "Section" object would give operators two places to curate the same thing and two sets of rules to keep consistent.

Neither part changes who can see or download anything. Premium sections advertise themselves as premium exactly like premium collections do today; the only authoritative entitlement gate remains the per-file download step.

## Clarifications

### Session 2026-07-27

- Q: BE-008 có mở đường sửa mô tả cho wallpaper đã tồn tại không (397 item seed sẵn đều chưa có mô tả, `POST /admin/wallpapers` chỉ dùng lúc đăng ký file mới)? → A: **Có** — thêm surface sửa wallpaper đã tồn tại, giới hạn ở `description`, vào cùng contract bump này, có audit như thao tác curated khác.
- Q: Home screen không phân trang → payload = (số collection được bật) × (≤10 wallpaper) và hiện không có trần trên. Hệ thống có tự chặn số section không? → A: **Trần cứng lúc đọc** — chỉ trả tối đa N section đầu theo thứ tự operator sắp (N=10), phần dư bỏ qua im lặng; KHÔNG chặn lúc operator ghi.
- Q: "Fast enough to be the app's first screen" là tính từ mơ hồ — có cam kết ngưỡng latency không, và ngưỡng đó có kéo cache vào spec này không? → A: **p95 < 300 ms server-side** ở tải hiện tại, **không thêm tầng cache**; đạt bằng truy vấn bounded + số query hằng số. Nếu số đo thật không đạt thì cache là việc của BE-006, không phải BE-008.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - App renders a curated, sectioned home screen (Priority: P1)

Someone opens the app. Instead of one undifferentiated grid of newest wallpapers, they see a short stack of titled rows the operator curated — each row named, visually themed, and holding a handful of wallpapers in the order the operator chose. Tapping a wallpaper opens it; tapping the row's "see all" opens that collection's full page, which already exists.

**Why this priority**: This is the screen every user lands on first, and the reason the ask exists — the app currently cannot match its own design. It is also the only part that needs a new read surface, so it carries the most risk and deserves to land first. Testable on its own using curated data seeded directly, without any operator tooling.

**Independent Test**: Flag two collections for the home screen with an explicit order and seed each with published wallpapers. Fetch the home screen once → both sections come back, correctly titled, in the operator's order, each carrying its wallpapers in curated order. Unflag one → it disappears from the response.

**Acceptance Scenarios**:

1. **Given** two collections flagged for the home screen with distinct positions, **When** the app fetches the home screen, **Then** it receives both sections ordered by the operator's chosen position, each with its title, cover, accent colour, premium flag, a reference to the underlying collection, and its wallpapers.
2. **Given** a flagged collection whose wallpapers were curated into a specific order, **When** its section is returned, **Then** the wallpapers appear in exactly that curated order.
3. **Given** a flagged collection holding more wallpapers than a section is allowed to show, **When** its section is returned, **Then** only the first N in curated order are included, and the section still points at the collection so the client can offer "see all".
4. **Given** no collection is flagged for the home screen, **When** the app fetches the home screen, **Then** it receives an empty list of sections and a success response — not an error.
5. **Given** a flagged collection containing wallpapers that are unpublished, still processing, failed, or deleted, **When** its section is returned, **Then** those wallpapers are omitted while the remaining published ones are still shown.
6. **Given** a flagged premium collection, **When** its section is returned, **Then** its wallpapers and premium flag are visible to everyone (no purchase required to browse), and no download link is included in the response.
7. **Given** more collections are flagged for the home screen than it is allowed to show, **When** the app fetches it, **Then** it receives exactly the maximum number of sections, taken in the operator's order, with the remainder omitted and no error.
8. **Given** a flagged collection that would fall within the maximum but has no visible wallpapers, **When** the home screen is assembled, **Then** it is omitted and the next flagged collection takes its slot.
9. **Given** a request without a valid app key, **When** the home screen is fetched, **Then** it is refused exactly like every other public endpoint.

---

### User Story 2 - Operator curates what appears on the home screen (Priority: P2)

An operator managing content decides that a collection deserves a spot on the home screen, and where in the stack it should sit. They can add it, move it, and remove it later — and every such change is traceable afterwards, like the rest of their curation work.

**Why this priority**: Without this, the home screen can only be changed by someone with direct database access — workable for a first demo (which is why US1 stands alone), but not for running the product. It is a small surface on top of operator tooling that already exists.

**Independent Test**: Through the operator surface, create a collection marked for the home screen at a given position, confirm it now appears on the public home screen, move it, confirm the order changed, then unflag it and confirm it disappears — and that each of these actions left an audit record.

**Acceptance Scenarios**:

1. **Given** an authenticated operator, **When** they create or update a collection and mark it for the home screen with a position, **Then** the setting is stored and immediately reflected on the public home screen.
2. **Given** a collection currently on the home screen, **When** the operator unflags it, **Then** it stops appearing on the home screen while the collection itself, its items, and its own page remain untouched.
3. **Given** any change to a collection's home-screen placement, **When** it is saved, **Then** an audit record attributes the change to the operator who made it.
4. **Given** a request from an unauthenticated or non-operator caller, **When** they attempt to change home-screen placement, **Then** it is refused by the existing operator authentication rules.
5. **Given** a collection created without any home-screen instruction, **When** it is saved, **Then** it does not appear on the home screen (staying off is the default).

---

### User Story 3 - Wallpaper carries a human description (Priority: P3)

An operator writes a short description for a wallpaper — either while registering it, or later on a wallpaper that already exists. Anyone viewing that wallpaper in the app sees it under a "description" block. Wallpapers without one show no such block at all — no empty heading, no blank space.

**Why this priority**: Genuinely useful and already promised by the published contract, but the app functions without it — the block is simply hidden today. Smallest slice of the three, fully independent of the section work.

**Independent Test**: Write a description on one wallpaper and leave another without one. Fetch both → the first carries its text, the second explicitly carries "no description" (not an empty string), so the client can tell the difference and hide the block. Then add a description to a wallpaper that already existed → it appears without anything else about that wallpaper changing.

**Acceptance Scenarios**:

1. **Given** a wallpaper with a description, **When** it is fetched, **Then** the description text is returned with it.
2. **Given** a wallpaper with no description, **When** it is fetched, **Then** the description is explicitly absent rather than an empty string, so the client can hide the block without string comparisons.
3. **Given** an operator registering a new wallpaper, **When** they supply a description, **Then** it is stored and appears on the public record.
4. **Given** an operator registering a new wallpaper, **When** they supply no description, **Then** the wallpaper is created successfully and reports no description.
5. **Given** a wallpaper that already exists (including one from the pre-existing catalogue), **When** an operator sets or changes its description, **Then** the new text appears on the public record and no other attribute of that wallpaper — its media, status, tags, category, or collection memberships — is altered.
6. **Given** a wallpaper with a description, **When** an operator clears it, **Then** it reverts to reporting no description and the client hides the block again.
7. **Given** an unauthenticated or non-operator caller, **When** they attempt to change a wallpaper's description, **Then** it is refused by the existing operator authentication rules.
8. **Given** any change to a wallpaper's description, **When** it is saved, **Then** an audit record attributes the change to the operator who made it.
9. **Given** wallpapers created before this feature and never edited, **When** they are fetched, **Then** they report no description and nothing else about them changes.

---

### Edge Cases

- **Two collections share the same home position** → order must still be deterministic and stable across repeated requests (never shuffling between loads); ties resolve by a fixed secondary rule.
- **A flagged collection has zero visible wallpapers** (empty, or every item unpublished/deleted) → the section is omitted entirely rather than rendering an empty titled row in the app.
- **A flagged collection is deleted** → it simply stops appearing; the home screen does not error.
- **More collections are flagged than the home screen shows** → the first N by the operator's order are served and the remainder are silently dropped; the operator is never blocked from flagging, and no error surfaces to the app. The operator's ordering is therefore what decides which flagged collections actually earn a slot.
- **Home screen requested on every cold app start** → it must answer within the stated latency budget (SC-005) and must not degrade as the number of sections or the catalogue grows (no per-item follow-up lookups).
- **A description containing very long text or newlines** → stored and returned faithfully; the client controls truncation.
- **A description written as whitespace only** → treated as no description, so the client does not render an empty block.
- **Existing clients on the older contract** → both additions are additive; a client that ignores the new field and the new screen keeps working unchanged.

## Requirements *(mandatory)*

### Functional Requirements

**Home screen sections**

- **FR-001**: The system MUST let an operator mark a curated collection as appearing on the app's home screen, and unmark it later. Not appearing MUST be the default for every existing and newly created collection.
- **FR-002**: The system MUST let an operator specify each home-screen collection's position in the stack, and MUST return sections in ascending position order.
- **FR-003**: The system MUST expose a single public read surface returning the entire home screen — all sections with their wallpapers — in one request, requiring no follow-up requests to render the screen.
- **FR-004**: Each section MUST carry the display data the screen needs: title, cover image, accent colour, premium flag, and an identifier of the underlying collection so the client can navigate to that collection's existing full page.
- **FR-005**: Each section MUST carry its wallpapers in the operator's curated order, capped at a documented maximum per section, using the same wallpaper representation as every other public endpoint (no section-specific wallpaper shape).
- **FR-006**: The home screen MUST NOT be paginated. It MUST instead be bounded on both axes: at most a documented maximum number of sections, each holding at most a documented maximum number of wallpapers, so the response size has a hard ceiling that operator actions cannot exceed.
- **FR-007**: When more collections are flagged for the home screen than the section maximum allows, the system MUST return the first N by the operator's chosen order and silently omit the rest. Flagging beyond the maximum MUST NOT be rejected at write time and MUST NOT produce an error on read.
- **FR-008**: The home screen MUST exclude wallpapers that are not publicly visible (unpublished, processing, failed, or deleted), and MUST omit any section left with no visible wallpapers. A section omitted for being empty MUST NOT consume one of the available section slots.
- **FR-009**: The home screen MUST be authenticated by the app tier exactly like other public endpoints, and MUST NOT accept or require operator credentials or any purchase identifier.
- **FR-010**: The home screen MUST NOT gate, hide, or alter premium content based on entitlement — premium sections and their wallpapers are browsable by everyone, and the sole entitlement gate remains the per-file download step.
- **FR-011**: The home screen MUST return successfully with an empty section list when nothing is curated for it.
- **FR-012**: Section ordering MUST be deterministic and stable across identical requests, including when positions collide.
- **FR-013**: Changes to a collection's home-screen placement MUST be recorded in the existing audit trail, attributed to the operator who made them, like other curation actions.

**Wallpaper description**

- **FR-014**: The system MUST let an operator record a free-text description for a wallpaper when registering it.
- **FR-015**: The system MUST let an operator set, change, or clear the description of a wallpaper that already exists, including every wallpaper in the pre-existing catalogue. This edit MUST NOT be able to alter any other attribute of the wallpaper, and MUST be recorded in the audit trail attributed to the operator.
- **FR-016**: The system MUST return a wallpaper's description on every public surface that returns a wallpaper, matching the already-published contract.
- **FR-017**: A wallpaper without a description MUST report it as explicitly absent, never as an empty string, so clients can hide the block by presence alone. Whitespace-only input MUST be normalized to absent.
- **FR-018**: Wallpapers that existed before this feature and were never edited MUST report no description, with no other change to their data or behaviour.

**Contract & cross-repo**

- **FR-019**: The screen inventory, the machine-readable contract, and its human-readable companion MUST be updated together — screens first, then contract — before server behaviour changes, and the contract version MUST be bumped to cover both the new home-screen surface and the new wallpaper-edit surface.
- **FR-020**: The documented maximums (sections per home screen, wallpapers per section) MUST be stated in the contract so client authors can size their UI and cache expectations without reading server code.
- **FR-021**: Both contract files MUST be copied verbatim into the mobile repo and the sync recorded there, flagging that this bump changes shape (not just wording) and therefore requires the mobile client to be regenerated.
- **FR-022**: The feature MUST introduce no new error codes; failures MUST reuse the existing catalog and the centralized error shape.
- **FR-023**: All additions MUST be backward compatible — a client written against the previous contract MUST keep working without modification.

### Key Entities

- **Collection** (existing, extended): a curated, ordered set of wallpapers with a title, author, cover, accent colour, and premium flag. Gains two curation attributes: whether it appears on the app's home screen, and its position in that stack. No other meaning changes — a collection on the home screen is the same collection reachable from the collections tab.
- **Home section** (derived, not stored): the presentation of one home-flagged collection — its display data plus a bounded, ordered slice of its wallpapers. Purely a read-time projection; nothing new is persisted and there is no separate object for an operator to manage.
- **Wallpaper** (existing, extended): gains an optional human-written description. Distinguishing "has no description" from "has an empty description" is meaningful and must survive to the client.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: The app renders its complete home screen — every section, titled, ordered, with its wallpapers — from a **single** request, with no additional round-trips.
- **SC-002**: An operator can put a collection on the home screen, change its position, and take it off again entirely through the operator surface, with no database access and no engineering involvement.
- **SC-003**: A change to home-screen curation is visible to app users on their next home-screen load, with no deploy or restart.
- **SC-004**: Home-screen cost stays flat as content grows — the number of database round-trips per request is constant regardless of how many sections or wallpapers are returned, verified by an automated query-count assertion.
- **SC-005**: The home screen answers within 300 ms at the 95th percentile, measured at the API boundary with the screen at full size (maximum sections, each full) against the current catalogue.
- **SC-006**: The home-screen response has a hard ceiling no operator action can exceed — with an arbitrarily large number of collections flagged, the response still contains at most the documented maximum sections and wallpapers per section, verified by an automated test that flags well beyond the limit.
- **SC-007**: 100% of home-screen sections and their wallpapers respect the operator's curated ordering, verified by automated tests over positions that include colliding values.
- **SC-008**: No wallpaper that is unpublished, processing, failed, or deleted ever appears on the home screen, verified by automated tests.
- **SC-009**: A client can decide whether to render the description block using presence alone — 100% of wallpapers without a description report it as absent, never as an empty or whitespace string.
- **SC-010**: An operator can give any wallpaper in the existing catalogue a description through the operator surface — no database access, no re-upload, and no other attribute of that wallpaper changing.
- **SC-011**: A client built against the previous contract keeps working unchanged against the new one — verified by the existing contract tests passing without modification.
- **SC-012**: The mobile repo holds byte-identical contract files and a recorded sync note before this feature is considered done.

## Assumptions

Defaults chosen where the request left room; each is cheap to revisit during planning.

- **Section size cap = 10 wallpapers.** Enough to fill a horizontally scrolling row without bloating the app's first response. The section always references its collection, so "see all" reaches the full set through the existing collection page.
- **Section count cap = 10 sections.** Combined with the size cap this puts a hard ceiling of ~100 wallpaper records on the app's first response — the same order of magnitude as the other bounded curated lists. Enforced when reading rather than when flagging, so an operator experimenting with placements never hits a write error.
- **Sections are collection-backed only.** No automatically computed rows ("newest", "trending") in this feature — those were explicitly deferred, along with the `is_featured` idea they would have needed.
- **A section shows the first N wallpapers in curated order**, not a random or rotating sample — the operator's ordering is the product decision, and a stable order also keeps the response cacheable later.
- **Empty sections are omitted rather than returned empty**, so the client never has to special-case a titled row with nothing in it.
- **Position ties break deterministically** by a fixed secondary attribute of the collection, so two collections sharing a position never swap places between requests.
- **The description is returned everywhere a wallpaper is returned** (lists, detail, batch), matching the published contract, rather than only on the detail surface — the contract already places it on the shared wallpaper shape, and a surface-dependent shape would itself be a contract change and would break the client's single wallpaper model.
- **Descriptions are plain text**, rendered by the client. No markup, sanitization, or length ceiling beyond ordinary text storage is assumed.
- **The wallpaper-edit surface is scoped to the description only.** It exists because the entire pre-existing catalogue was created before this field and could otherwise never receive one. Widening it to other wallpaper attributes is a separate decision — media, status, and curated relationships keep their current dedicated flows.
- **Whether sections show while a tag filter is active is a client decision.** The proposal recorded from the design pass — sections while the filter is "All", flat grid once a tag is chosen — needs no server support either way, since both surfaces already exist.
- **No caching layer is introduced.** The response is made cheap by construction (bounded size, no per-item lookups), which is expected to meet the latency budget on its own. If real measurements miss it, adding a cache is a hardening decision for the security/production-readiness spec, not a reason to widen this one.

## Dependencies

- **BE-003** — the `Wallpaper`, `Collection`, and ordered-membership model, plus the public read API this extends.
- **BE-004** — the operator authentication tier, the collection management surface being extended, and the audit trail that records curation changes.
- **Not dependent on BE-005** — this feature adds no entitlement logic and can be built and shipped whether or not the IAP work has merged.
- **Cross-repo** — the mobile repo must regenerate its API client after the contract bump before it can consume the home screen or display descriptions.

## Out of Scope

- A separate "section" object independent of collections, and any mixing of curated with automatically computed rows.
- Automatically derived sections (trending, most downloaded, newest, per-category) and any personalization or per-user ordering.
- An `is_featured` flag on wallpapers — explicitly rejected in favour of collection-backed sections.
- A dedicated "related wallpapers" surface — the client derives it from the existing tag filter.
- Pagination or lazy loading inside a section; "see all" reuses the existing collection page.
- Editing any wallpaper attribute other than the description — media, publication status, tags, category, and collection membership keep their existing dedicated flows.
- Any change to entitlement, download links, or premium enforcement.

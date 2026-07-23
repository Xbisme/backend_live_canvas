# Feature Specification: Admin Upload Pipeline

**Feature Branch**: `BE-004-admin-upload-pipeline`

**Created**: 2026-07-23

**Status**: Draft

**Input**: User description: "BE-004 Admin Upload Pipeline — admin auth tier, real object storage, async media pipeline, and bulk backfill of the local dataset. Admin login issues short-lived JWT for /admin/*; Cloudflare R2 (prod) / MinIO (dev) object storage via presigned URLs; two-step presigned upload with async processing (MIME sniffing, H.264 normalize, thumbnail, watermarked 720p preview); admin CRUD for wallpapers/tags/collections with audit log; bulk backfill of the 397 seeded wallpapers from the local dataset through the same pipeline; real short-lived download-url for free wallpapers (premium stays 402 until BE-005). ClamAV deferred to BE-006; IAP verification out of scope (BE-005)."

## Clarifications

### Session 2026-07-23

- Q: Thumbnail + preview được serve qua URL công khai qua CDN (không ký), hay mọi object đều phải presigned? → A: Tách 2 vùng — thumbnail + preview ở vùng public-read qua CDN (URL tĩnh, cache được); master gốc ở vùng private, chỉ phát qua presigned GET ≤ 5 phút; key non-guessable cho master.
- Q: Access token và refresh token admin sống bao lâu? → A: Access 30 phút / Refresh 7 ngày, refresh xoay vòng (rotate) khi dùng.
- Q: Trần dung lượng cho một video upload là bao nhiêu? → A: 500 MB mỗi file (gấp ~2× file lớn nhất trong dataset hiện tại).

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Admin publishes a new wallpaper end-to-end (Priority: P1)

A content admin signs in with their staff credentials, receives a short-lived access token, requests an upload slot for a video file, uploads the file directly to storage, then registers it as a new wallpaper with a title, category, and curated tags. The system processes the video in the background — verifying it really is a video, producing a device-compatible master, a thumbnail, and a watermarked preview — and the wallpaper automatically appears in the public catalog when processing succeeds, or is parked in a visible "failed" state when it does not.

**Why this priority**: This is the core content-operations loop the product needs to grow its catalog beyond the seeded dataset. Every other story in this spec either supports it (auth, storage) or reuses it (backfill).

**Independent Test**: With one staff account and one valid portrait video file, an admin can go from sign-in to seeing the new wallpaper served by the public list endpoint — with a real thumbnail and preview — without any manual step after registration.

**Acceptance Scenarios**:

1. **Given** a valid staff account, **When** the admin signs in with correct credentials, **Then** they receive a short-lived access credential (plus a means to refresh it) usable on `/admin/*` endpoints only.
2. **Given** an authenticated admin, **When** they request an upload slot for a `.mp4` file, **Then** they receive a time-limited upload destination and an opaque upload reference, and the API itself never receives the file bytes.
3. **Given** an uploaded file and a registration naming an existing category and existing curated tags, **When** the admin registers the wallpaper, **Then** the API responds immediately with the new wallpaper in `processing` state (media fields null) and processing starts in the background.
4. **Given** a registered wallpaper whose file is a genuine video, **When** background processing completes, **Then** the wallpaper is `published` with self-hosted thumbnail, preview, resolution, duration, and file size populated, and it appears in public list/detail responses.
5. **Given** a registration referencing a non-existent tag, **When** the admin submits it, **Then** the request fails with the catalog error `TAG_NOT_FOUND` and no wallpaper is created.
6. **Given** an uploaded file that is not actually a video (regardless of its extension or declared type), **When** processing runs, **Then** the wallpaper ends in `failed` state with the rejection reason recorded, and it never appears publicly.
7. **Given** a request to any `/admin/*` endpoint with a missing/expired/invalid credential, **When** it is received, **Then** it is rejected with `UNAUTHORIZED_ADMIN` (401); a valid app-tier key never grants admin access, and an admin credential never satisfies app-tier checks.

---

### User Story 2 - Operator backfills the seeded catalog to self-hosted storage (Priority: P1)

An operator runs a one-shot bulk import that takes the 397 already-seeded wallpapers, uploads each original video from the local dataset directory into object storage, and pushes every item through the exact same background processing as a normal admin upload. When it finishes, every seeded wallpaper's thumbnail and preview are served from the project's own storage/CDN instead of the interim third-party CDN, and real downloads become possible.

**Why this priority**: The public catalog currently depends on a third-party CDN the project does not control, and downloads are impossible because no file is self-hosted. This story removes both risks and doubles as the pipeline's first load test. It shares P1 because launch is blocked without it, but it builds on Story 1's pipeline.

**Independent Test**: Starting from the seeded database and the local dataset directory, one command run to completion leaves zero wallpapers referencing the third-party CDN, all 397 `published` with self-hosted media, and a re-run makes no changes.

**Acceptance Scenarios**:

1. **Given** the seeded catalog and a configured local dataset location, **When** the operator runs the backfill, **Then** each wallpaper's original file is uploaded to object storage and queued through the same processing path as an admin upload.
2. **Given** a completed backfill, **When** the public API is queried, **Then** every thumbnail/preview URL points to self-hosted storage and no Pexels URL remains.
3. **Given** a backfill interrupted partway (crash, Ctrl-C, network loss), **When** it is run again, **Then** already-completed items are skipped without re-uploading or re-processing, and the run completes the remainder.
4. **Given** a dataset file listed in the catalog but missing on disk, **When** the backfill reaches it, **Then** the item is reported and skipped, the run continues, and the summary lists all skipped items.
5. **Given** provenance data (source page, license, author attribution), **When** the backfill migrates media, **Then** that provenance is preserved unchanged.

---

### User Story 3 - App user downloads a free wallpaper (Priority: P2)

A mobile-app user browsing the catalog taps download on a free wallpaper. The app calls the download endpoint and receives a short-lived, single-file link to the full-quality video, which it downloads directly from storage/CDN. For premium wallpapers, the endpoint keeps refusing until purchase verification exists (next spec).

**Why this priority**: This turns the mock/501 download into the real product feature, but it only has value once files are self-hosted (Stories 1–2).

**Acceptance Scenarios**:

1. **Given** a published free wallpaper with self-hosted media, **When** the app requests its download URL with a valid app key, **Then** it receives a working link that expires within 5 minutes and serves exactly that one file.
2. **Given** a premium wallpaper, **When** the app requests its download URL (with or without a `transaction_id`), **Then** the response is `402 ENTITLEMENT_REQUIRED` — no premium bytes are obtainable in this phase.
3. **Given** a wallpaper that is `processing`, `failed`, or soft-deleted, **When** a download URL is requested, **Then** the response is `404 NOT_FOUND`.
4. **Given** an expired download link, **When** it is used, **Then** storage refuses it.

---

### User Story 4 - Admin curates tags and collections (Priority: P2)

An admin manages the curated vocabulary: creating and deleting tags, and creating, editing, reordering, and deleting collections (including uploading a cover image via the same presigned flow). The catalog stays browsable and consistent throughout.

**Why this priority**: Curated tags/collections already drive the public catalog (seeded), and registration (Story 1) needs `POST /admin/tags` to introduce new vocabulary. It is P2 because the seeded vocabulary suffices for day one.

**Acceptance Scenarios**:

1. **Given** an authenticated admin, **When** they create a tag with a new slug, **Then** it becomes available for wallpaper registration and appears in public `/tags`; the reserved slug `all` is rejected.
2. **Given** a tag still attached to wallpapers, **When** deletion is attempted, **Then** it fails with `TAG_IN_USE`.
3. **Given** a collection creation naming wallpapers in a specific order, **When** it succeeds, **Then** the public collection detail returns items in exactly that order; a duplicate slug fails with `COLLECTION_SLUG_CONFLICT`; an unknown wallpaper id fails with `WALLPAPER_NOT_FOUND`.
4. **Given** a collection update with a reordered wallpaper list, **When** it succeeds, **Then** the new order replaces the old atomically — a concurrent public read never sees a half-updated ordering.

---

### User Story 5 - Admin actions are auditable (Priority: P3)

Every state-changing admin action (login included) is recorded with who did it, what was affected, and when, so content and security incidents can be reconstructed after the fact.

**Why this priority**: Required for accountable operations, but it protects value rather than creating it — the catalog works without it.

**Acceptance Scenarios**:

1. **Given** any successful admin mutation (create/update/delete of wallpaper, tag, collection; upload registration), **When** it completes, **Then** an audit record exists identifying the admin account, the action, the affected object, and the time.
2. **Given** a failed sign-in attempt, **When** it is rejected, **Then** the attempt is recorded without storing the submitted password.
3. **Given** audit records, **When** they are inspected, **Then** they contain no secrets, tokens, or presigned URLs.

---

### Edge Cases

- **Orphaned uploads**: a file is uploaded to a presigned slot but never registered — it must never become publicly visible, and stale unregistered objects must be identifiable for cleanup.
- **Duplicate registration**: the same upload reference is registered twice — the second attempt must fail cleanly rather than create two wallpapers over one file.
- **Processing retry**: a transient failure (storage hiccup) during background processing must be retryable without producing duplicate renditions or a half-published wallpaper; re-processing an already-published item must be a no-op or a clean overwrite, never a corruption.
- **Presign abuse**: requesting an upload slot for a disallowed content type or an absurd file name must be refused with `VALIDATION_ERROR`.
- **Oversized upload**: a file exceeding the 500 MB ceiling must be rejected during processing (`failed`, reason recorded), not crash the worker.
- **Login edge**: a valid Django account that is not staff must be refused admin access (`FORBIDDEN_ADMIN_ROLE`); a disabled account must be refused sign-in.
- **Deleting curated parents**: deleting a wallpaper that belongs to collections must not break collection reads (soft-delete semantics — item disappears from public views gracefully).
- **Backfill vs. live edits**: if an admin edits or deletes a seeded wallpaper before the backfill reaches it, the backfill must respect current state (skip deleted, not resurrect).
- **Clock skew on token expiry**: tokens near expiry must fail closed (reject), never open.

## Requirements *(mandatory)*

### Functional Requirements

**Admin authentication tier**

- **FR-001**: The system MUST provide an admin sign-in operation that exchanges valid Django staff-user credentials for an access credential valid **30 minutes** and a refresh credential valid **7 days** (rotated on each use); non-staff or disabled accounts MUST be refused (`FORBIDDEN_ADMIN_ROLE` / `UNAUTHORIZED_ADMIN`).
- **FR-002**: All `/admin/*` endpoints MUST require the admin access credential and MUST reject the app-tier `X-App-Key` in its place; app-tier endpoints MUST reject admin credentials in place of the app key. The two tiers share no fallback path (Constitution II).
- **FR-003**: Expired, malformed, or revoked admin credentials MUST yield `UNAUTHORIZED_ADMIN` (401) via the centralized error handler; admin credentials MUST never appear in logs or error messages.
- **FR-004**: The new admin auth surface (sign-in, refresh) MUST be added to the contract (screen-inventory → openapi.yaml + api-context.md, version bump to v0.4.0) before implementation, and synced to the mobile repo per Constitution I.

**Object storage**

- **FR-005**: The system MUST use S3-compatible object storage configured per flavor — a real cloud bucket+CDN in `prod`, a local container in `dev` — selected purely by environment configuration; dev and tests MUST run without internet access (storage boundary mocked in tests).
- **FR-006**: File ingress MUST be a two-step presigned flow: the API issues a time-limited upload destination (`POST /admin/uploads/presign`), the client uploads directly to storage, and the API later receives only the opaque upload reference. The API process MUST never proxy file bytes (Constitution VII).
- **FR-007**: Storage MUST be split into two zones: a **public-read zone** (served via CDN with stable, cacheable URLs) holding thumbnails and watermarked previews, and a **private zone** holding normalized masters and raw uploads, reachable ONLY via short-lived presigned links. Master object keys MUST be non-guessable (no sequential or slug-derived names) to prevent enumeration/IDOR (Constitution III).

**Upload registration & async processing**

- **FR-008**: `POST /admin/wallpapers` MUST validate that the category exists and all `tag_ids` reference existing curated tags (`TAG_NOT_FOUND` otherwise), create the wallpaper in `processing` state with null media fields, respond immediately, and enqueue background processing. Each upload reference MUST be registrable at most once.
- **FR-009**: Background processing MUST (a) verify the file's real content type by magic-byte sniffing — never trusting extension or client-declared type; (b) produce a device-compatible normalized master retaining source resolution; (c) produce a thumbnail image; (d) produce a watermarked reduced-resolution preview; (e) populate resolution/duration/file-size metadata; then (f) atomically transition the wallpaper to `published`.
- **FR-010**: Any processing failure MUST leave the wallpaper in an inspectable `failed` state with a recorded reason — never half-published, never publicly visible. Tasks MUST be idempotent and safe to retry (Constitution VII).
- **FR-011**: Files exceeding the **500 MB** size ceiling MUST be rejected synchronously at registration (`422 FILE_REJECTED` — detected via a cheap storage HEAD, no bytes downloaded; a registration whose upload reference has no stored object fails `VALIDATION_ERROR`). Files whose sniffed content is not an accepted video format MUST be rejected during background processing (`failed` state with recorded reason) — content sniffing requires reading bytes and never happens on the request thread.
- **FR-012**: `GET /admin/wallpapers` MUST return cursor-paginated results including non-public states (`processing`, `failed`) with a `status` filter; `DELETE /admin/wallpapers/{id}` MUST soft-delete (Constitution VI, IX).

**Curated vocabulary management**

- **FR-013**: The system MUST provide admin tag management — create (rejecting the reserved slug `all` and duplicate slugs), list with per-tag usage counts, and delete (refusing with `TAG_IN_USE` when attached to any wallpaper).
- **FR-014**: The system MUST provide admin collection management — create/list/update/delete with ordered `wallpaper_ids` (unknown id → `WALLPAPER_NOT_FOUND`; duplicate slug → `COLLECTION_SLUG_CONFLICT`; cover image via the presigned flow). Reordering MUST replace the ordered membership atomically (Constitution IX).

**Bulk backfill**

- **FR-015**: The system MUST provide an operator-run bulk backfill that, for every seeded wallpaper, locates its original file in the local dataset (via the recorded per-item local path), uploads it to object storage, and processes it through the same pipeline as FR-009 — one processing path, no parallel implementation.
- **FR-016**: The backfill MUST be idempotent and resumable: completed items are skipped on re-run; missing local files are reported and skipped without aborting the run; a summary reports processed/skipped/failed counts. Provenance fields (source URL, license, attribution) MUST be preserved.
- **FR-017**: After a successful backfill, no public-facing media URL may reference the interim third-party CDN.

**Download delivery**

- **FR-018**: `GET /wallpapers/{id}/download-url` MUST return, for a published free wallpaper, a presigned single-object link expiring in ≤ 5 minutes; for premium wallpapers it MUST return `402 ENTITLEMENT_REQUIRED` unconditionally in this phase (entitlement verification arrives in BE-005); for processing/failed/deleted wallpapers it MUST return `404 NOT_FOUND` (Constitution III).

**Audit**

- **FR-019**: Every admin mutation and every sign-in attempt (success and failure) MUST produce an audit record (actor, action, object, timestamp) containing no credentials, tokens, or presigned URLs.

### Key Entities

- **Admin credential pair**: access credential (30 min) + rotating refresh credential (7 days) bound to a Django staff account; grants `/admin/*` only.
- **Upload slot**: a time-limited upload destination plus opaque upload reference; single-use — consumed by exactly one registration.
- **Media renditions**: per wallpaper, three stored artifacts — normalized master (the downloadable file; private zone, non-guessable key, presigned access only), thumbnail and watermarked preview (public-read zone, stable CDN URLs) — plus derived metadata (resolution, duration, size).
- **Processing state**: wallpaper lifecycle `processing → published | failed` (with recorded failure reason); only `published` and non-deleted items are publicly visible (existing invariant).
- **Audit record**: immutable log entry — actor, action, affected object, timestamp.
- **Backfill run state**: per-item completion tracking enabling skip-on-rerun.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: An admin can take a valid video from sign-in to publicly visible — with self-hosted thumbnail and preview — with no manual intervention after registration, and the registration call itself always responds in under 2 seconds regardless of file size.
- **SC-002**: After one completed backfill run, 100% of the 397 seeded wallpapers serve thumbnail and preview from project-controlled storage; zero third-party CDN URLs remain; provenance/attribution intact for all items.
- **SC-003**: An interrupted backfill re-run completes the catalog without duplicating a single stored object and without re-processing any completed item.
- **SC-004**: 100% of cross-tier access attempts are rejected: app-key on any `/admin/*` endpoint, admin credential on any app-tier endpoint — verified by automated tests for every admin endpoint.
- **SC-005**: Free-wallpaper download links work exactly once-per-issue semantics aside, expire within 5 minutes, and serve only their single target file; premium download attempts are refused 100% of the time in this phase.
- **SC-006**: A file that is not a genuine video never becomes publicly visible, regardless of extension or declared content type — verified with disguised-file tests.
- **SC-007**: Every admin mutation in a test run is traceable to an actor and timestamp in the audit trail, and no audit record contains a secret, token, or signed URL.

## Assumptions

- **Storage provider decision is locked**: Cloudflare R2 for `prod` (S3-compatible, zero egress fees — the dominant cost driver for a download-heavy wallpaper app), MinIO container for `dev`. Both are reached through the same S3-compatible interface, so no code path differs by flavor beyond configuration (Constitution VIII).
- **Single admin role**: all Django staff users are equivalent admins in this phase. `FORBIDDEN_ADMIN_ROLE` (403) applies to authenticated-but-not-staff accounts; finer-grained roles are future work.
- **Master format**: the downloadable artifact is a normalized H.264 (high profile) re-encode retaining source resolution — chosen for universal Android/iOS hardware-decoder compatibility. A multi-resolution ladder is out of scope.
- **Preview**: 720p-class, watermarked; thumbnail is a still image extracted from the video.
- **⚠️ Documented deviation from Constitution VII (requires the plan's Complexity Tracking entry)**: malware scanning (ClamAV) is deferred to BE-006. Rationale: in this phase the only upload principals are trusted internal staff accounts, files originate from the operator's own curated dataset or admin-chosen sources, and the scan step slots into the existing task chain later without reshaping the pipeline. Approved by project lead (user) during spec discussion, 2026-07-23.
- **Premium downloads stay closed**: there is no interim "accept any transaction_id" mode; the entitlement gate opens only when BE-005 delivers verification (safe by default).
- **Local dataset availability**: the backfill runs on a machine that has the crawled dataset directory (~22.4 GB); its location is provided by environment/argument, not hard-coded. The committed `data/crawl/` JSONs are the item-to-file mapping.
- **Contract impact**: new surface = admin sign-in/refresh; changed behavior = download-url (real link for free items). Both land as contract v0.4.0 and are synced to `livecanvas-mobile` before implementation (Constitution I). Pending BE-003 contract sync (v0.3.2) rides along or precedes it.
- **Out of scope**: ClamAV/malware scan (BE-006), IAP verification & premium entitlement resolution (BE-005), rate limiting/WAF (BE-006), multi-resolution transcode ladder, admin web UI (API only; Django's built-in admin remains a separate internal-staff tool).

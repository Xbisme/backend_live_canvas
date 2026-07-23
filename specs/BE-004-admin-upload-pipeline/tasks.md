# Tasks: Admin Upload Pipeline (BE-004)

**Input**: Design documents from `specs/BE-004-admin-upload-pipeline/`

**Prerequisites**: [plan.md](plan.md), [spec.md](spec.md), [research.md](research.md),
[data-model.md](data-model.md), [contracts/endpoints.md](contracts/endpoints.md), [quickstart.md](quickstart.md)

**Tests**: CÓ — spec + Constitution X yêu cầu tường minh (cách ly 2 tầng, state machine pipeline,
idempotent backfill, entitlement edge, contract shape). Test đi cùng trong phase của từng story.

**Organization**: nhóm theo user story (US1–US5 map spec.md) để mỗi story test độc lập được.

## Format: `[ID] [P?] [Story?] Description`

- **[P]**: chạy song song được (khác file, không phụ thuộc task chưa xong)
- **[Story]**: US1–US5 — chỉ gắn cho task thuộc phase user story

## Phase 1: Setup — Contract v0.4.0 & hạ tầng dev

**Purpose**: Contract đi trước code (Constitution I); dependency + container nền cho mọi story.

- [x] T001 Cập nhật `docs/screen-inventory.md`: thêm mục "Admin tooling (không phải màn hình app)" — nhu cầu đăng nhập admin, refresh phiên, và ghi chú download-url trả link thật (nguồn cho contract, Constitution I)
- [x] T002 Bump contract **v0.4.0**: `contracts/openapi.yaml` + `.claude/api-context.md` cùng lúc — thêm `POST /admin/auth/login`, `POST /admin/auth/refresh` (shape theo [research.md](research.md) D9), sửa mô tả `GET /wallpapers/{id}/download-url` (bỏ mock; free → presigned ≤5', premium → 402; ghi chú domain S3/R2 ≠ CDN — risk R4), làm rõ ở `POST /admin/wallpapers`: `422 FILE_REJECTED` bắn **đồng bộ lúc register** khi HEAD thấy object > 500MB; lỗi nội dung (sniff) surface bất đồng bộ qua `status=failed`; changelog header; KHÔNG thêm error code mới
- [x] T003 Contract Sync: copy nguyên văn `contracts/openapi.yaml` + `.claude/api-context.md` + `docs/screen-inventory.md` **v0.4.0** (gộp trả nợ v0.3.2) sang repo `livecanvas-mobile` và ghi nhận sync — thủ công, ngoài repo này
- [x] T004 Thêm dependency vào `requirements/base.in` (version đã tra PyPI 2026-07-23 — plan §Technical Context): `djangorestframework-simplejwt==5.5.1`, `celery[redis]==5.6.3`, `redis==8.0.1`, `python-magic==0.4.27`; compile `uv pip compile` cho cả 3 file `requirements/*.txt`; `uv pip sync requirements/dev.txt`; commit cả `.in` + `.txt`
- [x] T005 [P] `docker-compose.yml`: thêm service `redis` và `minio` + job init tạo 2 bucket `livecanvas-private`/`livecanvas-public` (bucket public gắn anonymous-download policy) — theo [quickstart.md](quickstart.md) §1
- [x] T006 [P] Cập nhật `.env.dev.example` + `.env.prod.example`: `AWS_PUBLIC_BUCKET_NAME`, `CELERY_BROKER_URL`, `UPLOAD_MAX_BYTES=524288000`, `BACKFILL_DATASET_DIR` (dev-only); ghi chú biến sẵn có tái dùng (bucket private, CDN_BASE_URL)

**Checkpoint**: contract v0.4.0 frozen + `docker compose up -d db redis minio` chạy được.

---

## Phase 2: Foundational — settings, Celery app, auth tier, storage 2 vùng, schema

**Purpose**: khung chặn mọi story — phải xong hết trước khi vào US1.

- [x] T007 Settings 3 file `config/settings/{base,dev,prod}.py`: `INSTALLED_APPS` += `rest_framework_simplejwt.token_blacklist`, `apps.audit`; block `SIMPLE_JWT` (access 30', refresh 7d, `ROTATE_REFRESH_TOKENS=True`, `BLACKLIST_AFTER_ROTATION=True`); block `CELERY_*` (broker từ env, `task_always_eager` bật được cho test); đọc env mới của T006 (public bucket, size ceiling); prod fail-fast khi thiếu (theo pattern BE-002)
- [x] T008 Thay placeholder `config/celery.py` bằng Celery app thật (`config` namespace, autodiscover tasks) + import app trong `config/__init__.py`; smoke-test `celery -A config worker` boot sạch trên Python local (risk R1 — nếu vỡ, pin venv dev về 3.13 và ghi vào research.md)
- [x] T009 [P] Tầng auth admin trong `core/`: `core/authentication.py` += `AdminJWTAuthentication` (wrap simplejwt, mọi lỗi map qua catalog `UNAUTHORIZED_ADMIN`); `core/permissions.py` += `IsAdminStaff` (user hợp lệ nhưng không `is_staff` → `FORBIDDEN_ADMIN_ROLE` 403); `core/api.py` += `AdminTierAPIView` (đối xứng `AppTierAPIView`, không fallback — Constitution II)
- [x] T010 [P] App mới `apps/audit/`: `apps.py`, `models.py` `AuditLogEntry` ([data-model.md](data-model.md) §3), `services.py` `record(actor, action, obj=None, **metadata)` có **sanitize guard** (raise nếu metadata chứa key/giá trị dạng token/password/signed-URL — FR-019), migration; đăng ký vào Django admin read-only
- [x] T011 [P] `apps/uploads/storage.py`: client 2 vùng theo research D3/D6 — `presign_upload(key, content_type)`, `presign_download(key, ttl=300)`, `public_url(key)`, `upload_file(local_path, key)`, `delete_object(key)`, `head_size(key)`, `read_head(key, n=2048)` (range-GET cho sniff); bucket private/public chọn theo prefix param
- [x] T012 `apps/uploads/models.py`: model `UploadSlot` ([data-model.md](data-model.md) §2) + migration
- [x] T013 `apps/wallpapers/models.py`: thêm 5 field `master_key`, `staging_key`, `thumbnail_key`, `preview_key`, `failure_reason` (nullable — [data-model.md](data-model.md) §1) + migration additive

**Checkpoint**: migrate sạch; `AdminTierAPIView` import được; storage client unit-test với boto3 mock.

---

## Phase 3: User Story 1 — Admin publishes a new wallpaper end-to-end (P1) 🎯 MVP

**Goal**: login → presign → PUT → register → pipeline nền → published với media tự host.

**Independent Test**: quickstart §3 — từ 1 staff user + 1 video thật đến item xuất hiện ở public
list với thumbnail/preview thuộc CDN dev, không thao tác tay sau register; file giả dạng → `failed`.

- [x] T014 [US1] Auth views trong `core/views.py` (hoặc `core/auth_views.py`): `AdminLoginView` (check password + `is_staff` + `is_active`, trả `{access, refresh, expires_in}`, audit `admin.login`/`admin.login_failed` — KHÔNG log password), `AdminRefreshView` (rotate + blacklist); route `admin/auth/login|refresh` trong `core/urls.py`
- [x] T015 [P] [US1] Tests auth: `core/tests/test_admin_auth.py` — login đúng/sai credential (401 `UNAUTHORIZED_ADMIN`), non-staff (403 `FORBIDDEN_ADMIN_ROLE`), disabled account, refresh rotate (refresh cũ chết sau khi dùng), access hết hạn 30' (freeze time), shape đúng contract v0.4.0
- [x] T016 [US1] Presign endpoint: `apps/uploads/serializers.py` (whitelist content_type theo research D4, filename sanitize) + `apps/uploads/views.py` `PresignView(AdminTierAPIView)` tạo `UploadSlot` + trả `{upload_url, upload_key, expires_at}` + audit `upload.presign`; `apps/uploads/urls.py` mount `admin/uploads/presign` vào `config/urls.py`
- [x] T017 [P] [US1] `apps/uploads/ffmpeg.py`: wrappers subprocess theo research D5 — `probe(path)`, `normalize_master(src, dst)`, `extract_thumbnail(src, dst)`, `render_preview(src, dst)` (720p + drawtext watermark + 10s); timeout + stderr rút gọn làm exception message
- [x] T018 [US1] `apps/uploads/services.py`: `consume_slot(key)` (select_for_update, single-use — public service cho app khác gọi, Constitution V), `start_processing(wallpaper)` enqueue; `apps/uploads/tasks.py` `process_wallpaper(wallpaper_id)`: guard idempotent (đã published → no-op) → HEAD size ≤ `UPLOAD_MAX_BYTES` → sniff `read_head` bằng python-magic → tải staging về tmp → probe → normalize/thumb/preview → upload 3 artifact đúng vùng ([data-model.md](data-model.md) §5) → **1 transaction** ghi keys + URLs (`public_url`) + metadata + `status=published` → xóa staging; mọi nhánh fail → `status=failed` + `failure_reason`
- [x] T019 [US1] Admin wallpaper endpoints: `apps/wallpapers/admin_serializers.py` (create: validate `category_id`, `tag_ids` → `TAG_NOT_FOUND`, `upload_key` slot hợp lệ; **HEAD-check đồng bộ lúc register**: object không tồn tại → `VALIDATION_ERROR`, Content-Length > `UPLOAD_MAX_BYTES` → `422 FILE_REJECTED` — remediation A1; list item kèm `status`, `failure_reason`) + `apps/wallpapers/admin_views.py` (`POST/GET /admin/wallpapers` — GET cursor `EnvelopeCursorPagination` + filter `?status=`, `DELETE /admin/wallpapers/{id}` soft-delete) + audit `wallpaper.create`/`wallpaper.delete`; `apps/wallpapers/urls_admin.py` mount vào `config/urls.py`
- [x] T020 [P] [US1] Tests cách ly 2 tầng (SC-004): `core/tests/test_tier_isolation.py` — ma trận: MỌI route `/admin/*` (auth/presign/wallpapers/tags/collections — parametrize từ URLconf) nhận `X-App-Key` hợp lệ → 401 `UNAUTHORIZED_ADMIN`; route app-tier nhận Bearer admin → 401 `INVALID_APP_KEY`
- [x] T021 [P] [US1] Tests pipeline: `apps/uploads/tests/test_pipeline.py` — celery eager + mock storage/ffmpeg/magic: happy path (processing → published atomic, URL từ public zone, staging bị xóa), file giả dạng (`failed` + reason, không leak public — SC-006), quá 500MB (`failed`), retry idempotent (chạy lại task đã published → no-op), double-register slot (`VALIDATION_ERROR`)
- [x] T022 [US1] Tests admin wallpaper CRUD: `apps/wallpapers/tests/test_admin_wallpapers.py` — create 201 shape contract (media null, `processing`), `TAG_NOT_FOUND`, register object thiếu → `VALIDATION_ERROR`, register object > 500MB (mock HEAD) → `422 FILE_REJECTED`, list filter status + cursor envelope, `failure_reason` chỉ ở admin tier, soft-delete 204 rồi biến mất khỏi public

**Checkpoint**: quickstart §3 + §4 pass thủ công; MVP demo được.

---

## Phase 4: User Story 2 — Bulk backfill seeded catalog (P1)

**Goal**: 397 wallpaper seeded chuyển sang media tự host qua đúng pipeline US1.

**Independent Test**: quickstart §5 — chạy full → 0 URL Pexels; Ctrl-C giữa chừng → chạy lại
skip item xong; chạy lần 3 → full-skip.

- [x] T023 [US2] `apps/uploads/management/commands/backfill_media.py`: đọc mapping `local_path`↔`source_url` từ fixture `apps/wallpapers/fixtures/seed_content.json`, chọn wallpaper `master_key IS NULL AND deleted_at IS NULL` (research D7), mỗi item: upload file gốc → `staging/{uuid}`, set `staging_key`, enqueue `process_wallpaper`; flags `--dataset-dir` (default env `BACKFILL_DATASET_DIR`), `--limit`, `--dry-run`; file thiếu trên disk → log + skip; summary `processed/skipped-done/skipped-missing/failed`; audit `backfill.run` (counts trong metadata)
- [x] T024 [US2] Tests backfill: `apps/uploads/tests/test_backfill.py` — mock storage + eager: chạy 2 lần không duplicate (SC-003), item có `master_key` bị skip, file thiếu → skip + đếm đúng, wallpaper soft-deleted không bị đụng, provenance (`source_url`, `license_type`) giữ nguyên sau backfill, sau full-run không còn URL chứa `pexels.com` (SC-002)

**Checkpoint**: chạy backfill thật trên máy dev (dataset local) — quickstart §5.

---

## Phase 5: User Story 3 — Real download-url for free wallpapers (P2)

**Goal**: thay mock bằng presigned GET thật; premium vẫn đóng.

**Independent Test**: quickstart §6 — free → link sống ≤5' tải được từ MinIO; premium → 402;
processing/failed/deleted → 404.

- [x] T025 [US3] Sửa `WallpaperDownloadUrlView` trong `apps/wallpapers/views.py` (+ service nếu cần): wallpaper published + free + có `master_key` → `{download_url: presign_download(master_key, ttl=300), expires_at}`; premium → 402 `ENTITLEMENT_REQUIRED` vô điều kiện; chưa có `master_key` / processing / failed / deleted → 404 `NOT_FOUND`; KHÔNG log URL đã ký
- [x] T026 [P] [US3] Tests download: `apps/wallpapers/tests/test_download_url.py` (cập nhật file BE-003): free → shape contract + TTL ≤ 300s (mock storage trả URL + expiry), premium ± `transaction_id` → 402, ba trạng thái ẩn → 404, wallpaper seeded chưa backfill (`master_key` null) → 404

**Checkpoint**: contract test download khớp v0.4.0.

---

## Phase 6: User Story 4 — Admin curates tags & collections (P2)

**Goal**: CRUD vocabulary curated qua API admin, integrity đúng catalog code.

**Independent Test**: quickstart §7 — tạo/xóa tag với đủ nhánh lỗi; collection ordered + reorder
atomic quan sát được qua public detail.

- [x] T027 [US4] Admin tags: serializer + views `POST/GET /admin/tags`, `DELETE /admin/tags/{id}` trong `apps/wallpapers/admin_views.py` (+ `apps/wallpapers/services.py` `delete_tag` check in-use → `TAG_IN_USE` 409; create qua validator reserved-slug sẵn có; GET kèm `wallpaper_count`); audit `tag.create`/`tag.delete`; route vào `apps/wallpapers/urls_admin.py`
- [x] T028 [US4] Admin collections: serializer (validate `wallpaper_ids` tồn tại → `WALLPAPER_NOT_FOUND`; slug trùng → `COLLECTION_SLUG_CONFLICT` 409; `cover_upload_key` = slot image consume + sniff image + đẩy vào public zone prefix `covers/` ([data-model.md](data-model.md) §5) — research D4/plan) + views `POST/GET /admin/collections`, `PATCH/DELETE /admin/collections/{id}`; reorder thay thế atomic trong transaction (pattern delete+bulk_create như seeder — [data-model.md](data-model.md) §7); audit `collection.*`
- [x] T029 [P] [US4] Tests curated CRUD: `apps/wallpapers/tests/test_admin_curated.py` — tag: create/dup slug/reserved `all`/`TAG_IN_USE`/count; collection: ordered items đúng position qua public detail, reorder atomic, `WALLPAPER_NOT_FOUND`, `COLLECTION_SLUG_CONFLICT`, cover qua slot; tất cả route đã nằm trong ma trận T020

**Checkpoint**: US4 độc lập pass; public collection detail phản ánh order mới ngay.

---

## Phase 7: User Story 5 — Admin actions are auditable (P3)

**Goal**: chứng minh độ phủ audit (ghi đã wire trong T014/T016/T019/T023/T027/T028).

**Independent Test**: spec US5 — mỗi mutation admin trong test run sinh đúng 1 record sạch secret.

- [x] T030 [US5] Tests audit: `apps/audit/tests/test_audit.py` — mỗi action (login ok/fail, presign, register, wallpaper delete, tag create/delete, collection create/update/delete, backfill) sinh record đúng `action`/`actor_label`; login-fail không chứa password; sanitize guard raise khi metadata chứa token/URL ký (unit test guard T010); record append-only (không API sửa/xóa)

---

## Phase 8: Polish & Cross-Cutting

- [x] T031 [P] `apps/uploads/management/commands/purge_stale_uploads.py`: liệt kê (`--dry-run` mặc định) và xóa (`--delete`) `UploadSlot` chưa consume > 24h + object staging tương ứng; test nhỏ trong `apps/uploads/tests/test_purge.py`
- [x] T032 [P] Cập nhật docs vận hành: `README.md` (prereq `brew install ffmpeg libmagic`, chạy worker, MinIO console) + `CLAUDE.md` §Common commands (worker + backfill + purge) — mirror đúng constitution, không mâu thuẫn
- [x] T033 [P] Cập nhật `.claude/project-context.md` + `.claude/sdd-roadmap.md` (BE-003 ✅ merged + dataset thật đã seed; BE-004 trạng thái + quyết định R2/2-bucket/simplejwt; xóa mục "Chưa quyết định: S3 provider") + `.claude/changelog.md` khi merge
- [x] T034 Chạy toàn bộ quickstart end-to-end trên dev stack thật (MinIO + Redis + worker + ffmpeg thật, không mock) — đối chiếu bảng Expected outcomes ở [quickstart.md](quickstart.md); ghi lệch (nếu có) thành issue/fix trước khi đóng
- [x] T035 Gates cuối: `ruff check . && ruff format --check .` + `pytest` + `python manage.py makemigrations --check --dry-run` + `DJANGO_SETTINGS_MODULE=config.settings.prod python manage.py check --deploy` (với `.env.prod` giả lập đủ biến) — tất cả sạch

---

## Dependencies & Execution Order

```
Phase 1 (T001→T002→T003 tuần tự; T004; T005,T006 [P])
  └─▶ Phase 2 (T007→T008; T009,T010,T011 [P] sau T007; T012,T013 sau T007)
        └─▶ Phase 3 US1 (T014→T015; T016→T018; T017 [P]; T019 sau T016,T018; T020–T022 sau T019)
              ├─▶ Phase 4 US2 (T023→T024) — cần pipeline T018
              ├─▶ Phase 5 US3 (T025→T026) — cần storage T011 + master_key từ pipeline/backfill
              └─▶ Phase 6 US4 (T027,T028→T029) — cần T009 + slot T012 (cover)
                    └─▶ Phase 7 US5 (T030) — cần mọi mutation đã wire audit
                          └─▶ Phase 8 (T031–T033 [P]; T034 sau TẤT CẢ; T035 cuối)
```

- US2/US3/US4 **độc lập lẫn nhau** sau khi US1 xong — có thể làm song song.
- T003 (sync mobile) không chặn code local nhưng PHẢI xong trước khi merge (Constitution I).

## Parallel Example (sau khi US1 xong)

```
Track A: T023 → T024        (backfill)
Track B: T025 → T026        (download-url)
Track C: T027 → T028 → T029 (curated CRUD)
```

## Implementation Strategy

- **MVP = Phase 1 + 2 + US1** (T001–T022): demo được vòng đời upload đầy đủ trên dev stack.
- Tăng trưởng theo lát: mỗi phase sau là increment độc lập, test độc lập (Independent Test ghi ở đầu phase).
- Backfill thật (T034 phần §5 quickstart) chạy cuối cùng trên máy có dataset — mọi thứ trước đó xanh bằng mock.

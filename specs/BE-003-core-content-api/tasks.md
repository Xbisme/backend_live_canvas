---
description: "Task list — BE-003 Core Content API"
---

# Tasks: Core Content API (BE-003)

**Input**: Design documents from `specs/BE-003-core-content-api/`

**Prerequisites**: [plan.md](plan.md), [spec.md](spec.md), [research.md](research.md),
[data-model.md](data-model.md), [contracts/endpoints.md](contracts/endpoints.md), [quickstart.md](quickstart.md)

**Tests**: ĐƯỢC BAO GỒM — Constitution X bắt buộc test cho auth `X-App-Key`, cursor pagination (gồm
invalid cursor), curated integrity (thứ tự collection), và envelope lỗi. Contract v0.3.2 (thẻ ảo "All").

**Organization**: Tasks nhóm theo user story để implement + test độc lập. Tầng nền BE-002 tái sử dụng
nguyên vẹn (`core.api.AppTierAPIView`, `core.pagination.EnvelopeCursorPagination`,
`core.exception_handler`, `core.errors`). App đích: `apps/wallpapers/`.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: chạy song song được (khác file, không phụ thuộc task chưa xong)
- **[Story]**: US1..US5 (map tới user story trong spec.md); Setup/Foundational/Polish không gắn nhãn

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Khởi tạo khung module cho app content.

- [X] T001 Tạo skeleton các module rỗng trong `apps/wallpapers/`: `serializers.py`, `services.py`, `views.py`, `urls.py`, `admin.py` (stub tối thiểu, import sạch) + `apps/wallpapers/tests/__init__.py`

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Model, migration, serializer/service dùng chung, wiring URL, exception — nền cho MỌI story.

**⚠️ CRITICAL**: Không story nào bắt đầu được cho tới khi phase này xong.

- [X] T002 Implement 5 model + `WallpaperQuerySet.published()` manager trong `apps/wallpapers/models.py` (`Category`, `Tag`, `Wallpaper` [status, deleted_at, created_at, index `(created_at, id)`/`is_premium`/`deleted_at`], `Collection`, `CollectionItem` [position, unique_together] — đúng [data-model.md](data-model.md)). Gồm hằng `RESERVED_TAG_SLUGS = {"all"}` + `validate_tag_slug` gọi trong `Tag.clean()` (chặn slug reserved ở **tầng model** cho mọi caller — U2)
- [X] T003 [P] Thêm exception `EntitlementRequired(AppError)` (code `ENTITLEMENT_REQUIRED`, 402) trong `core/errors.py` (mã đã khai báo, chỉ thiếu class — không đổi contract)
- [X] T004 Sinh migration `apps/wallpapers/migrations/0001_initial.py` qua `makemigrations` (kèm index; non-destructive) và xác nhận `makemigrations --check --dry-run` sạch
- [X] T005 [P] Đăng ký 5 model trong `apps/wallpapers/admin.py` (internal-staff curation, session auth); admin form gọi `full_clean()` để `Tag.clean()` (validator reserved-slug ở T002) áp dụng — không tự viết lại logic chặn slug
- [X] T006 [P] Tạo factory-boy factories trong `apps/wallpapers/tests/factories.py` (Category/Tag/Wallpaper/Collection/CollectionItem; helper tạo wallpaper published/hidden)
- [X] T007 Implement serializers dùng chung trong `apps/wallpapers/serializers.py`: `CategorySerializer`, `TagSerializer`, `CollectionRefSerializer` (mini id/slug/title/cover_url/is_premium), `CollectionMetaSerializer` (+`wallpaper_count`), `WallpaperListSerializer` (`collections: []`), `WallpaperDetailSerializer` (`collections` populate) — đúng [data-model.md](data-model.md) (depends T002)
- [X] T008 Implement helper service trong `apps/wallpapers/services.py`: annotate `wallpaper_count` (chỉ `published()`) cho Category/Tag/Collection; helper lấy queryset `published()` (depends T002)
- [X] T009 Tạo `apps/wallpapers/urls.py` (urlpatterns rỗng ban đầu) và include vào `config/urls.py` dưới product API (tách khỏi health của `core`)
- [X] T010 Gỡ probe tạm BE-002: xoá 4 route `_probe/*` trong `core/urls.py` + các view `AppTierProbeView/ProbeValidationView/ProbeNotFoundView/ProbeBoomView` trong `core/views.py`; chuyển/loại test probe tương ứng trong `core/tests/`

**Checkpoint**: Model + migration + serializer/service nền sẵn sàng — các story bắt đầu được.

---

## Phase 3: User Story 1 - Duyệt & khám phá hình nền (Priority: P1) 🎯 MVP

**Goal**: `GET /categories`, `GET /tags` (+ thẻ ảo "All"), `GET /wallpapers` (cursor + filter
category/tags-AND/orientation/is_premium/search, sắp xếp mới→cũ).

**Independent Test**: Seed vài category + wallpaper published/hidden; gọi list với các tổ hợp filter +
phân trang cursor; `GET /tags` có thẻ ảo "All" ở [0].

### Tests for User Story 1 ⚠️ (viết trước, phải FAIL trước khi implement)

- [X] T011 [P] [US1] `apps/wallpapers/tests/test_categories_tags.py`: list + `wallpaper_count` chỉ đếm published; 401 `INVALID_APP_KEY`; 405 `METHOD_NOT_ALLOWED`; **thẻ ảo "All" tại [0]** (`id:0, slug:"all", wallpaper_count=tổng published`); không tag thật slug `all`
- [X] T012 [P] [US1] `apps/wallpapers/tests/test_wallpapers_list.py`: envelope `{items,next_cursor,has_more}`; cursor hợp lệ (không trùng/nhảy khi chèn bản ghi) + invalid cursor→400; `limit>100`→400; `tags=a,b` AND; `tags=all`/không tags→toàn bộ mới→cũ; filter category/orientation/is_premium; `search` khớp title; chỉ trả published (ẩn/xoá không rò rỉ)

### Implementation for User Story 1

- [X] T013 [US1] `CategoryListView` + `TagListView` trong `apps/wallpapers/views.py` (kế thừa `AppTierAPIView`); service dựng danh sách tags **prepend thẻ ảo "All"** (`id:0, slug:"all", name:"Tất cả", wallpaper_count=tổng published`) trong `services.py`
- [X] T014 [US1] `build_wallpaper_queryset(params)` trong `apps/wallpapers/services.py`: base `published()`; filter category slug; `tags` AND (nhiều `.filter(tags__slug=)`), **strip slug reserved `all`**; orientation; is_premium; search `title__icontains`; validate giá trị sai → raise để handler trả `VALIDATION_ERROR`
- [X] T015 [US1] `WallpaperListView` trong `views.py` với pagination subclass ordering `("-created_at","-id")` (kế thừa `EnvelopeCursorPagination`) — dùng `build_wallpaper_queryset`. **Bắt buộc**: subclass bọc/override để **cursor hỏng/hết hạn → `400 VALIDATION_ERROR`** (bắt `NotFound` từ `decode_cursor`, KHÔNG để DRF trả 404) — Constitution VI, R1; cover bằng test T012 invalid-cursor
- [X] T016 [US1] Khai báo route `/categories`, `/tags`, `/wallpapers` trong `apps/wallpapers/urls.py`

**Checkpoint**: US1 chạy độc lập — MVP duyệt/lọc/tìm kiếm + thẻ ảo All.

---

## Phase 4: User Story 2 - Xem chi tiết một hình nền (Priority: P1)

**Goal**: `GET /wallpapers/{id}` trả detail với `collections` populate đầy đủ.

**Independent Test**: Gọi detail cho wallpaper thuộc ≥1 collection → `collections` đầy đủ; id ẩn/không tồn tại → 404.

### Tests for User Story 2 ⚠️

- [X] T017 [P] [US2] `apps/wallpapers/tests/test_wallpaper_detail.py`: 200 detail + `collections: CollectionRef[]` populate; 404 `NOT_FOUND` cho id không tồn tại / không `published()`; 401

### Implementation for User Story 2

- [X] T018 [US2] `WallpaperDetailView` trong `views.py` (dùng `WallpaperDetailSerializer`, `get_object` trên `published()` → `Http404` nếu không thấy)
- [X] T019 [US2] Thêm route `/wallpapers/{id}` trong `apps/wallpapers/urls.py`

**Checkpoint**: US1 + US2 độc lập.

---

## Phase 5: User Story 3 - Đồng bộ Favorites (Priority: P2)

**Goal**: `POST /wallpapers/batch` — lấy data mới nhất theo danh sách id, bỏ qua id thiếu.

**Independent Test**: Batch với id tồn tại + không tồn tại + ẩn → chỉ trả id published tồn tại; ≤100 enforce.

### Tests for User Story 3 ⚠️

- [X] T020 [P] [US3] `apps/wallpapers/tests/test_wallpaper_batch.py`: mix id tồn tại/thiếu → bỏ qua âm thầm; `ids` rỗng hoặc >100 → 400 `VALIDATION_ERROR`; id của wallpaper ẩn không trả; 401

### Implementation for User Story 3

- [X] T021 [US3] `WallpaperBatchView` (POST) trong `views.py` + serializer validate `ids` (1..100 int) trong `serializers.py`; lọc `published().filter(id__in=ids)`, serialize `WallpaperListSerializer`
- [X] T022 [US3] Thêm route `/wallpapers/batch` trong `apps/wallpapers/urls.py`

**Checkpoint**: US1–US3 độc lập.

---

## Phase 6: User Story 4 - Duyệt bộ sưu tập (Priority: P2)

**Goal**: `GET /collections` (meta, không items) + `GET /collections/{id}` (nhúng items đúng thứ tự `position`).

**Independent Test**: Seed collection với thứ tự cụ thể → list có `wallpaper_count`, detail trả `items`
đúng thứ tự, chỉ thành viên published; premium collection vẫn trả đầy đủ; id sai → 404.

### Tests for User Story 4 ⚠️

- [X] T023 [P] [US4] `apps/wallpapers/tests/test_collections.py`: list meta + `wallpaper_count`, không `items`; detail `items` đúng thứ tự `position`, chỉ published; premium vẫn trả đầy đủ (không gate); 404 `NOT_FOUND`; 401

### Implementation for User Story 4

- [X] T024 [US4] `CollectionListView` trong `views.py` (`CollectionMetaSerializer` + annotate count, không phân trang)
- [X] T025 [US4] `CollectionDetailView` trong `views.py`: nhúng `items` từ `CollectionItem` order theo `position`, join wallpaper `published()`, serialize `WallpaperDetailSerializer`; `Http404` nếu không thấy
- [X] T026 [US4] Thêm route `/collections`, `/collections/{id}` trong `apps/wallpapers/urls.py`

**Checkpoint**: US1–US4 độc lập.

---

## Phase 7: User Story 5 - Lấy link tải (đường đi tạm) (Priority: P3)

**Goal**: `GET /wallpapers/{id}/download-url` — non-premium→200 mock; premium→402; ẩn/không tồn tại→404.

**Independent Test**: Gọi download-url cho non-premium (200 `{download_url,expires_at≤5m}`), premium (402
`ENTITLEMENT_REQUIRED`), id sai (404).

### Tests for User Story 5 ⚠️

- [X] T027 [P] [US5] `apps/wallpapers/tests/test_download_url.py`: non-premium 200 shape + `expires_at ≤ now+5m`; premium 402 `ENTITLEMENT_REQUIRED`; id không tồn tại/ẩn 404; 401

### Implementation for User Story 5

- [X] T028 [US5] `build_download_url(wallpaper)` trong `services.py`: 404 nếu không `published()`; raise `EntitlementRequired` nếu `is_premium`; else trả `{download_url: <CDN_BASE_URL/source_url mock>, expires_at: now+5m ISO8601}`
- [X] T029 [US5] `WallpaperDownloadUrlView` trong `views.py` + route `/wallpapers/{id}/download-url` trong `urls.py`

**Checkpoint**: Toàn bộ 8 endpoint hoạt động.

---

## Phase 8: Polish & Cross-Cutting Concerns

**Purpose**: Seed nội dung, đồng bộ contract, chạy gate.

- [X] T030 [P] Tạo fixture cố định `apps/wallpapers/fixtures/seed_content.json` (Category/Tag/Wallpaper/Collection + quan hệ ordered, mỗi wallpaper có `source_url`+`license_type` từ Pixabay/Pexels/Mixkit) và management command `apps/wallpapers/management/commands/seed_content.py` (idempotent qua `update_or_create` theo slug) — FR-016
- [X] T031 [P] `apps/wallpapers/tests/test_seed_command.py`: chạy 2 lần không nhân bản (idempotent); `source_url`/`license_type` set; không tạo tag thật slug `all` (fixture/command tôn trọng `validate_tag_slug` từ T002)
- [ ] T032 Contract Sync: copy nguyên văn `.claude/openapi.yaml` + `.claude/api-context.md` + `.claude/screen-inventory.md` (v0.3.2) sang repo `livecanvas-mobile` và ghi nhận sync (Constitution I) — thủ công, ngoài repo này
- [X] T033 Chạy full gate + quickstart: `ruff check . && ruff format --check .`, `pytest apps/wallpapers`, `makemigrations --check --dry-run`, và smoke test thủ công theo [quickstart.md](quickstart.md)

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (P1)**: không phụ thuộc — bắt đầu ngay.
- **Foundational (P2)**: phụ thuộc Setup — **BLOCKS mọi user story**. Trong đó: T002 (models) chặn T004/T006/T007/T008; T003 độc lập; T009/T010 độc lập tương đối.
- **User Stories (P3–P7)**: đều phụ thuộc Foundational xong. Sau đó có thể chạy song song (khác nhóm view class), hoặc tuần tự P1→P3.
- **Polish (P8)**: sau khi các story mong muốn đã xong (T033 chạy cuối cùng).

### User Story Dependencies

- **US1 (P1)**: sau Foundational — không phụ thuộc story khác (MVP).
- **US2 (P1)**: sau Foundational — độc lập (dùng detail serializer nền).
- **US3 (P2)**: sau Foundational — độc lập.
- **US4 (P2)**: sau Foundational — độc lập (cần `CollectionItem` từ T002).
- **US5 (P3)**: sau Foundational — cần `EntitlementRequired` (T003) + `CDN_BASE_URL` (đã có).

### Within Each User Story

- Test (⚠️) viết trước và FAIL trước khi implement.
- Service/query trước view; view trước route.
- Story hoàn tất → sang story ưu tiên kế.

### Parallel Opportunities

- Foundational: T003, T005, T006 [P] (khác file, sau/không cần T002 tuỳ task — T005/T006 cần T002).
- Mỗi story: task test [P] chạy song song với nhau (khác file test).
- Sau Foundational: US1–US5 có thể phân cho nhiều người (mỗi story thêm view class riêng; lưu ý `views.py`/`urls.py` dùng chung → phối hợp khi merge).
- Polish: T030, T031 [P].

---

## Parallel Example: Foundational

```bash
# Sau khi T002 (models) xong, chạy song song:
Task: "T005 Đăng ký model trong apps/wallpapers/admin.py"
Task: "T006 Tạo factories trong apps/wallpapers/tests/factories.py"
# Độc lập T002:
Task: "T003 Thêm EntitlementRequired trong core/errors.py"
```

## Parallel Example: User Story tests

```bash
# Mỗi story có 1 file test riêng — chạy song song khi tới phase tương ứng:
Task: "T011 test_categories_tags.py"   # US1
Task: "T012 test_wallpapers_list.py"    # US1
```

---

## Implementation Strategy

### MVP First (User Story 1)

1. Phase 1 Setup → 2. Phase 2 Foundational (CRITICAL) → 3. Phase 3 US1 →
4. **STOP & VALIDATE**: test US1 độc lập (Browse/lọc/tìm kiếm + thẻ ảo All) → 5. Demo cho mobile (một phần MO-002).

### Incremental Delivery

Foundational → US1 (MVP) → US2 → US3 → US4 → US5 → Polish (seed + sync contract + gate).
Mỗi story thêm giá trị mà không phá story trước. Sau US1–US4 mobile đã chuyển được Browse/Detail/
Favorites/Collections khỏi mock (điểm đồng bộ MO-002); US5 mở đường download; entitlement thật ở BE-005.

---

## Notes

- [P] = khác file, không phụ thuộc. [Story] để truy vết.
- Contract v0.3.2 đóng băng — KHÔNG đổi shape khi implement; lệch → dừng, sửa contract trước (Constitution I).
- Không mở endpoint tầng admin nào (`/admin/tags` hoãn BE-004) — Constitution II.
- Verify test FAIL trước khi implement; commit sau mỗi task/nhóm hợp lý.
- Gate bắt buộc trước commit: `ruff`, `pytest`, `makemigrations --check` (Constitution X, XI).

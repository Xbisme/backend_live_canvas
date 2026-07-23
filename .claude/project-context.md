# LiveCanvas Backend — Project Context

> Repo: `livecanvas-backend` (Django + DRF)
> Repo liên quan: `livecanvas-mobile` (Flutter, độc lập hoàn toàn — đồng bộ qua `contracts/openapi.yaml` + `.claude/api-context.md`, copy tay giữa 2 repo)
>
> Last updated: 2026-07-23 (BE-001 + BE-002 đã merge · contract v0.3.2 — thẻ ảo "All" ở /tags · đang plan BE-003 Core Content API)
> **Mục đích**: Snapshot tối thiểu để bắt đầu 1 session làm việc trên repo backend.
>
> **Đọc file nào khi nào**:
> - Bắt đầu session mới → file này + `docs/PRD.md` + `CLAUDE.md` (khi có).
> - Chuẩn bị họp spec mới → file này + [`sdd-roadmap.md`](sdd-roadmap.md).
> - **Trước khi đổi/thêm bất kỳ API nào** → [`../docs/screen-inventory.md`](../docs/screen-inventory.md) TRƯỚC TIÊN (màn hình cần gì quyết định API, không phải ngược lại), rồi mới tới `api-context.md`.
> - Cần biết chi tiết từng endpoint (header/body/response) → [`api-context.md`](api-context.md) + [`openapi.yaml`](openapi.yaml) — **contract version hiện tại: `v0.3.2`**.
> - Cần hiểu vì sao spec X ra đời → [`decisions/`](decisions/).
> - Cần biết spec nào ship khi nào → [`changelog.md`](changelog.md).

## Snapshot

- **Vai trò repo này**: Backend cho app hình nền động LiveCanvas — cung cấp API public (wallpaper/category/tag/collection), API admin upload nội dung + quản lý tag/collection, và xác thực IAP (verify-receipt tự viết, không dùng RevenueCat).
- **Stack**: Django + Django REST Framework, PostgreSQL, S3-compatible storage + CDN, Celery + Redis (transcode/scan bất đồng bộ).
- **Không có hệ thống user/account** — entitlement premium xác định qua `transaction_id` (App Store/Play), verify trực tiếp với Apple/Google, không qua login.
- **2 tầng auth hoàn toàn tách biệt**: `X-App-Key` (app, không phải user) cho endpoint public/IAP · `Authorization: Bearer <jwt>` cho endpoint `/admin/*`. Không bao giờ trộn 2 tầng này.
- **Communication**: Tiếng Việt giữa user + Claude · Tiếng Anh cho code/comment/commit.

## Current Focus

- **Trạng thái**: BE-001 (bootstrap 2-flavor + constitution) và BE-002 (foundation: DRF, app skeleton, X-App-Key gate, error envelope, storage config) đã merge vào `main`.
- **Đã có sẵn**:
  - `docs/screen-inventory.md` — danh sách màn hình + data cần, làm nền cho contract (đã review, 1 giả định còn treo: Onboarding không cần data riêng).
  - `.claude/openapi.yaml` v0.3.2 + `.claude/api-context.md` v0.3.2 — cursor-based pagination, resource `Tag` curated (+ **thẻ ảo "All"** id=0/slug=all ở đầu `GET /tags`, reserved slug), `POST /wallpapers/batch` cho Favorites, resource `Collection` curated (bộ sưu tập có thứ tự) + `GET /collections`, `GET /collections/{id}`, admin `/admin/collections`; error code `SERVER_ERROR`, `METHOD_NOT_ALLOWED`.
  - ⚠️ **Chưa sync sang `livecanvas-mobile`**: contract v0.3.2 (openapi.yaml + api-context.md + screen-inventory.md) cần copy nguyên văn sang repo mobile (Contract Sync).
  - `core/` — api (`AppTierAPIView`), authentication (`AppKeyAuthentication`), errors (catalog), exception_handler, pagination (cursor envelope), permissions, urls, views. Apps `wallpapers|uploads|iap` mới có `apps.py` + `migrations/`, **chưa có model nghiệp vụ**.
- **Spec tiếp theo**: `BE-003-core-content-api` — models `Category`/`Tag`/`Wallpaper`/`Collection` + public content API (list/detail/filter/search, cursor pagination), admin `/admin/tags`, seed script, `download-url` mock/`501` tạm. ⚠️ Điểm đồng bộ với repo mobile (MO-002).
- **Quyết định kỹ thuật đã chốt** (ảnh hưởng schema DB):
  - Pagination: cursor-based (keyset), không dùng offset `page`/`page_size`.
  - Tag: curated — model `Tag` many-to-many với `Wallpaper`, admin chỉ chọn `tag_ids` có sẵn khi upload, tạo tag mới qua endpoint riêng `/admin/tags`.
  - Collection (bộ sưu tập): curated — many-to-many **có thứ tự** với `Wallpaper` (bảng nối lưu `position`); `GET /collections` không phân trang, `GET /collections/{id}` nhúng `items` đúng thứ tự; entitlement bộ premium vẫn quyết ở `download-url` từng file ("Tải tất cả" = client lặp gọi download-url).
- **Chưa quyết định**:
  - Tên sản phẩm thật + domain API production.
  - Nhà cung cấp S3-compatible (AWS S3 / Cloudflare R2 / DO Spaces) + CDN đi kèm.
  - Danh sách wallpaper seed ban đầu (Pixabay/Pexels/Mixkit) — cần trước `BE-003`.
  - Có cần mục "Nổi bật/Trending" riêng (field `is_featured`) không — hiện Onboarding đang giả định mở thẳng vào Browse mặc định.

## Repo Layout

```
.claude/
├── project-context.md      # ← you are here
├── sdd-roadmap.md           # spec planning (chỉ track BE-*)
├── dev-workflow.md          # quy trình speckit + Contract Sync với repo mobile
├── api-context.md           # chi tiết header/body/response từng endpoint
├── changelog.md
└── decisions/

contracts/
└── openapi.yaml              # bản sao — đồng bộ tay với repo mobile khi đổi API

config/                       # Django settings: base.py + 2 flavor (dev.py, prod.py) — KHÔNG staging; celery.py
apps/
├── wallpapers/                # Category, Wallpaper models + public API
├── uploads/                   # Admin upload, presigned URL, transcode pipeline
└── iap/                       # verify-receipt, webhook Apple/Google, entitlement
requirements/                  # base.txt, dev.txt, prod.txt
specs/                         # BE-NNN-*/ folders (speckit output)
docs/
├── PRD.md                     # product requirements (phần liên quan backend)
└── screen-inventory.md        # màn hình + data cần — nền tảng của contract, đọc TRƯỚC api-context.md
manage.py
```

## Key Documents

| File | Vai trò |
|---|---|
| [`../docs/screen-inventory.md`](../docs/screen-inventory.md) | Màn hình cần gì → đọc TRƯỚC khi sửa API |
| [`api-context.md`](api-context.md) | Chi tiết endpoint: header, request body, response thành công/lỗi |
| [`../contracts/openapi.yaml`](../contracts/openapi.yaml) | API contract máy-đọc — nguồn để generate code |
| [`sdd-roadmap.md`](sdd-roadmap.md) | Spec planning track backend |
| [`dev-workflow.md`](dev-workflow.md) | Quy trình speckit + Contract Sync giữa 2 repo |
| [`changelog.md`](changelog.md) | Ship history (append-only) |

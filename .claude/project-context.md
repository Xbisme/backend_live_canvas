# LiveCanvas Backend — Project Context

> Repo: `livecanvas-backend` (Django + DRF)
> Repo liên quan: `livecanvas-mobile` (Flutter, độc lập hoàn toàn — đồng bộ qua `contracts/openapi.yaml` + `.claude/api-context.md`, copy tay giữa 2 repo)
>
> Last updated: 2026-07-23 (BE-001→003 merged · **BE-004 implemented** trên branch `BE-004-admin-upload-pipeline` · contract **v0.4.0** · ✅ đã sync mobile 2026-07-23)
> **Mục đích**: Snapshot tối thiểu để bắt đầu 1 session làm việc trên repo backend.
>
> **Đọc file nào khi nào**:
> - Bắt đầu session mới → file này + `docs/PRD.md` + `CLAUDE.md` (khi có).
> - Chuẩn bị họp spec mới → file này + [`sdd-roadmap.md`](sdd-roadmap.md).
> - **Trước khi đổi/thêm bất kỳ API nào** → [`../docs/screen-inventory.md`](../docs/screen-inventory.md) TRƯỚC TIÊN (màn hình cần gì quyết định API, không phải ngược lại), rồi mới tới `api-context.md`.
> - Cần biết chi tiết từng endpoint (header/body/response) → [`api-context.md`](api-context.md) + [`openapi.yaml`](openapi.yaml) — **contract version hiện tại: `v0.4.0`**.
> - Cần hiểu vì sao spec X ra đời → [`decisions/`](decisions/).
> - Cần biết spec nào ship khi nào → [`changelog.md`](changelog.md).

## Snapshot

- **Vai trò repo này**: Backend cho app hình nền động LiveCanvas — cung cấp API public (wallpaper/category/tag/collection), API admin upload nội dung + quản lý tag/collection, và xác thực IAP (verify-receipt tự viết, không dùng RevenueCat).
- **Stack**: Django + Django REST Framework, PostgreSQL, S3-compatible storage + CDN, Celery + Redis (transcode/scan bất đồng bộ).
- **Không có hệ thống user/account** — entitlement premium xác định qua `transaction_id` (App Store/Play), verify trực tiếp với Apple/Google, không qua login.
- **2 tầng auth hoàn toàn tách biệt**: `X-App-Key` (app, không phải user) cho endpoint public/IAP · `Authorization: Bearer <jwt>` cho endpoint `/admin/*`. Không bao giờ trộn 2 tầng này.
- **Communication**: Tiếng Việt giữa user + Claude · Tiếng Anh cho code/comment/commit.

## Current Focus

- **Trạng thái**: BE-001→BE-003 đã merge vào `main`. **BE-004 đã implement đầy đủ** trên branch `BE-004-admin-upload-pipeline` (SDD trọn chuỗi specify→clarify→plan→tasks→analyze→implement; toàn bộ tests xanh) — chờ quickstart end-to-end + review/merge.
- **Đã có sẵn**:
  - Catalog thật: **397 wallpaper Pexels** (dataset local ~22.4 GB tại `~/Documents/database/crawl_script/livewallpapers`; metadata commit ở `data/crawl/`; fixture sinh bởi `scripts/build_seed_fixture.py` → `manage.py seed_content`). 5 categories / 21 curated tags / 83 premium / 5 collections.
  - Contract **v0.4.0** (`.claude/openapi.yaml` + `api-context.md`): + `POST /admin/auth/login|refresh` (JWT access 30'/refresh 7d rotate), download-url presigned thật ≤5' cho free (premium 402 tới BE-005), 422 FILE_REJECTED đồng bộ khi >500MB, bỏ server Staging.
  - BE-004 stack: admin tier (`AdminTierAPIView`/`AdminJWTAuthentication`/`IsAdminStaff` trong `core`), storage 2 vùng (bucket private staging+masters / public thumbs+previews+covers; MinIO dev qua docker-compose, R2 prod), pipeline Celery+Redis (magic-byte sniff → H.264 normalize → thumbnail → preview 720p watermark; state machine processing→published|failed, idempotent theo `master_key`), admin CRUD wallpapers/tags/collections + app `apps/audit` (append-only, sanitize guard), `backfill_media` + `purge_stale_uploads`.
  - ✅ **Đã sync `livecanvas-mobile`** (2026-07-23): contract v0.4.0 copy nguyên văn (openapi.yaml → `.claude/` + `contracts/`, api-context.md, screen-inventory.md) + ghi chú vào changelog mobile. Mobile cần regenerate `packages/livecanvas_api` và chuyển mock → API thật (MO-002).
- **Việc còn treo của BE-004**: (1) chạy nốt `backfill_media` full 397 (đã verify 3 item thật end-to-end; resumable); (2) tạo bucket R2 + CDN khi lên prod.
- **Spec tiếp theo**: `BE-005-iap-verify-entitlement` — verify-receipt, webhook Apple/Google, mở gate entitlement thật ở download-url.
- **Quyết định kỹ thuật đã chốt** (ảnh hưởng schema DB):
  - Pagination: cursor-based (keyset), không dùng offset `page`/`page_size`.
  - Tag: curated — model `Tag` many-to-many với `Wallpaper`, admin chỉ chọn `tag_ids` có sẵn khi upload, tạo tag mới qua endpoint riêng `/admin/tags`.
  - Collection (bộ sưu tập): curated — many-to-many **có thứ tự** với `Wallpaper` (bảng nối lưu `position`); `GET /collections` không phân trang, `GET /collections/{id}` nhúng `items` đúng thứ tự; entitlement bộ premium vẫn quyết ở `download-url` từng file ("Tải tất cả" = client lặp gọi download-url).
- **Đã chốt thêm (BE-004)**: storage = **Cloudflare R2** (egress free) + MinIO dev, mô hình 2 bucket public/private; admin JWT = simplejwt (login endpoint, access 30'/refresh 7d rotate); master H.264 giữ resolution; preview 720p watermark 10s; trần upload 500 MB; ClamAV hoãn BE-006 (deviation có phê duyệt).
- **Chưa quyết định**:
  - Tên sản phẩm thật + domain API production (+ tài khoản Cloudflare/R2 bucket thật).
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

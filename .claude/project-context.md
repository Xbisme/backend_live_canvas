# LiveCanvas Backend — Project Context

> Repo: `livecanvas-backend` (Django + DRF)
> Repo liên quan: `livecanvas-mobile` (Flutter, độc lập hoàn toàn — đồng bộ qua `contracts/openapi.yaml` + `.claude/api-context.md`, copy tay giữa 2 repo)
>
> Last updated: 2026-07-27 (BE-001→**BE-004 merged** vào `main` — PR #4+#5 · **BE-005 IAP implemented** trên branch, 196 tests xanh · **Contract Sync v0.5.0 → mobile ĐÃ XONG** (2026-07-26) · contract hiện tại **v0.7.1** · spec tiếp theo: **BE-006 Security**)
>
> ✅ **BE-008 (2 ask mobile) đã IMPLEMENT XONG trên branch `BE-008-mobile-driven-content` (2026-07-29)** — contract **v0.7.1**, 240 tests xanh, đã sync mobile:
> (1) `Wallpaper.description` **có giá trị thật** + `PATCH /admin/wallpapers/{id}` để điền mô tả cho 397 item catalog cũ;
> (2) `GET /home` — Browse dạng **section curated**, tái dùng `Collection` (`show_on_home`/`home_position`), KHÔNG model mới, ≤10 section × ≤10 wallpaper, **4 query cố định**, p95 37 ms.
> Chi tiết: `sdd-roadmap.md` §BE-008. **Số spec là ID, không phải thứ tự thi công** — BE-006/BE-007 giữ số cũ, chạy sau.
> **Mục đích**: Snapshot tối thiểu để bắt đầu 1 session làm việc trên repo backend.
>
> **Đọc file nào khi nào**:
> - Bắt đầu session mới → file này + `docs/PRD.md` + `CLAUDE.md` (khi có).
> - Chuẩn bị họp spec mới → file này + [`sdd-roadmap.md`](sdd-roadmap.md).
> - **Trước khi đổi/thêm bất kỳ API nào** → [`../docs/screen-inventory.md`](../docs/screen-inventory.md) TRƯỚC TIÊN (màn hình cần gì quyết định API, không phải ngược lại), rồi mới tới `api-context.md`.
> - Cần biết chi tiết từng endpoint (header/body/response) → [`api-context.md`](api-context.md) + [`openapi.yaml`](openapi.yaml) — **contract version hiện tại: `v0.7.1`** (v0.5.0 entitlement thật ở `download-url` · v0.6.0 khai `Wallpaper.description` · v0.7.0 `GET /home` + description có giá trị thật · v0.7.1 khai đúng `AdminWallpaper` cho `/admin/wallpapers`).
> - Cần hiểu vì sao spec X ra đời → [`decisions/`](decisions/).
> - Cần biết spec nào ship khi nào → [`changelog.md`](changelog.md).

## Snapshot

- **Vai trò repo này**: Backend cho app hình nền động LiveCanvas — cung cấp API public (wallpaper/category/tag/collection), API admin upload nội dung + quản lý tag/collection, và xác thực IAP (verify-receipt tự viết, không dùng RevenueCat).
- **Stack**: Django + Django REST Framework, PostgreSQL, S3-compatible storage + CDN, Celery + Redis (transcode/scan bất đồng bộ).
- **Không có hệ thống user/account** — entitlement premium xác định qua `transaction_id` (App Store/Play), verify trực tiếp với Apple/Google, không qua login.
- **2 tầng auth hoàn toàn tách biệt**: `X-App-Key` (app, không phải user) cho endpoint public/IAP · `Authorization: Bearer <jwt>` cho endpoint `/admin/*`. Không bao giờ trộn 2 tầng này.
- **Communication**: Tiếng Việt giữa user + Claude · Tiếng Anh cho code/comment/commit.

## Current Focus

- **Trạng thái**: BE-001→**BE-004 đã merge vào `main`** (PR #4 + #5). **BE-005 IAP đã implement đầy đủ trên branch `BE-005-iap-verify-entitlement`** (SDD trọn chuỗi; contract **v0.5.0**; 35/36 task, 196 tests xanh, ruff/format sạch) — **Contract Sync v0.5.0 → mobile đã xong (2026-07-26, T002)**, chỉ còn review/merge. Spec tiếp theo: **BE-006 Security Hardening**.
- **Đã có sẵn**:
  - Catalog thật: **397 wallpaper Pexels** (dataset local ~22.4 GB tại `~/Documents/database/crawl_script/livewallpapers`; metadata commit ở `data/crawl/`; fixture sinh bởi `scripts/build_seed_fixture.py` → `manage.py seed_content`). 5 categories / 21 curated tags / 83 premium / 5 collections.
  - Contract **v0.4.0** (`.claude/openapi.yaml` + `api-context.md`): + `POST /admin/auth/login|refresh` (JWT access 30'/refresh 7d rotate), download-url presigned thật ≤5' cho free (premium 402 tới BE-005), 422 FILE_REJECTED đồng bộ khi >500MB, bỏ server Staging.
  - BE-004 stack: admin tier (`AdminTierAPIView`/`AdminJWTAuthentication`/`IsAdminStaff` trong `core`), storage 2 vùng (bucket private staging+masters / public thumbs+previews+covers; MinIO dev qua docker-compose, R2 prod), pipeline Celery+Redis (magic-byte sniff → H.264 normalize → thumbnail → preview 720p watermark; state machine processing→published|failed, idempotent theo `master_key`), admin CRUD wallpapers/tags/collections + app `apps/audit` (append-only, sanitize guard), `backfill_media` + `purge_stale_uploads`.
  - ✅ **Đã sync `livecanvas-mobile`** (2026-07-23): contract v0.4.0 copy nguyên văn (openapi.yaml → `.claude/` + `contracts/`, api-context.md, screen-inventory.md) + ghi chú vào changelog mobile. Mobile cần regenerate `packages/livecanvas_api` và chuyển mock → API thật (MO-002).
  - ✅ **Đã sync `livecanvas-mobile` v0.5.0** (2026-07-26, T002 của BE-005): 3 file contract copy nguyên văn + entry changelog mobile + sửa điểm đồng bộ **MO-006: BE-004 → BE-005** (kèm ràng buộc entitlement vào scope MO-006). Mobile **không cần regenerate client** cho v0.5.0 (chỉ đổi semantics; `transactionId` optional ở `download-url` và 2 endpoint IAP đã có sẵn trong client sinh trước đó).
  - ✅ **Contract v0.6.0 (mobile-driven, 2026-07-27)**: mobile bump + copy ngược sang repo này (3 file đã khớp verbatim). `Wallpaper.description` mới là **khai báo trước** — backend trả `null` cho tới khi ship BE-008; client ẩn mục "Mô tả" khi null.
- **Việc còn treo của BE-004** (chuyển tiếp, không chặn BE-005): (1) chạy nốt `backfill_media` full 397 (đã verify 3 item thật end-to-end; resumable); (2) tạo bucket R2 + CDN khi lên prod.
- **BE-005 đã ship trên branch** (contract v0.5.0): `POST /iap/verify-receipt`, `GET /iap/subscription-status` (app-tier), `POST /iap/webhook/apple|google` (signature-only), gate entitlement thật ở `download-url`. Entitlement account-less theo original transaction id; grace = còn quyền; adapter Apple/Google validate qua mock (live-store để staging).
- **BE-008 đã ship trên branch** (contract v0.7.0 → **v0.7.1**): `GET /home` (app tier, bounded ≤10×10, trần áp lúc đọc, section rỗng không chiếm slot); `Collection.show_on_home`/`home_position` + index; `Wallpaper.description` thật (rỗng/whitespace → `null`); `PATCH /admin/wallpapers/{id}` chỉ sửa mô tả. Kèm **v0.7.1**: khai đúng `AdminWallpaper` (= `Wallpaper` + `status` + `failure_reason`) cho cả 3 verb `/admin/wallpapers` — sửa lệch contract có từ BE-004, **không đổi hành vi server**. **Đã sync mobile** cả hai bump; mobile phải regenerate cho v0.7.0 (đổi path+schema), riêng v0.7.1 thì không cần (chỉ admin tier).
- **Spec tiếp theo**: `BE-006-security-hardening` — rate limit, WAF, Sentry, load test, OWASP (IDOR ở download-url), + ClamAV (hoãn từ BE-004). **Đã gánh thêm 2 nợ từ BE-008** (chi tiết ở `sdd-roadmap.md` §BE-006): (1) **N+1 `COUNT(*)`** còn ở `GET /wallpapers`, `/wallpapers/batch`, `/collections/{id}`, `/admin/wallpapers` — `/home` đã fix bằng prefetch-kèm-annotation, dùng làm khuôn; (2) ~~nợ contract `/admin/wallpapers`~~ → **đã fix ở BE-008 (contract v0.7.1)**, không còn là việc của BE-006. Sau đó là `BE-007-deploy-launch`.
- **Quyết định kỹ thuật đã chốt** (ảnh hưởng schema DB):
  - Pagination: cursor-based (keyset), không dùng offset `page`/`page_size`.
  - Tag: curated — model `Tag` many-to-many với `Wallpaper`, admin chỉ chọn `tag_ids` có sẵn khi upload, tạo tag mới qua endpoint riêng `/admin/tags`.
  - Collection (bộ sưu tập): curated — many-to-many **có thứ tự** với `Wallpaper` (bảng nối lưu `position`); `GET /collections` không phân trang, `GET /collections/{id}` nhúng `items` đúng thứ tự; entitlement bộ premium vẫn quyết ở `download-url` từng file ("Tải tất cả" = client lặp gọi download-url).
- **Đã chốt thêm (BE-004)**: storage = **Cloudflare R2** (egress free) + MinIO dev, mô hình 2 bucket public/private; admin JWT = simplejwt (login endpoint, access 30'/refresh 7d rotate); master H.264 giữ resolution; preview 720p watermark 10s; trần upload 500 MB; ClamAV hoãn BE-006 (deviation có phê duyệt).
- **Chưa quyết định**:
  - Tên sản phẩm thật + domain API production (+ tài khoản Cloudflare/R2 bucket thật).
  - ~~Có cần mục "Nổi bật/Trending" riêng (`is_featured`)~~ → **đã chốt 2026-07-27**: KHÔNG thêm `is_featured`; Browse dùng **section curated tái dùng `Collection`** (`show_on_home`/`home_position`) — thuộc BE-008.
  - **Chốt khi plan BE-008** (chi tiết ở `sdd-roadmap.md`): kiểu field `description` (`null=True` vs `default=""` + map `""`→`null`); số item tối đa mỗi section (đề xuất ≤10); section có hiện khi đang lọc tag không (đề xuất: chỉ khi chip "Tất cả"); có thêm `PATCH /admin/wallpapers/{id}` để sửa mô tả không.

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

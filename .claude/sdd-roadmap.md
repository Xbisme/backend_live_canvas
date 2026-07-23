# LiveCanvas Backend v1.0 — Spec Roadmap

> Repo: `livecanvas-backend`. Track song song bên repo `livecanvas-mobile` (spec `MO-NNN`) — không sống trong repo này, chỉ tham chiếu tại các điểm đồng bộ contract.
>
> **Vai trò file này**: pure planning cho track backend. Trạng thái hiện tại → [`project-context.md`](project-context.md). Ship history → [`changelog.md`](changelog.md).
>
> Last updated: 2026-07-23 (Chưa có spec nào merge · contract v0.3.0 — thêm resource Collection · thêm BE-001 Project Bootstrap 2-flavor, renumber BE cũ +1)
> Full requirements: `docs/PRD.md`
>
> **Quy ước flavor**: Toàn repo **chỉ có đúng 2 flavor**: `dev` và `prod` (production). KHÔNG có `staging` hay bất kỳ flavor nào khác. Mọi settings/env/CI/deploy đều bám theo đúng 2 flavor này.

---

## SDD Workflow For Each Spec

```
/speckit.specify → /speckit.clarify → /speckit.plan → /speckit.tasks → /speckit.implement
```

Branch: `BE-NNN-feature-name`, folder `specs/BE-NNN-feature-name/`

---

## Dependency Graph

```
Spec #000: API Contract Freeze                    ← SHARED — phối hợp với repo mobile
           (contracts/openapi.yaml +               (độc lập với BE-001; chỉ BE-003+ mới
            .claude/api-context.md v1.0)             cần contract đã chốt)
    │
    │   BE-001: Project Bootstrap & 2-Flavor Setup   ← có thể chạy song song với #000
    │   (Django project + constitution, config/settings
    │    base + ĐÚNG 2 flavor DEV & PROD, django-environ,
    │    requirements, CI skeleton — CHỈ dev + prod)
    │        │
    └────────┴──▼
BE-002: Backend Foundation
(apps/wallpapers|uploads|iap skeleton, PostgreSQL,
 S3+CDN config, middleware X-App-Key)
    │
    ▼
BE-003: Core Content API                          ⇄ Điểm đồng bộ: repo mobile cần API này
(Category, Tag, Wallpaper, Collection models,         thật (thay mock) trước khi merge MO-002
 public list/detail/filter/search)
    │
    ▼
BE-004: Admin Upload Pipeline
(Presigned upload 2 bước, Celery+Redis,
 transcode ffmpeg, thumbnail, malware scan,
 Admin CRUD)
    │
    ▼
BE-005: IAP Verify & Entitlement                  ⇄ Điểm đồng bộ: repo mobile cần endpoint
(verify-receipt, webhook Apple/Google,                này hoạt động thật trước khi merge MO-005
 subscription-status, entitlement gate
 trên download-url)
    │
    ▼
BE-006: Security Hardening & Production Readiness
(Rate limit, WAF, audit log, Sentry, load test)
    │
    ▼
BE-007: Deploy & Launch Support                   ⇄ Điểm đồng bộ: repo mobile chờ backend
(Deploy flavor PROD, backup, runbook)                 production trước khi submit store (MO-006)
```

---

## Spec Details

### Spec #000: API Contract Freeze

- **Status**: 🟡 In progress (v0.3.0 — thêm resource `Collection`, chờ xác nhận cuối)
- **Không tạo branch riêng** — review trực tiếp `contracts/openapi.yaml` + `.claude/api-context.md`, phối hợp với repo `livecanvas-mobile`.
- **Thứ tự bắt buộc**: `docs/screen-inventory.md` (màn hình cần gì) → mới tới contract. Không sửa contract trực tiếp mà không cập nhật screen-inventory trước.
- **Checklist**: xem bản đầy đủ trong `api-context.md` §Quy ước chung; xác nhận error code catalog đã cover hết case; xác nhận entitlement luôn quyết ở `download-url` (kể cả bộ sưu tập premium — "Tải tất cả" chỉ lặp gọi download-url); xác nhận cursor pagination đã áp dụng đúng cho mọi list endpoint lớn; xác nhận tag + collection là curated (không free-form); xác nhận `GET /collections` không phân trang còn `GET /collections/{id}` nhúng items đúng thứ tự.
- **v0.3.0 — Collection**: resource mới `Collection` (bộ sưu tập curated, many-to-many có thứ tự với `Wallpaper`) + `GET /collections`, `GET /collections/{id}`; `Wallpaper.collections: CollectionRef[]`; admin `POST/GET/PATCH/DELETE /admin/collections`; error `COLLECTION_SLUG_CONFLICT`, `WALLPAPER_NOT_FOUND`.

### BE-001: Project Bootstrap & 2-Flavor Setup

- **Status**: ⬜ Not started
- **Branch**: `BE-001-project-bootstrap`
- **Depends on**: — (không phụ thuộc contract; có thể chạy song song / trước #000)
- **Mục tiêu**: Tạo khung project Django chạy được với **đúng 2 flavor `dev` + `prod`**, chốt constitution — CHƯA có model/endpoint nghiệp vụ nào.
- **Scope**:
  - **Constitution**: chạy `/speckit.constitution` viết `.specify/memory/constitution.md` cho backend (hiện đang là template rỗng) — nguyên tắc cốt lõi bám project: 2-tầng auth tách biệt tuyệt đối (`X-App-Key` vs admin Bearer JWT), no-user/account system (entitlement qua `transaction_id`), error-code catalog là hợp đồng, contract-first (`openapi.yaml` + `api-context.md` là nguồn sự thật, sync tay 2 repo), cursor pagination, curated tag/collection, test discipline (`pytest-django`), Dependency Hygiene (pin version + đọc docs chính thức, tham khảo mẫu constitution `flutter_formly`), và **kỷ luật 2-flavor** (chỉ dev + prod).
  - **Project skeleton**: `django-admin startproject`, `manage.py`, `config/wsgi.py` + `asgi.py`.
  - **Settings tách flavor**: `config/settings/base.py` + **đúng 2 file flavor** `dev.py`, `prod.py`. TUYỆT ĐỐI không tạo `staging.py` hay flavor nào khác. Chọn flavor qua `DJANGO_SETTINGS_MODULE` (`config.settings.dev` | `config.settings.prod`), mặc định `manage.py` = dev.
  - **Env**: `django-environ` đọc `.env.dev` / `.env.prod`; commit `.env.dev.example` + `.env.prod.example`, `.gitignore` chặn `.env.dev`/`.env.prod` thật.
  - **Khác biệt 2 flavor**: `dev` (`DEBUG=True`, DB Postgres local / SQLite, console email, CORS mở, log verbose, S3 tuỳ chọn MinIO local) vs `prod` (`DEBUG=False`, Postgres managed, security headers + `ALLOWED_HOSTS` chặt, S3+CDN thật, log JSON).
  - **Requirements**: `requirements/base.txt`, `dev.txt` (`-r base.txt`), `prod.txt` (`-r base.txt`) — khớp đúng 2 flavor.
  - **CI skeleton**: `ruff` + `pytest-django`; healthcheck `GET /health` để smoke-test cả 2 flavor boot được.
  - **Docs**: `README` hướng dẫn chạy từng flavor; `CLAUDE.md` mirror các rule runtime từ constitution.
- **Ra khỏi scope**: mọi model/endpoint nghiệp vụ (để BE-002+); Celery/Redis (BE-004).

### BE-002: Backend Foundation

- **Status**: ⬜ Not started
- **Branch**: `BE-002-backend-foundation`
- **Depends on**: BE-001 (+ #000 gần chốt)
- **Scope**: DRF skeleton + app `apps/wallpapers`, `apps/uploads`, `apps/iap` (rỗng, chưa model nghiệp vụ); wiring PostgreSQL vào 2 flavor; S3 (`django-storages`) + CDN config theo flavor; middleware xác thực `X-App-Key` cho tầng public/IAP; base cho error-code catalog (exception handler → format `{ "error": { "code", "message" } }`).

### BE-003: Core Content API

- **Status**: ⬜ Not started
- **Branch**: `BE-003-core-content-api`
- **Depends on**: BE-002
- **Scope**: Model `Category`/`Tag`/`Wallpaper`/`Collection` (many-to-many Wallpaper↔Tag; many-to-many **có thứ tự** Collection↔Wallpaper qua bảng nối `position`) đúng `openapi.yaml`; `GET /categories`, `GET /tags`, `GET /wallpapers` (cursor pagination), `GET /wallpapers/{id}` (populate `collections`), `POST /wallpapers/batch`; `GET /collections` (không phân trang), `GET /collections/{id}` (nhúng `items` đúng thứ tự); `POST/GET/DELETE /admin/tags` (curated tag management); seed script Pixabay/Pexels/Mixkit (lưu `source_url`, `license_type`); `download-url` trả mock/`501` tạm — hoàn thiện thật ở BE-004.
- **⚠️ Điểm đồng bộ**: báo repo mobile khi merge — họ cần chuyển từ mock server sang API thật (MO-002).

### BE-004: Admin Upload Pipeline

- **Status**: ⬜ Not started
- **Branch**: `BE-004-admin-upload-pipeline`
- **Depends on**: BE-003
- **Scope**: `POST /admin/uploads/presign`, `POST /admin/wallpapers` (validate `tag_ids` tồn tại → `TAG_NOT_FOUND` nếu sai), `GET/DELETE /admin/wallpapers` (cursor pagination); `POST/GET/PATCH/DELETE /admin/collections` (curated collection management — validate `wallpaper_ids` tồn tại → `WALLPAPER_NOT_FOUND`, `slug` trùng → `COLLECTION_SLUG_CONFLICT`, cover ảnh qua presign → `cover_upload_key`, `wallpaper_ids` giữ thứ tự); Celery worker (validate MIME thật, scan malware ClamAV, transcode ffmpeg, thumbnail + preview watermark); `AdminBearer` JWT riêng; audit log.

### BE-005: IAP Verify & Entitlement

- **Status**: ⬜ Not started
- **Branch**: `BE-005-iap-verify-entitlement`
- **Depends on**: BE-003
- **Scope**: `POST /iap/verify-receipt` (App Store Server API / Google Play Developer API); `POST /iap/webhook/apple` + `/google` (verify chữ ký JWS/Pub-Sub); `GET /iap/subscription-status`; hoàn thiện entitlement check thật ở `download-url`; presigned URL premium hết hạn ≤5 phút.
- **⚠️ Điểm đồng bộ**: báo repo mobile khi merge — họ cần endpoint này hoạt động thật để test MO-005 end-to-end.

### BE-006: Security Hardening & Production Readiness

- **Status**: ⬜ Not started
- **Branch**: `BE-006-security-hardening`
- **Depends on**: BE-004, BE-005
- **Scope**: Rate limiting, WAF/CDN rules, Sentry, load test (Locust) cho presigned URL + verify-receipt, OWASP Top 10 review (đặc biệt IDOR ở `download-url`).

### BE-007: Deploy & Launch Support

- **Status**: ⬜ Not started
- **Branch**: `BE-007-deploy-launch`
- **Depends on**: BE-006
- **Scope**: Deploy flavor `prod` lên hạ tầng production (build từ `config.settings.prod` + `.env.prod`), backup định kỳ, runbook vận hành. Không có bước staging riêng — verify trên flavor `dev` rồi promote thẳng lên `prod`.
- **⚠️ Điểm đồng bộ**: báo repo mobile khi production sẵn sàng — họ cần trước khi submit store (MO-006).

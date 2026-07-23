# Implementation Plan: Admin Upload Pipeline

**Branch**: `BE-004-admin-upload-pipeline` | **Date**: 2026-07-23 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/BE-004-admin-upload-pipeline/spec.md`

## Summary

Dựng **tầng admin hoàn chỉnh** cho LiveCanvas backend: (1) auth tier thứ hai — `POST /admin/auth/login`
+ `POST /admin/auth/refresh` cấp JWT access 30' / refresh 7 ngày (rotate) cho Django staff user, cách ly
tuyệt đối với `X-App-Key` (Constitution II); (2) **object storage 2 vùng** — bucket private (master +
staging upload, chỉ presigned ≤5') và bucket public-read sau CDN (thumbnail + preview watermark), R2 ở
prod / MinIO ở dev; (3) **pipeline media bất đồng bộ** Celery+Redis: sniff magic-bytes → normalize H.264
→ thumbnail → preview 720p watermark → flip `processing→published` (fail → `failed` + reason, idempotent
retry); (4) đầy đủ admin CRUD theo contract: presign, wallpapers (đăng ký/list/soft-delete), tags,
collections (ordered, atomic reorder) + **audit log** mọi mutation; (5) **bulk backfill 397 wallpaper**
đã seed: upload file gốc từ dataset local qua đúng pipeline trên, thay toàn bộ URL Pexels tạm bằng URL
tự host; (6) `download-url` thật — presigned GET cho wallpaper free, premium giữ 402 tới BE-005
(Constitution III). Contract bump **v0.4.0** (surface mới: admin auth; hành vi mới: download-url) phải
đi trước code theo Constitution I, kèm trả nợ sync v0.3.2 sang repo mobile.

## Technical Context

**Language/Version**: Python 3.11+ (Django 5.2 LTS; dev local đang chạy CPython 3.14 — xem risk R1
trong [research.md](research.md))

**Primary Dependencies** (mới, version tra PyPI 2026-07-23 — Constitution XI):
`djangorestframework-simplejwt` 5.5.1 (admin JWT + rotate/blacklist), `celery[redis]` 5.6.3 (worker;
kéo redis client 6.4.0 — kombu caps `redis <6.5`, xem research D2), `python-magic` 0.4.27
(magic-byte sniffing; cần libmagic hệ thống). Tái dùng
sẵn có: `django-storages[s3]` 1.14.6 (đã pin từ BE-002). **Binary hệ thống**: `ffmpeg` (transcode/
thumbnail/watermark), `libmagic`. KHÔNG thêm result-backend (django-celery-results) — trạng thái task
phản ánh vào `Wallpaper.status`.

**Storage**: PostgreSQL (models mới: `UploadSlot`, `AuditLogEntry`, refresh-token blacklist của
simplejwt; `Wallpaper` thêm storage keys + `failure_reason`). Object storage 2 bucket:
`private` (staging + masters, presigned-only) và `public` (thumbs + previews, CDN static URL).
Dev: MinIO container (docker-compose, 2 bucket tự tạo); Prod: Cloudflare R2 + CDN. Broker: Redis
container (dev) / managed (prod).

**Testing**: `pytest-django` + `factory-boy`; Celery chạy `task_always_eager` trong test; storage +
ffmpeg + magic mock tại boundary (Constitution X — không chạm mạng/binary thật trong test); test file
giả dạng (magic-bytes) cho FR-011/SC-006; test cách ly 2 tầng auth cho **mọi** admin endpoint (SC-004).

**Target Platform**: Linux server (API + Celery worker cùng codebase, 2 process); backfill chạy trên
máy operator có dataset local (~22.4 GB).

**Project Type**: web-service (DRF) — mở rộng `apps/uploads` (presign, pipeline, backfill), `apps/wallpapers`
(admin CRUD wallpaper/tag/collection), app mới `apps/audit` (audit log), `core` (AdminTierAPIView).

**Performance Goals**: đăng ký wallpaper phản hồi < 2s bất kể dung lượng file (SC-001 — API không đụng
bytes); backfill 397 file ~22.4 GB chạy hết trong 1 phiên, resumable; presign/list admin theo cursor
chuẩn BE-002.

**Constraints**: trần file 500 MB; presigned GET ≤ 5 phút; access JWT 30' / refresh 7 ngày rotate;
key master non-guessable (uuid4); premium bytes đóng 100% (không có chế độ tạm); dev/test chạy offline;
không log secret/token/presigned URL (Constitution XI).

**Scale/Scope**: catalog hiện 397 wallpaper (+ tăng trưởng qua admin upload); 1–vài admin nội bộ;
~6 endpoint admin mới + 2 auth + sửa 1 public (download-url); 3 model mới + ~5 field mới trên Wallpaper.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| # | Nguyên tắc | Đánh giá | Ghi chú |
|---|---|---|---|
| I | Contract-First & Dual-Repo Sync | ✅ PASS (có điều kiện thứ tự) | Surface mới (admin auth) + hành vi mới (download-url thật) → bump **v0.4.0**: sửa `docs/screen-inventory.md` (mục Admin tooling) → `contracts/openapi.yaml` + `.claude/api-context.md` → sync mobile, **trước khi code endpoint**. Nợ sync v0.3.2 trả cùng lúc. Task đầu tiên của tasks.md phải là contract update. |
| II | Two-Tier Auth Isolation | ✅ PASS | `AdminTierAPIView` (Bearer JWT) song song `AppTierAPIView` (X-App-Key), không fallback, không mixin chung authentication. Test cách ly 2 chiều cho mọi endpoint (SC-004). Webhook không liên quan spec này. |
| III | Entitlement at Download Edge | ✅ PASS | Master ở bucket private, key uuid non-guessable, presigned ≤5'; premium → 402 vô điều kiện (gate mở ở BE-005). Thumb/preview public là metadata-tier (đã watermark/thu nhỏ), không phải bytes premium. |
| IV | Structured Errors & Catalog | ✅ PASS | Dùng lại `core.errors` + handler BE-002. Code dùng: `UNAUTHORIZED_ADMIN`, `FORBIDDEN_ADMIN_ROLE`, `VALIDATION_ERROR`, `TAG_NOT_FOUND`, `TAG_IN_USE`, `WALLPAPER_NOT_FOUND`, `COLLECTION_SLUG_CONFLICT`, `FILE_REJECTED`, `ENTITLEMENT_REQUIRED`, `NOT_FOUND` — tất cả đã có trong catalog v0.3.2, **không thêm code mới** (xác nhận ở research). |
| V | Feature-First App Architecture | ✅ PASS | `apps/uploads`: presign + pipeline + backfill; `apps/wallpapers`: admin CRUD content; `apps/audit` (MỚI): model + service `record()` — core giữ đúng "no models". Cross-app qua public service function. Logic nặng trong services/tasks, view mỏng. |
| VI | Cursor Pagination & Envelopes | ✅ PASS | `GET /admin/wallpapers` dùng lại `EnvelopeCursorPagination`; admin tags/collections trả nguyên mảng (curated bounded) đúng contract. |
| VII | Async Media Pipeline Safety | ⚠️ PASS với 1 deviation | Presign 2 bước, API không proxy bytes; Celery task idempotent, fail → `failed` inspectable; sniff magic-bytes thật. **Deviation: ClamAV hoãn sang BE-006** — xem Complexity Tracking. |
| VIII | Two-Flavor Config | ✅ PASS | Chỉ thêm env mới vào `.env.*.example` (2 bucket, Redis URL, JWT lifetime, CDN, dataset dir); MinIO+Redis vào docker-compose (dev); không flavor mới. |
| IX | Data Integrity & Curated | ✅ PASS | Migration additive (thêm field nullable + model mới, không destructive); `TAG_IN_USE` khi xóa tag đang dùng; reorder collection thay thế atomic trong transaction; soft-delete giữ nguyên semantics BE-003. |
| X | Testing Discipline | ✅ PASS | Coverage bắt buộc: cách ly 2 tầng, entitlement download-url, state machine pipeline, idempotent backfill, contract shape. Mock S3/ffmpeg/magic tại boundary; `task_always_eager`; không phụ thuộc wall-clock (freeze time cho expiry test). |
| XI | Code Quality & Dependency | ✅ PASS | 4 package mới đã tra PyPI (bảng ở Technical Context + research.md); pin `.in` → compile `uv pip compile` → commit cả 2; ruff zero-warning; không log secret. |

**Kết luận gate**: PASS — 1 deviation có chủ đích (ClamAV), justified bên dưới. Re-check sau Phase 1: PASS (không phát sinh vi phạm mới trong design).

## Project Structure

### Documentation (this feature)

```text
specs/BE-004-admin-upload-pipeline/
├── plan.md              # File này
├── research.md          # Phase 0 — quyết định kỹ thuật + version PyPI + risks
├── data-model.md        # Phase 1 — model/field mới, state machine, key scheme
├── quickstart.md        # Phase 1 — dựng dev stack, chạy pipeline end-to-end, backfill
├── contracts/
│   └── endpoints.md     # Phase 1 — ánh xạ endpoint contract v0.4.0 ↔ implementation
└── tasks.md             # Phase 2 — /speckit.tasks (chưa tạo)
```

### Source Code (repository root)

```text
config/
├── celery.py                  # Celery app THẬT (thay placeholder BE-001)
├── settings/base.py           # + SIMPLE_JWT, CELERY_*, 2-bucket storage config, size ceiling
├── settings/dev.py            # + MinIO 2 bucket, Redis local, eager-friendly defaults
└── settings/prod.py           # + R2 2 bucket (env bắt buộc), Redis managed

core/
├── api.py                     # + AdminTierAPIView (Bearer JWT, staff-only permission)
├── authentication.py          # + AdminJWTAuthentication (wrap simplejwt, map lỗi → catalog)
└── permissions.py             # + IsAdminStaff (403 FORBIDDEN_ADMIN_ROLE cho non-staff)

apps/wallpapers/
├── models.py                  # Wallpaper + master_key/thumbnail_key/preview_key/failure_reason
├── admin_serializers.py       # serializers cho admin CRUD (tách khỏi public serializers)
├── admin_views.py             # /admin/wallpapers, /admin/tags, /admin/collections
├── services.py                # + services tạo/sửa/xóa curated (tag in-use, reorder atomic)
└── urls_admin.py              # route /admin/* của content domain

apps/uploads/
├── models.py                  # UploadSlot (single-use, orphan-trackable)
├── storage.py                 # 2-zone client: presign PUT/GET, public URL builder, key scheme
├── services.py                # presign, register-upload, publish/fail transitions
├── tasks.py                   # process_wallpaper (sniff→normalize→thumb→preview→publish)
├── ffmpeg.py                  # subprocess wrappers (probe, transcode, frame, watermark)
├── views.py + urls.py         # POST /admin/uploads/presign (auth login/refresh nằm ở core — xem Structure Decision)
└── management/commands/
    ├── backfill_media.py      # bulk backfill 397 items (idempotent, resumable, summary)
    └── purge_stale_uploads.py # liệt kê/xóa staging orphan quá hạn (edge case)

apps/audit/                    # APP MỚI
├── models.py                  # AuditLogEntry (immutable)
├── services.py                # record(actor, action, obj, meta) — API duy nhất app khác gọi
└── migrations/

apps/*/tests/                  # test mới theo khối (auth, presign, pipeline, admin CRUD, backfill, download)
docker-compose.yml             # + redis, minio (+ tạo bucket init)
requirements/base.in           # + simplejwt, celery[redis], redis, python-magic
```

**Structure Decision**: giữ ranh giới domain của Constitution V — `apps/uploads` sở hữu file-ingress
+ pipeline + backfill; admin CRUD của content nằm cùng `apps/wallpapers` (cạnh model của nó, file
`admin_*` tách riêng khỏi public); audit là app mới vì `core` cấm model mà audit cần bảng riêng.
Admin auth routes (login/refresh) mount dưới `apps/uploads` bị gượng — đặt trong `core/urls.py`?
KHÔNG: core không models nhưng auth không cần model riêng (dùng simplejwt + User) → **đặt view auth
trong `core`** (không model, đúng vai trò cross-cutting), route `admin/auth/*` include từ core.

## Complexity Tracking

> Fill ONLY if Constitution Check has violations that must be justified

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| **Constitution VII — bỏ bước ClamAV trước publish (hoãn sang BE-006)** | Phase này principal upload duy nhất là staff nội bộ đã xác thực JWT; file đến từ dataset curated của chính operator hoặc nguồn admin tự chọn. Giảm 1 service hệ thống (clamd) + độ phức tạp docker/CI ở spec vốn đã lớn. Bước scan sẽ chèn vào đúng chain Celery hiện có (giữa sniff và transcode) ở BE-006 mà không đổi kiến trúc. Đã được project lead duyệt trong spec discussion 2026-07-23 (ghi ở spec.md §Assumptions). | "Làm luôn ClamAV cho đủ VII": thêm clamd container + tuning memory (~1 GB) + cập nhật virus DB vào dev stack và prod deploy ngay bây giờ, trong khi surface tấn công thực (upload công khai/third-party) chưa tồn tại — chi phí vận hành trả trước cho rủi ro chưa có, và BE-006 (hardening) là chỗ tự nhiên của nó cùng rate-limit/WAF. |
| **App mới `apps/audit` (vượt 3 app domain ban đầu)** | Audit cần bảng DB; `core` theo thiết kế BE-002/CLAUDE.md là "no models"; nhét vào `apps/uploads` thì wallpapers/tags/collections mutation phải import ngược domain uploads — sai hướng phụ thuộc. | "Để model trong core": phá invariant "core no models" đã ghi thành văn. "Để trong uploads": tạo phụ thuộc chéo ngược chiều giữa 2 domain ngang hàng (Constitution V cấm import nội bộ chéo). |

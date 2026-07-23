# Implementation Plan: Core Content API

**Branch**: `BE-003-core-content-api` | **Date**: 2026-07-23 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/BE-003-core-content-api/spec.md`

## Summary

Hiện thực lớp **public content API** đầu tiên phục vụ dữ liệu thật cho app LiveCanvas (thay mock
server — điểm đồng bộ MO-002). Dựng 4 model biên tập (`Category`, `Tag`, `Wallpaper`, `Collection`)
trong app `apps/wallpapers` đúng contract v0.3.2, cùng 8 endpoint đọc tầng-app (`X-App-Key`):
categories/tags/collections (không phân trang; `GET /tags` chèn **thẻ ảo "All"** id=0 slug=all ở đầu,
API sinh không lưu DB), collections detail (nhúng items đúng thứ tự),
wallpapers (cursor pagination + filter category/tags-AND/orientation/is_premium/search),
wallpaper detail (populate collections), batch, và download-url tạm (non-premium → mock 200,
premium → 402). Tái sử dụng nguyên vẹn nền BE-002: `AppTierAPIView`, `EnvelopeCursorPagination`,
exception handler + error catalog. Nội dung mẫu nạp qua **fixture cố định + management command**.
Không mở endpoint tầng admin nào (hoãn `/admin/tags` sang BE-004).

## Technical Context

**Language/Version**: Python 3.11+ (Django 5.2 LTS)

**Primary Dependencies**: Django 5.2, `djangorestframework` 3.17.1, `psycopg[binary]` 3.3.4 —
**không thêm dependency mới** (filtering & search hand-rolled trên ORM; không cần `django-filter`).

**Storage**: PostgreSQL (dev: docker-compose local; prod: managed). Media URL lưu dạng chuỗi
(URLField) trỏ nguồn công khai/CDN — file thật + pipeline thuộc BE-004.

**Testing**: `pytest-django` 4.12 + `factory-boy` 3.3.3; test đặt tại `apps/wallpapers/tests/`.

**Target Platform**: Linux server (API service).

**Project Type**: web-service (DRF backend, single project) — mở rộng app `apps/wallpapers`.

**Performance Goals**: `GET /wallpapers` cursor keyset ổn định trên tập lớn (index theo
`(-created_at, -id)`); danh sách curated bounded < 100 trả nguyên mảng. Không mục tiêu tải cao
đặc thù ở spec này (rate-limit/WAF ở BE-006).

**Constraints**: account-less (không model user); contract v0.3.2 đóng băng (chỉ implement, không
đổi shape); cursor pagination keyset (cấm offset); mọi lỗi qua exception handler tập trung với mã
catalog; nội dung chưa publish / xoá mềm không rò rỉ ra endpoint public.

**Scale/Scope**: categories/tags/collections < 100 mỗi loại (curated); wallpapers không giới hạn
(phân trang); soft-cap ≤ 100 wallpaper/collection.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| # | Principle | Áp dụng cho BE-003 | Trạng thái |
|---|---|---|---|
| I | Contract-First & Dual-Repo Sync | Chỉ implement theo contract v0.3.2 đã đóng băng; không đổi shape. Nếu phát sinh lệch → dừng, sửa contract trước. | ✅ PASS |
| II | Two-Tier Auth Isolation & Account-Less | Toàn bộ endpoint dùng `AppTierAPIView` (`X-App-Key`); **không** endpoint admin, **không** model user. `/admin/tags` hoãn BE-004. | ✅ PASS |
| III | Entitlement at Download Edge | download-url là gate duy nhất; premium → `402 ENTITLEMENT_REQUIRED` (thật ở BE-005). List/detail phơi `is_premium`, không gate. | ✅ PASS (tạm) |
| IV | Structured Errors & Catalog | Mọi lỗi qua `structured_exception_handler` + `core.errors.ErrorCode`; không body lỗi tự chế. | ✅ PASS |
| V | Feature-First Django App | Model + view + serializer + service trong `apps/wallpapers`; view mỏng, logic (filter/build) ở service/queryset; không import chéo app. | ✅ PASS |
| VI | Cursor Pagination & Envelopes | `GET /wallpapers` dùng `EnvelopeCursorPagination`; curated lists trả nguyên mảng; cursor lỗi → `400 VALIDATION_ERROR`. | ✅ PASS |
| VII | Async Media Pipeline Safety | Ngoài scope (BE-004). BE-003 không xử lý bytes; media-derived field có thể null. | ✅ N/A |
| VIII | Two-Flavor Config | Không thêm flavor; không thêm setting bắt buộc mới (dùng `CDN_BASE_URL` đã có cho mock URL). | ✅ PASS |
| IX | Data Integrity & Curated Referential | Tag/Collection curated; Collection↔Wallpaper **ordered M2M** (`position`); xoá mềm wallpaper; migration non-destructive. | ✅ PASS |
| X | Testing Discipline | pytest-django; test bắt buộc: auth `X-App-Key`, cursor (gồm invalid), thứ tự collection, filter AND, không rò rỉ nội dung ẩn, envelope lỗi. | ✅ PASS |
| XI | Code Quality & Dependency Hygiene | Không thêm dep (không cần lookup PyPI). `ruff` sạch; type hints module mới; validate input qua serializer; không log secret. | ✅ PASS |

**Kết luận GATE**: PASS, không có vi phạm → Complexity Tracking để trống.

## Project Structure

### Documentation (this feature)

```text
specs/BE-003-core-content-api/
├── plan.md              # This file
├── spec.md              # Feature spec (input)
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/           # Phase 1 output — mapping tới openapi.yaml đã đóng băng
│   └── endpoints.md
├── checklists/
│   └── requirements.md  # spec quality checklist (đã pass)
└── tasks.md             # Phase 2 (/speckit-tasks — chưa tạo ở đây)
```

### Source Code (repository root)

```text
apps/wallpapers/
├── models.py            # Category, Tag, Wallpaper, Collection, CollectionItem (ordered join)
├── serializers.py       # Category/Tag/Collection(+Ref)/Wallpaper(list & detail variants)
├── services.py          # wallpaper filtering, batch fetch, download-url mock, count annotation
├── views.py             # 8 AppTierAPIView public read views
├── urls.py              # product API routes (categories/tags/collections/wallpapers…)
├── admin.py             # Django-admin registration (internal-staff curation, session auth)
├── apps.py              # (đã có) WallpapersConfig
├── migrations/          # 0001_initial (models) + index migration
├── fixtures/
│   └── seed_content.json   # fixture nội dung cố định (Category/Tag/Wallpaper/Collection)
├── management/commands/
│   └── seed_content.py  # nạp fixture (idempotent), FR-016
└── tests/
    ├── factories.py     # factory-boy factories
    ├── test_categories_tags.py
    ├── test_collections.py
    ├── test_wallpapers_list.py   # cursor + filter AND + search
    ├── test_wallpaper_detail.py  # US2: detail populate collections
    ├── test_wallpaper_batch.py   # US3: batch skip-missing
    ├── test_download_url.py
    └── test_seed_command.py

config/urls.py           # thêm include("apps.wallpapers.urls") dưới prefix product API
core/urls.py             # gỡ 4 route _probe/* tạm của BE-002 (đã hết vai trò)
```

**Structure Decision**: Single-project DRF backend theo Constitution V. Toàn bộ domain nội dung
gói trong `apps/wallpapers` (đúng phân chia app trong constitution). Product API mount tách khỏi
health routes của `core` (health không thuộc contract). Model join `CollectionItem` mang `position`
để hiện thực ordered M2M (Constitution IX). Endpoint tầng admin & pipeline media không thuộc plan này.

## Complexity Tracking

> Không có vi phạm Constitution Check — bảng để trống.

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| — | — | — |

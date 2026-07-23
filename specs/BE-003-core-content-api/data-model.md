# Phase 1 Data Model: Core Content API

> App: `apps/wallpapers`. Mọi field/kiểu bám contract v0.3.2 (`.claude/api-context.md` +
> `contracts/openapi.yaml`). Không đổi shape contract — đây là bản dịch contract → schema DB.

## Entity: Category

Danh mục curated cấp cao. Một Wallpaper thuộc **đúng một** Category.

| Field | Kiểu | Ràng buộc | Ghi chú |
|---|---|---|---|
| `id` | BigAutoField | PK | |
| `slug` | SlugField | unique, indexed | định danh ổn định dùng trong filter `?category=` |
| `name` | CharField | not null | tên hiển thị (đa ngữ để sau nếu cần) |
| `icon_url` | URLField | blank cho phép | ảnh icon (CDN/nguồn) |
| `created_at` | DateTimeField | auto_now_add | |

- **Derived (không lưu cột)**: `wallpaper_count` = số Wallpaper `published()` trỏ tới category, annotate lúc đọc.
- **Serialize** (`GET /categories`): `{ id, slug, name, icon_url, wallpaper_count }`.

## Entity: Tag

Nhãn **curated** (không free-form), quan hệ nhiều-nhiều với Wallpaper. Tạo/xoá tag qua endpoint admin
là **BE-004**; BE-003 chỉ đọc + seed/Django-admin.

| Field | Kiểu | Ràng buộc | Ghi chú |
|---|---|---|---|
| `id` | BigAutoField | PK | |
| `slug` | SlugField | unique, indexed | dùng trong filter `?tags=` |
| `name` | CharField | not null | |
| `created_at` | DateTimeField | auto_now_add | |

- **Derived**: `wallpaper_count` = số Wallpaper `published()` gắn tag (annotate).
- **Serialize** (`GET /tags`, và nhúng trong Wallpaper): `{ id, slug, name, wallpaper_count }`.
- **Thẻ ảo "All" (v0.3.2)**: `GET /tags` chèn phần tử `{ id: 0, slug: "all", name: "Tất cả",
  wallpaper_count: <tổng published> }` ở đầu mảng — **tổng hợp trong serializer/service, KHÔNG là
  record DB**. `id=0` và `slug="all"` là **reserved**.
  - **Enforce ở tầng model** (một chỗ, mọi caller): định nghĩa hằng dùng chung `RESERVED_TAG_SLUGS = {"all"}`
    và một `validate_tag_slug` gọi trong `Tag.clean()` (raise `ValidationError` nếu slug ∈ reserved).
    Nhờ đó admin (T005), seed (T030), factories (T006) và BE-004 sau này đều bị chặn — không phụ thuộc
    riêng lớp admin.
  - Trong `build_wallpaper_queryset`, slug `all` bị **strip** khỏi danh sách `tags` trước khi áp AND
    (nên `tags=all` → toàn bộ; `tags=all,neon` → chỉ `neon`).

## Entity: Wallpaper

Đơn vị nội dung trung tâm (video hình nền động).

| Field | Kiểu | Ràng buộc | Ghi chú |
|---|---|---|---|
| `id` | BigAutoField | PK | |
| `title` | CharField | not null | search `title__icontains` |
| `category` | FK → Category | `PROTECT`, not null | 1 wallpaper ↔ 1 category |
| `tags` | M2M → Tag | blank | filter AND theo slug |
| `orientation` | CharField(choices) | `portrait`\|`landscape`\|`square` | khớp enum contract |
| `thumbnail_url` | URLField | null=True | media-derived; null khi processing (BE-004), seed set sẵn |
| `preview_video_url` | URLField | null=True | như trên |
| `is_premium` | BooleanField | default False, indexed | phơi cho client; gate thật ở download-url |
| `resolution` | CharField | null=True | ví dụ `1080x1920` |
| `duration_seconds` | FloatField | null=True | contract: number, nullable |
| `file_size_bytes` | BigIntegerField | null=True | |
| `download_count` | PositiveIntegerField | default 0 | |
| `like_count` | PositiveIntegerField | default 0 | |
| `source_url` | URLField | not null | xuất xứ nguồn (Pixabay/Pexels/Mixkit) — FR-004 |
| `license_type` | CharField | not null | loại giấy phép — FR-004 |
| `status` | CharField(choices) | `processing`\|`published`\|`failed`, default `published` | R3; publish gate |
| `deleted_at` | DateTimeField | null=True, indexed | soft-delete (R3) |
| `created_at` | DateTimeField | auto_now_add, indexed | cursor ordering |

- **Ordered M2M ngược**: `collections` (qua `CollectionItem`, xem dưới) — populate đầy đủ ở detail,
  rỗng ở list (R4).
- **Manager/queryset**: `Wallpaper.objects.published()` = `filter(status="published", deleted_at__isnull=True)`.
  Mọi endpoint public/batch/collection-items **bắt buộc** đi qua đây (FR-013, SC-005).
- **Index**: `(created_at, id)` (hoặc `-created_at, -id`) cho cursor keyset ổn định (R1); `is_premium`;
  `deleted_at`.
- **Serialize (list)** `WallpaperListSerializer` — dùng ở `GET /wallpapers` (items) & `POST /wallpapers/batch`:
  `{ id, title, category (CategoryRef), tags: Tag[], orientation, thumbnail_url, preview_video_url,
  is_premium, resolution, duration_seconds, file_size_bytes, download_count, like_count, source_url,
  license_type, collections: [] , created_at }`.
- **Serialize (detail)** `WallpaperDetailSerializer` — dùng ở `GET /wallpapers/{id}` & nhúng trong
  `GET /collections/{id}.items`: giống list nhưng `collections: CollectionRef[]` populate đầy đủ.

## Entity: Collection

Bộ sưu tập curated, quan hệ nhiều-nhiều **có thứ tự** với Wallpaper.

| Field | Kiểu | Ràng buộc | Ghi chú |
|---|---|---|---|
| `id` | BigAutoField | PK | |
| `slug` | SlugField | unique, indexed | |
| `title` | CharField | not null | |
| `author` | CharField | blank | người/nhóm biên tập |
| `description` | TextField | blank | |
| `cover_url` | URLField | blank | ảnh bìa (CDN/nguồn) |
| `accent_color` | CharField | null=True | hex, ví dụ `#FF6F9C` (contract nullable) |
| `is_premium` | BooleanField | default False | phơi cho client; không gate ở đây |
| `created_at` | DateTimeField | auto_now_add | |
| `wallpapers` | M2M → Wallpaper `through=CollectionItem` | ordered | thứ tự qua `position` |

- **Derived**: `wallpaper_count` = số Wallpaper `published()` thành viên (annotate).
- **Serialize (meta)** — `GET /collections`, `POST /admin/...` (BE-004), nhúng `CollectionRef`:
  `{ id, slug, title, author, description, cover_url, accent_color, is_premium, wallpaper_count, created_at }`
  (không `items`).
- **Serialize (detail)** — `GET /collections/{id}`: meta **kèm** `items: Wallpaper[]` (detail serializer)
  đúng thứ tự `position`, chỉ gồm thành viên `published()`.
- **CollectionRef (mini)** — nhúng trong `Wallpaper.collections`:
  `{ id, slug, title, cover_url, is_premium }` (theo ví dụ contract).

## Entity: CollectionItem (bảng nối ordered)

Hiện thực ordered M2M (Constitution IX).

| Field | Kiểu | Ràng buộc | Ghi chú |
|---|---|---|---|
| `id` | BigAutoField | PK | |
| `collection` | FK → Collection | `CASCADE` | xoá collection thì gỡ hàng nối (không xoá wallpaper) |
| `wallpaper` | FK → Wallpaper | `CASCADE` | |
| `position` | PositiveIntegerField | not null | thứ tự hiển thị trong bộ |

- **Ràng buộc**: `unique_together (collection, wallpaper)` — một wallpaper xuất hiện tối đa 1 lần/bộ;
  `unique_together (collection, position)` — không trùng vị trí (hoặc enforce ở tầng service khi ghi).
- **Ordering mặc định**: `("collection", "position")`.
- **Đọc**: `GET /collections/{id}.items` = các `CollectionItem` order theo `position`, join wallpaper
  đã lọc `published()`, serialize bằng `WallpaperDetailSerializer`.
- **Ghi (thứ tự)**: reorder = thay thế atomically toàn bộ tập theo danh sách truyền lên (BE-004 admin);
  ở BE-003 chỉ tạo qua seed command.

## Quan hệ tổng quan

```
Category 1 ──< Wallpaper >── M2M ── Tag
                  │
                  └──< CollectionItem >── Collection
                        (position: ordered)
```

## Ràng buộc & bất biến (invariants) cần test

1. Endpoint public/batch/collection-items **không bao giờ** trả wallpaper `status!=published` hoặc
   `deleted_at != null` (FR-013, SC-005).
2. `GET /collections/{id}.items` theo đúng thứ tự `position` tăng dần (SC-006).
3. `wallpaper_count` = số thành viên `published()` (FR-005) — không đếm ẩn/xoá.
4. Cursor keyset ổn định: không trùng/nhảy item khi chèn wallpaper mới giữa các trang (R1, SC-002).
5. Filter `tags=a,b` là AND (chỉ wallpaper có **cả** a và b) (FR-009).
6. download-url: non-premium → 200 shape đúng; premium → 402; không tồn tại/ẩn → 404 (FR-012).

## Migrations

- `0001_initial`: 4 model + `CollectionItem` + M2M through + index `(created_at, id)`, `is_premium`,
  `deleted_at`. Non-destructive (bảng mới hoàn toàn) — Constitution IX.
- Chạy `python manage.py makemigrations --check --dry-run` sạch trước commit (pre-commit gate).

# API Context — LiveCanvas

> **Vai trò**: Companion đọc-được-cho-người/LLM của [`contracts/openapi.yaml`](openapi.yaml). File này được suy ra từ [`docs/screen-inventory.md`](../docs/screen-inventory.md) — mọi thay đổi màn hình phải sửa file đó trước, rồi mới sửa 2 file này.
>
> File này tồn tại độc lập ở CẢ 2 REPO (`livecanvas-backend`, `livecanvas-mobile`). Khi API đổi, sửa cả `openapi.yaml` lẫn `api-context.md` ở repo đang implement, rồi copy nguyên văn sang repo còn lại (xem "Contract Sync" trong `dev-workflow.md`).
>
> Last updated: 2026-07-23 · Contract version: **`v0.3.1`**
>
> **Đổi so với v0.3.0**: thêm 2 error code nền tảng `SERVER_ERROR` (500, lỗi máy chủ không lường trước — không lộ chi tiết nội bộ) và `METHOD_NOT_ALLOWED` (405) cho centralized exception handler (BE-002). Không đổi endpoint/schema nào khác.
>
> **Đổi so với v0.2.0**: thêm resource `Collection` (bộ sưu tập curated, quan hệ many-to-many có thứ tự với `Wallpaper`) + endpoint public `GET /collections`, `GET /collections/{id}` và admin `POST/GET/PATCH/DELETE /admin/collections`; `Wallpaper` thêm field `collections: CollectionRef[]`; thêm error code `COLLECTION_SLUG_CONFLICT`, `WALLPAPER_NOT_FOUND`.
>
> **Đổi so với v0.1.0**: pagination chuyển từ offset (`page`/`page_size`) sang **cursor-based**; thêm resource `Tag` + endpoint `/tags`, `/admin/tags`; thêm `POST /wallpapers/batch` cho màn Favorites; `Wallpaper.tags` đổi từ mảng string sang mảng object `Tag`.

---

## Quy ước chung

### Auth Headers

| Header | Dùng cho |
|---|---|
| `X-App-Key` | Toàn bộ endpoint Public + IAP (trừ webhook) |
| `Authorization: Bearer <jwt>` | Toàn bộ endpoint `/admin/*` |
| *(không header đặc biệt)* | `/iap/webhook/apple`, `/iap/webhook/google` — xác thực bằng chữ ký trong body |

### Cursor Pagination

Áp dụng cho `GET /wallpapers` và `GET /admin/wallpapers`. **Không dùng `page`/`page_size`.**

- Request: `?cursor=<string, optional>&limit=<int, default 20, max 100>` (kèm filter khác nếu có)
- Response:
```json
{
  "items": [ /* Wallpaper[] */ ],
  "next_cursor": "eyJjcmVhdGVkX2F0IjoiMjAyNi0wNy0yMFQxMDowMDowMFoiLCJpZCI6ODd9",
  "has_more": true
}
```
- Lấy trang tiếp theo: gọi lại với `cursor=next_cursor` vừa nhận. `next_cursor: null` + `has_more: false` = hết dữ liệu.
- **Client bắt buộc**: dùng `ListView.builder`/`GridView.builder` (lazy build), chỉ gọi trang tiếp khi scroll gần cuối, không giữ toàn bộ item đã tải trong 1 list phẳng không giới hạn — kết hợp dispose `VideoPlayerController` của item ngoài viewport để tránh tràn RAM (pagination server chỉ giải quyết 1 nửa vấn đề).

### `GET /categories`, `GET /tags`, `GET /collections` — KHÔNG phân trang

Cả 3 đều là danh sách curated bởi admin, số lượng nhỏ (dự kiến <100), trả về **toàn bộ mảng** trong 1 lần gọi, không cursor. `GET /collections/{id}` cũng không phân trang: nhúng thẳng `items: Wallpaper[]` đúng thứ tự curate (tập bounded, soft-cap ≤100 wallpaper/bộ).

### Error Code Catalog

| Code | HTTP Status | Ý nghĩa |
|---|---|---|
| `INVALID_APP_KEY` | 401 | Thiếu/sai `X-App-Key` |
| `UNAUTHORIZED_ADMIN` | 401 | Thiếu/sai/hết hạn admin JWT |
| `FORBIDDEN_ADMIN_ROLE` | 403 | Admin đúng nhưng không đủ quyền |
| `VALIDATION_ERROR` | 400 | Body/query sai định dạng (bao gồm `cursor` không hợp lệ, `limit` > 100, `ids` rỗng/quá 100 ở batch) |
| `NOT_FOUND` | 404 | Resource không tồn tại |
| `METHOD_NOT_ALLOWED` | 405 | HTTP method không được hỗ trợ trên resource này |
| `ENTITLEMENT_REQUIRED` | 402 | Wallpaper premium, chưa có `transaction_id` active |
| `RECEIPT_INVALID` | 400 | Receipt không verify được với Apple/Google |
| `RECEIPT_CONFLICT` | 409 | Receipt đã gắn transaction/device khác |
| `STORE_API_UNAVAILABLE` | 503 | App Store/Play API không phản hồi |
| `FILE_REJECTED` | 422 | File sai định dạng thật hoặc dính malware |
| `WEBHOOK_SIGNATURE_INVALID` | 400 | Chữ ký JWS/Pub-Sub không hợp lệ |
| `TAG_NOT_FOUND` | 400 | `tag_ids` chứa ID không tồn tại khi tạo wallpaper |
| `TAG_SLUG_CONFLICT` | 409 | Tạo tag với `slug` đã tồn tại |
| `TAG_IN_USE` | 409 | Xóa tag nhưng vẫn còn wallpaper đang dùng |
| `WALLPAPER_NOT_FOUND` | 400 | `wallpaper_ids` chứa ID không tồn tại khi tạo/sửa collection |
| `COLLECTION_SLUG_CONFLICT` | 409 | Tạo collection với `slug` đã tồn tại |
| `SERVER_ERROR` | 500 | Lỗi máy chủ không lường trước (generic; không lộ chi tiết nội bộ) |

Format chung:
```json
{ "error": { "code": "ENTITLEMENT_REQUIRED", "message": "Wallpaper này yêu cầu gói premium đang hoạt động" } }
```

---

## Public Endpoints

### `GET /categories`
- Header: `X-App-Key`
- **200**: `[{ "id": 1, "slug": "nature", "name": "Thiên nhiên", "icon_url": "https://cdn.../nature.png", "wallpaper_count": 42 }]`
- **401**: `INVALID_APP_KEY`

### `GET /tags`
- Header: `X-App-Key`
- **200**: `[{ "id": 12, "slug": "neon", "name": "Neon", "wallpaper_count": 87 }]`
- **401**: `INVALID_APP_KEY`

### `GET /collections`
- Header: `X-App-Key`
- Danh sách bộ sưu tập curated (tab "Bộ sưu tập") — **không phân trang**, chỉ meta + `wallpaper_count`, KHÔNG nhúng items.
- **200**:
```json
[
  {
    "id": 1,
    "slug": "neon-nights",
    "title": "Neon về đêm",
    "author": "tokyo",
    "description": "12 hình nền lấy cảm hứng từ những thành phố không bao giờ ngủ…",
    "cover_url": "https://cdn.example.com/collections/neon-nights.jpg",
    "accent_color": "#FF6F9C",
    "is_premium": false,
    "wallpaper_count": 6,
    "created_at": "2026-07-01T10:00:00Z"
  }
]
```
- **401**: `INVALID_APP_KEY`

### `GET /collections/{id}`
- Header: `X-App-Key` · Path: `id`
- Chi tiết 1 bộ sưu tập + **danh sách wallpaper thuộc bộ, đúng thứ tự curate** — không phân trang.
- **200**: object `Collection` như trên **kèm** `items` là mảng `Wallpaper` đầy đủ:
```json
{
  "id": 1, "slug": "neon-nights", "title": "Neon về đêm", "author": "tokyo",
  "description": "…", "cover_url": "…", "accent_color": "#FF6F9C",
  "is_premium": false, "wallpaper_count": 6, "created_at": "2026-07-01T10:00:00Z",
  "items": [ { "id": 5, "title": "Shibuya 2099", "...": "..." } ]
}
```
- **Lưu ý entitlement**: bộ premium (`is_premium: true`) vẫn trả về đầy đủ meta + items; client hiển thị nút "Mở khoá bộ sưu tập" dựa trên field này. **Gate thật vẫn nằm ở `GET /wallpapers/{id}/download-url` từng file** — "Tải tất cả" chỉ là client lặp gọi download-url cho từng item.
- **404**: `NOT_FOUND` · **401**: `INVALID_APP_KEY`

### `GET /wallpapers`
- Header: `X-App-Key`
- Query: `cursor` (string, optional), `limit` (int, default 20, max 100), `category` (slug), `tags` (slug, phân tách phẩy — **AND**, phải khớp hết), `orientation`, `search`, `is_premium`
- **200**:
```json
{
  "items": [
    {
      "id": 101,
      "title": "Neon City Loop",
      "category": { "id": 3, "slug": "urban", "name": "Đô thị", "icon_url": "...", "wallpaper_count": 20 },
      "tags": [{ "id": 12, "slug": "neon", "name": "Neon", "wallpaper_count": 87 }],
      "orientation": "portrait",
      "thumbnail_url": "https://cdn.example.com/thumbs/101.jpg",
      "preview_video_url": "https://cdn.example.com/preview/101_wm.mp4",
      "is_premium": true,
      "resolution": "1080x1920",
      "duration_seconds": 8.0,
      "file_size_bytes": 5242880,
      "download_count": 934,
      "like_count": 210,
      "source_url": "https://pixabay.com/videos/...",
      "license_type": "Pixabay License",
      "collections": [{ "id": 1, "slug": "neon-nights", "title": "Neon về đêm", "cover_url": "https://cdn.example.com/collections/neon-nights.jpg", "is_premium": false }],
      "created_at": "2026-07-01T10:00:00Z"
    }
  ],
  "next_cursor": "eyJjcmVhdGVkX2F0IjoiMjAyNi0wNy0wMVQxMDowMDowMFoiLCJpZCI6MTAxfQ==",
  "has_more": true
}
```
- **400**: `VALIDATION_ERROR` (cursor sai/hết hạn, `limit`>100)
- **401**: `INVALID_APP_KEY`

### `POST /wallpapers/batch`
- Header: `X-App-Key`, `Content-Type: application/json`
- Dùng cho màn Favorites — lấy lại data mới nhất theo danh sách ID local
- **Body**: `{ "ids": [101, 205, 310] }` (tối đa 100 id)
- **200**: mảng `Wallpaper` — id không tìm thấy bị **bỏ qua âm thầm** (không lỗi), client tự đối chiếu để biết item nào đã bị xóa
```json
[ { "id": 101, "title": "Neon City Loop", "...": "..." } ]
```
- **400**: `VALIDATION_ERROR` (`ids` rỗng hoặc > 100)
- **401**: `INVALID_APP_KEY`

### `GET /wallpapers/{id}`
- Header: `X-App-Key` · Path: `id`
- **200**: 1 object `Wallpaper` (schema như trên). Field `collections` (mảng `CollectionRef` mini) **được đảm bảo populate ở đây** để màn Detail nhảy vào bộ sưu tập ("Từ bộ sưu tập ·…"); ở list lớn (`GET /wallpapers`) field này có thể rỗng để tiết kiệm payload.
- **404**: `NOT_FOUND` · **401**: `INVALID_APP_KEY`

### `GET /wallpapers/{id}/download-url`
- Header: `X-App-Key` · Path: `id` · Query: `transaction_id` (bắt buộc nếu premium)
- **200**: `{ "download_url": "https://cdn.../101.mp4?X-Amz-Signature=...", "expires_at": "2026-07-22T10:35:00Z" }`
- **402**: `ENTITLEMENT_REQUIRED` · **404**: `NOT_FOUND` · **401**: `INVALID_APP_KEY`

---

## IAP Endpoints

### `POST /iap/verify-receipt`
- Header: `X-App-Key`
- **Body**: `{ "platform": "ios", "receipt_data": "...", "transaction_id": "1000000123456789", "product_id": "premium_monthly", "device_id": "device-uuid-abc123" }`
- **200**: `{ "transaction_id": "...", "product_id": "premium_monthly", "status": "active", "expires_at": "2026-08-22T00:00:00Z", "auto_renew": true }`
- **400**: `RECEIPT_INVALID` · **409**: `RECEIPT_CONFLICT` · **503**: `STORE_API_UNAVAILABLE` · **401**: `INVALID_APP_KEY`

### `GET /iap/subscription-status`
- Header: `X-App-Key` · Query: `transaction_id` (bắt buộc)
- **200**: cùng schema `SubscriptionStatus` · **404**: `NOT_FOUND` · **401**: `INVALID_APP_KEY`

### `POST /iap/webhook/apple`
- Không `X-App-Key` — verify chữ ký JWS trong `signedPayload`
- **Body**: `{ "signedPayload": "<JWS string>" }`
- **200**: `{}` · **400**: `WEBHOOK_SIGNATURE_INVALID`

### `POST /iap/webhook/google`
- Không `X-App-Key` — verify Pub/Sub OIDC token
- **Body**: `{ "message": { "data": "<base64 JSON>", "messageId": "..." } }`
- **200**: `{}` · **400**: `WEBHOOK_SIGNATURE_INVALID`

---

## Admin Endpoints

### `POST /admin/uploads/presign`
- Header: `Authorization: Bearer <admin_jwt>`
- **Body**: `{ "filename": "neon-city-loop.mp4", "content_type": "video/mp4" }`
- **200**: `{ "upload_url": "https://s3.../tmp-xyz.mp4?...", "upload_key": "uploads/tmp-xyz.mp4", "expires_at": "..." }`
- **400**: `VALIDATION_ERROR` · **401**: `UNAUTHORIZED_ADMIN` · **403**: `FORBIDDEN_ADMIN_ROLE`

### `POST /admin/wallpapers`
- Header: `Authorization: Bearer <admin_jwt>`
- **Body**:
```json
{
  "title": "Neon City Loop",
  "category_id": 3,
  "tag_ids": [12, 15],
  "orientation": "portrait",
  "is_premium": true,
  "source_url": "https://pixabay.com/videos/...",
  "license_type": "Pixabay License",
  "upload_key": "uploads/tmp-xyz.mp4"
}
```
  - `tag_ids` **curated** — phải trỏ tới tag đã tồn tại; muốn tag mới, gọi `POST /admin/tags` trước.
- **201**: object `Wallpaper`, các field media (`thumbnail_url`, `resolution`...) = `null` vì đang xử lý bất đồng bộ
- **400**: `VALIDATION_ERROR` (thiếu field, `category_id` không tồn tại), `TAG_NOT_FOUND` (tag_ids sai)
- **422**: `FILE_REJECTED` · **401**: `UNAUTHORIZED_ADMIN` · **403**: `FORBIDDEN_ADMIN_ROLE`

### `GET /admin/wallpapers`
- Header: `Authorization: Bearer <admin_jwt>`
- Query: `cursor`, `limit`, `status` (`processing`|`published`|`failed`)
- **200**: `WallpaperCursorPage` (bao gồm cả wallpaper chưa publish)
- **401**: `UNAUTHORIZED_ADMIN` · **403**: `FORBIDDEN_ADMIN_ROLE`

### `DELETE /admin/wallpapers/{id}`
- Header: `Authorization: Bearer <admin_jwt>` · Path: `id`
- **204**: xóa mềm · **404**: `NOT_FOUND` · **401**/**403** như trên

### `POST /admin/tags`
- Header: `Authorization: Bearer <admin_jwt>`
- **Body**: `{ "slug": "neon", "name": "Neon" }`
- **201**: `{ "id": 12, "slug": "neon", "name": "Neon", "wallpaper_count": 0 }`
- **409**: `TAG_SLUG_CONFLICT` · **401**/**403** như trên

### `GET /admin/tags`
- Header: `Authorization: Bearer <admin_jwt>`
- **200**: mảng `Tag` kèm `wallpaper_count` (để admin biết tag nào đang được dùng trước khi xóa)
- **401**/**403** như trên

### `DELETE /admin/tags/{id}`
- Header: `Authorization: Bearer <admin_jwt>` · Path: `id`
- **204**: đã xóa
- **404**: `NOT_FOUND`
- **409**: `TAG_IN_USE` — vẫn còn wallpaper đang gắn tag này, phải gỡ tag khỏi wallpaper trước
- **401**/**403** như trên

### `POST /admin/collections`
- Header: `Authorization: Bearer <admin_jwt>`
- Tạo bộ sưu tập curated. Cover ảnh upload trước qua `POST /admin/uploads/presign` rồi truyền `cover_upload_key`.
- **Body**:
```json
{
  "slug": "neon-nights",
  "title": "Neon về đêm",
  "author": "tokyo",
  "description": "12 hình nền lấy cảm hứng từ những thành phố không bao giờ ngủ…",
  "cover_upload_key": "uploads/tmp-cover-xyz.jpg",
  "accent_color": "#FF6F9C",
  "is_premium": false,
  "wallpaper_ids": [5, 6, 7, 8, 1, 3]
}
```
  - `wallpaper_ids` là **danh sách có thứ tự** (thứ tự này = thứ tự hiển thị trong bộ), phải trỏ tới wallpaper đã tồn tại.
- **201**: object `Collection` (chưa nhúng items)
- **400**: `VALIDATION_ERROR` (thiếu field), `WALLPAPER_NOT_FOUND` (`wallpaper_ids` sai)
- **409**: `COLLECTION_SLUG_CONFLICT` (slug trùng)
- **401**: `UNAUTHORIZED_ADMIN` · **403**: `FORBIDDEN_ADMIN_ROLE`

### `GET /admin/collections`
- Header: `Authorization: Bearer <admin_jwt>`
- **200**: mảng `Collection` (meta + `wallpaper_count`, không nhúng items). Không phân trang.
- **401**/**403** như trên

### `PATCH /admin/collections/{id}`
- Header: `Authorization: Bearer <admin_jwt>` · Path: `id`
- Sửa meta hoặc **thêm/bớt/sắp xếp lại** wallpaper trong bộ. Mọi field optional; truyền field nào cập nhật field đó. `wallpaper_ids` (nếu có) **thay thế toàn bộ** danh sách hiện tại theo đúng thứ tự truyền lên.
- **Body** (ví dụ chỉ đổi thứ tự + đổi tên):
```json
{ "title": "Neon về đêm (2026)", "wallpaper_ids": [8, 5, 7, 6] }
```
- **200**: object `Collection` sau khi cập nhật
- **400**: `VALIDATION_ERROR`, `WALLPAPER_NOT_FOUND`
- **404**: `NOT_FOUND` · **409**: `COLLECTION_SLUG_CONFLICT` (nếu đổi `slug` sang slug đã tồn tại)
- **401**/**403** như trên

### `DELETE /admin/collections/{id}`
- Header: `Authorization: Bearer <admin_jwt>` · Path: `id`
- Chỉ xóa bộ sưu tập (bản ghi nhóm) — **không xóa wallpaper thành viên**.
- **204**: đã xóa · **404**: `NOT_FOUND` · **401**/**403** như trên

# API Context — LiveCanvas

> **Vai trò**: Companion đọc-được-cho-người/LLM của [`contracts/openapi.yaml`](openapi.yaml). File này được suy ra từ [`docs/screen-inventory.md`](../docs/screen-inventory.md) — mọi thay đổi màn hình phải sửa file đó trước, rồi mới sửa 2 file này.
>
> File này tồn tại độc lập ở CẢ 2 REPO (`livecanvas-backend`, `livecanvas-mobile`). Khi API đổi, sửa cả `openapi.yaml` lẫn `api-context.md` ở repo đang implement, rồi copy nguyên văn sang repo còn lại (xem "Contract Sync" trong `dev-workflow.md`).
>
> Last updated: 2026-07-29 · Contract version: **`v0.7.0`**
>
> **Đổi so với v0.6.0 (BE-008)** — ⚠️ **bump này ĐỔI PATH + SCHEMA, khác v0.5.0/v0.6.0: mobile BẮT BUỘC regenerate client** (`scripts/generate_api.sh`).
> - **Màn Browse có section curated**: thêm `GET /home` (app tier) trả **cả màn trong 1 lần gọi**, KHÔNG phân trang, bounded cứng **≤10 section × ≤10 wallpaper/section**. Section **KHÔNG phải resource mới** — là `Collection` được admin bật `show_on_home` + `home_position`.
> - Trần áp **lúc đọc**: admin bật dư thì phần dư bị bỏ qua im lặng (không lỗi ở cả lúc ghi lẫn lúc đọc). Section rỗng (hết wallpaper hiển thị được) **bị bỏ hẳn và không chiếm slot**. Chưa bật gì → `sections: []` + 200, không phải 404. Trùng `home_position` → thứ tự vẫn **ổn định giữa các request** (tie-break theo id).
> - **`Wallpaper.description` nay trả giá trị thật** (v0.6.0 mới chỉ khai báo, backend luôn trả `null`). Rỗng/whitespace được chuẩn hoá thành `null` — client vẫn ẩn mục "Mô tả" chỉ bằng phép kiểm tra null.
> - Thêm **`PATCH /admin/wallpapers/{id}`** chỉ sửa `description` (điền mô tả cho catalog cũ). Admin bật section qua `show_on_home`/`home_position` trong body `POST|PATCH /admin/collections`.
> - **Payload công khai `GET /collections` KHÔNG đổi** — 2 field home chỉ là input phía admin.
> - **Không error code mới.** Additive → client viết theo v0.6.0 vẫn chạy nguyên.
>
> **Đổi so với v0.5.0 (mobile-driven)**: thêm field **`Wallpaper.description`** (`string`, nullable) cho mục "Mô tả" màn Wallpaper Detail (screen-inventory #7) — khai báo trước ở v0.6.0, backend implement thật ở v0.7.0. **Related wallpapers KHÔNG thêm endpoint** — client suy theo `GET /wallpapers?tags=<tag đầu tiên của wallpaper>` (loại chính nó, ≤6). Palette là suy diễn phía client, không cần backend.
>
> **Đổi so với v0.4.0 (BE-005)**: IAP verify + entitlement đi vào hoạt động thật. `GET /wallpapers/{id}/download-url` với wallpaper **premium** THÔI trả `402` vô điều kiện — nay kiểm tra entitlement thật từ `transaction_id` đã verify: entitled (`status ∈ {active, in_grace_period}`, chưa quá `expires_at`) → `200` presigned ≤5 phút; thiếu/hết hạn/không entitled → `402 ENTITLEMENT_REQUIRED`. Free giữ nguyên (bỏ qua `transaction_id`). Kích hoạt `POST /iap/verify-receipt`, `GET /iap/subscription-status`, `POST /iap/webhook/apple|google`. Entitlement **định danh theo original transaction id** (ổn định qua mọi kỳ renewal — mọi `transaction_id` trong chuỗi resolve về 1 entitlement); tắt auto-renew mà còn trong kỳ → `status=active, auto_renew=false`; `device_id` chỉ để phát hiện lạm dụng (restore trên máy mới tự do). **Không error code mới** (các mã IAP đã có sẵn trong catalog từ trước).
>
> **Đổi so với v0.3.2 (BE-004)**: thêm **admin auth surface** — `POST /admin/auth/login` (credential Django staff → JWT access 30 phút + refresh 7 ngày) và `POST /admin/auth/refresh` (rotate: trả cặp token MỚI, refresh cũ bị blacklist). `GET /wallpapers/{id}/download-url` **hết mock**: wallpaper free → presigned URL thật hết hạn ≤5 phút (⚠️ domain S3/R2 endpoint, KHÁC domain CDN của `thumbnail_url`/`preview_video_url` — client không hardcode/so sánh domain); premium giữ nguyên `402` cho tới BE-005; wallpaper `processing`/`failed`/đã xóa → `404`. `POST /admin/wallpapers`: `422 FILE_REJECTED` bắn **đồng bộ** tại register khi file vượt 500 MB (HEAD check); lỗi nội dung file phát hiện bất đồng bộ → `status=failed` (không 422). **Không error code mới**. Bỏ server "Staging" khỏi openapi (kỷ luật 2-flavor).
>
> **Đổi so với v0.3.1**: `GET /tags` giờ chèn **tag ảo "Tất cả"** (`{ id: 0, slug: "all", name: "Tất cả", wallpaper_count: <tổng published> }`) ở đầu mảng — do API sinh, KHÔNG lưu DB, làm chip mặc định "lấy toàn bộ". Slug `all` là **reserved**: `GET /wallpapers?tags=` bỏ qua slug `all` (không ràng buộc tag). Không thêm endpoint/error code nào; không đổi schema Wallpaper.
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
- Danh sách tag curated (không phân trang). Phần tử **đầu tiên luôn là tag ảo "Tất cả"** (`id: 0`, `slug: "all"`) do API sinh — không lưu DB, `wallpaper_count` = tổng wallpaper published. Client render làm chip mặc định; chọn "All" = gọi `GET /wallpapers` **không** truyền `tags`.
- **200**:
```json
[
  { "id": 0, "slug": "all", "name": "Tất cả", "wallpaper_count": 128 },
  { "id": 12, "slug": "neon", "name": "Neon", "wallpaper_count": 87 }
]
```
- **Reserved**: slug `all` không được dùng cho tag thật (admin/seed cấm tạo); trong filter `?tags=` slug `all` bị bỏ qua (coi như không ràng buộc).
- **401**: `INVALID_APP_KEY`

### `GET /home` *(v0.7.0)*
- Header: `X-App-Key`
- **Cả màn Browse trong 1 lần gọi** — không phân trang, không query param nào. Section = 1 `Collection` được admin bật `show_on_home`; **không có resource mới**.
- **Bounded cứng: tối đa 10 section × tối đa 10 wallpaper/section.** Trần áp **lúc đọc** — admin bật dư thì phần dư bị bỏ qua im lặng (không lỗi ở cả 2 phía).
- Thứ tự section theo `home_position` tăng dần; **trùng vị trí vẫn ổn định giữa các request** (tie-break theo id) — client cache/scroll-state không bị nhảy.
- Chỉ chứa wallpaper `published`. Section không còn wallpaper nào hiển thị được thì **bị bỏ hẳn và KHÔNG chiếm slot** — section kế tiếp lấp vào. Chưa bật collection nào → `sections: []` + **200** (KHÔNG phải 404).
- `key` = slug của collection, dùng làm định danh ổn định phía client (đổi `title` không đổi `key`). `collection_id` là target của "Xem tất cả" → `GET /collections/{id}` đã có (trong section KHÔNG có phân trang).
- **Không nhận và không đọc `transaction_id`**: section premium chỉ hiển thị badge, gate entitlement vẫn duy nhất ở `download-url`. Response không chứa download URL nào.
- Mỗi phần tử `items` dùng **đúng schema `Wallpaper` như mọi list khác** (`collections` rỗng) — client dùng chung 1 model.
- **200**:
```json
{
  "sections": [
    {
      "key": "neon-nights",
      "title": "Neon về đêm",
      "collection_id": 1,
      "cover_url": "https://cdn.example.com/collections/neon-nights.jpg",
      "accent_color": "#FF6F9C",
      "is_premium": false,
      "items": [ { "id": 5, "title": "Shibuya 2099", "description": null, "...": "..." } ]
    }
  ]
}
```
- **401**: `INVALID_APP_KEY`

### `GET /collections`
- Header: `X-App-Key`
- Danh sách bộ sưu tập curated (tab "Bộ sưu tập") — **không phân trang**, chỉ meta + `wallpaper_count`, KHÔNG nhúng items.
- **v0.7.0 KHÔNG đổi payload này**: `show_on_home`/`home_position` chỉ là input phía admin, không xuất hiện ở đây.
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
- Query: `cursor` (string, optional), `limit` (int, default 20, max 100), `category` (slug), `tags` (slug, phân tách phẩy — **AND**, phải khớp hết; slug reserved `all` bị bỏ qua → không truyền `tags` hoặc `tags=all` đều trả toàn bộ, sắp xếp mới→cũ), `orientation`, `search`, `is_premium`
- **200**:
```json
{
  "items": [
    {
      "id": 101,
      "title": "Neon City Loop",
      "description": null,
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
- **200** (v0.4.0 — presigned thật): `{ "download_url": "https://<s3-r2-endpoint>/masters/<uuid>.mp4?X-Amz-Signature=...", "expires_at": "..." }` — hết hạn **≤ 5 phút**, chỉ 1 object. ⚠️ Domain là **S3/R2 endpoint**, KHÁC domain CDN của thumbnail/preview — client không hardcode/so sánh domain.
- **402**: `ENTITLEMENT_REQUIRED` — wallpaper premium mà `transaction_id` thiếu / hết hạn / không resolve tới entitlement đang active|in_grace_period (v0.5.0). Free bỏ qua check. · **404**: `NOT_FOUND` (không tồn tại, `processing`, `failed`, hoặc đã xóa — đánh giá **trước** gate entitlement) · **401**: `INVALID_APP_KEY`

---

## IAP Endpoints

> **Entitlement model (v0.5.0)**: entitlement định danh theo **original transaction id** của store (ổn định qua mọi kỳ renewal); mọi `transaction_id` trong chuỗi renewal đều resolve về đúng 1 entitlement, nên verify/status/download tra bằng `transaction_id` kỳ nào cũng ra. `status` ∈ `active | in_grace_period | expired | canceled | refunded`. **Còn quyền tải** khi `status ∈ {active, in_grace_period}` và chưa quá `expires_at`. Tắt auto-renew mà còn trong kỳ → `active` + `auto_renew=false` (không phải `canceled`). `device_id` chỉ ghi nhận để phát hiện lạm dụng, KHÔNG chặn — restore trên máy mới verify lại bình thường.

### `POST /iap/verify-receipt`
- Header: `X-App-Key` (app tier)
- **Body**: `{ "platform": "ios", "receipt_data": "...", "transaction_id": "1000000123456789", "product_id": "premium_monthly", "device_id": "device-uuid-abc123" }` (`platform` ∈ `ios|android`)
- Backend verify trực tiếp với App Store Server API / Google Play Developer API, upsert entitlement (idempotent theo original transaction id).
- **200**: `{ "transaction_id": "...", "product_id": "premium_monthly", "status": "active", "expires_at": "2026-08-22T00:00:00Z", "auto_renew": true }` (schema `SubscriptionStatus`)
- **400**: `RECEIPT_INVALID` (store từ chối) · **409**: `RECEIPT_CONFLICT` (`transaction_id` đã gắn subscription/tài khoản store khác — KHÔNG phải chỉ khác device) · **503**: `STORE_API_UNAVAILABLE` (store timeout/5xx, retryable) · **401**: `INVALID_APP_KEY`

### `GET /iap/subscription-status`
- Header: `X-App-Key` · Query: `transaction_id` (bắt buộc; chấp nhận bất kỳ id trong chuỗi renewal)
- Read-only — KHÔNG mutate/gia hạn entitlement.
- **200**: schema `SubscriptionStatus` · **404**: `NOT_FOUND` (không có entitlement nào) · **401**: `INVALID_APP_KEY`

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

### `POST /admin/auth/login`
- Không header auth — credential trong body. KHÔNG nhận `X-App-Key` (2 tầng tách tuyệt đối).
- **Body**: `{ "username": "...", "password": "..." }` (Django staff user — không có hệ thống user app)
- **200**: `{ "access": "<jwt 30 phút>", "refresh": "<token 7 ngày>", "expires_in": 1800 }`
- **401**: `UNAUTHORIZED_ADMIN` (sai username/password) · **403**: `FORBIDDEN_ADMIN_ROLE` (đúng credential nhưng không phải staff hoặc tài khoản bị khoá)
- Mọi attempt (thành công/thất bại) đều được audit; password không bao giờ được ghi log.

### `POST /admin/auth/refresh`
- **Body**: `{ "refresh": "<refresh token còn hạn>" }`
- **200**: cùng schema login — cặp token **MỚI** (rotate); refresh cũ bị blacklist ngay, dùng lại → 401.
- **401**: `UNAUTHORIZED_ADMIN` (hết hạn / đã rotate / blacklist)

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
  "description": "Đèn neon phản chiếu trên mặt đường sau mưa.",
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
  - `description` (v0.7.0) **optional**; chuỗi rỗng hoặc toàn khoảng trắng được chuẩn hoá thành `null`.
- **201**: object `Wallpaper`, các field media (`thumbnail_url`, `resolution`...) = `null` vì đang xử lý bất đồng bộ
- **400**: `VALIDATION_ERROR` (thiếu field, `category_id` không tồn tại, `upload_key` đã dùng hoặc object chưa upload), `TAG_NOT_FOUND` (tag_ids sai)
- **422**: `FILE_REJECTED` — bắn **đồng bộ** khi HEAD thấy file vượt 500 MB. Lỗi nội dung (sai định dạng thật; malware scan từ BE-006) phát hiện **bất đồng bộ** trong pipeline → `status=failed` + `failure_reason` (xem qua `GET /admin/wallpapers?status=failed`), không 422 lúc đó.
- **401**: `UNAUTHORIZED_ADMIN` · **403**: `FORBIDDEN_ADMIN_ROLE`

### `GET /admin/wallpapers`
- Header: `Authorization: Bearer <admin_jwt>`
- Query: `cursor`, `limit`, `status` (`processing`|`published`|`failed`)
- **200**: `WallpaperCursorPage` (bao gồm cả wallpaper chưa publish); item tầng admin kèm thêm `status` và `failure_reason` (lý do khi `failed` — chỉ hiển thị ở tier admin, không bao giờ xuất hiện ở public tier)
- **401**: `UNAUTHORIZED_ADMIN` · **403**: `FORBIDDEN_ADMIN_ROLE`

### `PATCH /admin/wallpapers/{id}` *(v0.7.0)*
- Header: `Authorization: Bearer <admin_jwt>` · Path: `id`
- Sửa mô tả của wallpaper **đã tồn tại** (toàn bộ catalog cũ được tạo trước khi có field này nên chỉ đường này mới điền được cho chúng).
- **Body**: `{ "description": "Đèn neon phản chiếu trên mặt đường sau mưa." }`
  - **CHỈ nhận `description`** — mọi field khác trong body bị **bỏ qua**, không sửa được media/status/tag/category/collection (những thứ đó giữ luồng riêng).
  - `null`, chuỗi rỗng, hoặc toàn khoảng trắng → lưu `null` (client ẩn mục "Mô tả").
- **200**: object `Wallpaper` sau khi sửa
- **404**: `NOT_FOUND` (không tồn tại hoặc đã xóa mềm) · **401**: `UNAUTHORIZED_ADMIN` · **403**: `FORBIDDEN_ADMIN_ROLE`

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
  "show_on_home": true,
  "home_position": 0,
  "wallpaper_ids": [5, 6, 7, 8, 1, 3]
}
```
  - `wallpaper_ids` là **danh sách có thứ tự** (thứ tự này = thứ tự hiển thị trong bộ), phải trỏ tới wallpaper đã tồn tại.
  - `show_on_home` (v0.7.0, default `false`) + `home_position` (default `0`) quyết định bộ này có thành **section ở màn Browse** (`GET /home`) và đứng thứ mấy. Bật quá 10 bộ **vẫn hợp lệ** — trần chỉ áp lúc đọc. Hai field này là **input phía admin**, KHÔNG xuất hiện trong response `Collection`.
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
- Bật/tắt hoặc đổi chỗ section ở màn Browse (v0.7.0): `{ "show_on_home": true, "home_position": 2 }` — tắt bằng `{ "show_on_home": false }`, bộ sưu tập và trang riêng của nó không bị ảnh hưởng.
- **200**: object `Collection` sau khi cập nhật
- **400**: `VALIDATION_ERROR`, `WALLPAPER_NOT_FOUND`
- **404**: `NOT_FOUND` · **409**: `COLLECTION_SLUG_CONFLICT` (nếu đổi `slug` sang slug đã tồn tại)
- **401**/**403** như trên

### `DELETE /admin/collections/{id}`
- Header: `Authorization: Bearer <admin_jwt>` · Path: `id`
- Chỉ xóa bộ sưu tập (bản ghi nhóm) — **không xóa wallpaper thành viên**.
- **204**: đã xóa · **404**: `NOT_FOUND` · **401**/**403** như trên

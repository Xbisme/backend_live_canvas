# Contracts: Core Content API (BE-003)

> **Contract đã đóng băng** — nguồn sự thật là `contracts/openapi.yaml` **v0.3.2** +
> `.claude/api-context.md` **v0.3.2**. BE-003 **chỉ hiện thực**, KHÔNG tạo/sửa contract mới
> (Constitution I). File này chỉ **ánh xạ** endpoint contract ↔ implementation + hành vi kỳ vọng
> để viết test hợp đồng (Constitution X). Nếu phát hiện contract sai → dừng, sửa contract trước.

## Endpoint thuộc BE-003 (8 route public, tầng `X-App-Key`)

| # | Method & Path | View | Auth | Phân trang | Ghi chú hiện thực |
|---|---|---|---|---|---|
| 1 | `GET /categories` | `CategoryListView` | X-App-Key | Không | Trả nguyên mảng + `wallpaper_count` (annotate published) |
| 2 | `GET /tags` | `TagListView` | X-App-Key | Không | Trả nguyên mảng + `wallpaper_count` |
| 3 | `GET /collections` | `CollectionListView` | X-App-Key | Không | Meta + `wallpaper_count`, **không** nhúng items |
| 4 | `GET /collections/{id}` | `CollectionDetailView` | X-App-Key | Không | Meta + `items: Wallpaper[]` đúng thứ tự `position`, chỉ thành viên published |
| 5 | `GET /wallpapers` | `WallpaperListView` | X-App-Key | **Cursor** | Envelope `{items,next_cursor,has_more}`; filter category/tags(AND)/orientation/is_premium/search |
| 6 | `GET /wallpapers/{id}` | `WallpaperDetailView` | X-App-Key | — | Populate `collections` đầy đủ (CollectionRef) |
| 7 | `POST /wallpapers/batch` | `WallpaperBatchView` | X-App-Key | — | Body `{ids:[...]}` ≤100; bỏ qua id thiếu; `collections: []` |
| 8 | `GET /wallpapers/{id}/download-url` | `WallpaperDownloadUrlView` | X-App-Key | — | non-premium→200 mock; premium→402; ẩn/thiếu→404 |

> Prefix mount: các route trên nằm dưới `apps/wallpapers/urls.py`, include vào `config/urls.py`.
> Health (`/health`, `/health/ready`) của `core` **không** thuộc contract, giữ nguyên.

## Hành vi & mã lỗi kỳ vọng (để test hợp đồng)

### 1. `GET /categories` — `GET /tags`
- **200**: JSON array. Category item: `{id, slug, name, icon_url, wallpaper_count}`. Tag item:
  `{id, slug, name, wallpaper_count}`. `wallpaper_count` chỉ đếm published.
- **`GET /tags` — thẻ ảo "All" (v0.3.2)**: phần tử **[0] luôn là** `{ id: 0, slug: "all",
  name: "Tất cả", wallpaper_count: <tổng published> }` (API sinh, không DB), theo sau là tag thật.
  Test: mảng không rỗng, `result[0].id == 0 && result[0].slug == "all"`, `wallpaper_count` = tổng
  wallpaper published; không có tag thật nào mang slug `all`.
- **401** `INVALID_APP_KEY`: thiếu/sai `X-App-Key`.
- **405** `METHOD_NOT_ALLOWED`: method ≠ GET.

### 3. `GET /collections`
- **200**: array của Collection meta (không `items`), mỗi phần tử có `wallpaper_count`.
- **401** `INVALID_APP_KEY`.

### 4. `GET /collections/{id}`
- **200**: object Collection meta **+** `items: Wallpaper[]` (detail serializer) đúng thứ tự `position`,
  chỉ gồm wallpaper published. Bộ premium vẫn trả đầy đủ (không gate).
- **404** `NOT_FOUND`: id không tồn tại.
- **401** `INVALID_APP_KEY`.

### 5. `GET /wallpapers`
- Query: `cursor?`, `limit`(default 20, max 100), `category`(slug), `tags`(csv slug, **AND**;
  reserved slug `all` bị bỏ qua → `tags=all` hoặc không truyền = toàn bộ, mới→cũ),
  `orientation`(portrait|landscape|square), `is_premium`(bool), `search`(khớp title).
- **200**: envelope `{ items: Wallpaper[](list serializer), next_cursor: str|null, has_more: bool }`.
- **400** `VALIDATION_ERROR`: `cursor` hỏng/hết hạn, `limit`>100, `is_premium`/`orientation` sai giá trị.
- **401** `INVALID_APP_KEY`.
- Bất biến: chỉ trả published; tags AND; phân trang ổn định (R1).

### 6. `GET /wallpapers/{id}`
- **200**: Wallpaper (detail serializer) với `collections: CollectionRef[]` populate.
- **404** `NOT_FOUND`: id không tồn tại hoặc không published/đã xoá.
- **401** `INVALID_APP_KEY`.

### 7. `POST /wallpapers/batch`
- Body: `{ "ids": [int, ...] }`, 1..100 phần tử.
- **200**: array Wallpaper (list serializer) cho các id **published** tồn tại; id thiếu/ẩn **bỏ qua âm thầm**.
- **400** `VALIDATION_ERROR`: `ids` rỗng hoặc >100 hoặc sai kiểu.
- **401** `INVALID_APP_KEY`.

### 8. `GET /wallpapers/{id}/download-url`
- Query: `transaction_id?` (contract có, nhưng verify thật ở BE-005 — BE-003 bỏ qua giá trị).
- **200** (non-premium): `{ "download_url": "<mock/CDN url>", "expires_at": "<ISO8601, ≤ now+5m>" }`.
- **402** `ENTITLEMENT_REQUIRED` (premium): luôn, vì chưa có hệ thống verify (BE-005 hoàn thiện).
- **404** `NOT_FOUND`: id không tồn tại/không published.
- **401** `INVALID_APP_KEY`.

## Envelope lỗi (mọi endpoint)

`{ "error": { "code": "<CODE>", "message": "..." } }` — sinh **duy nhất** qua
`core.exception_handler.structured_exception_handler`. Mã dùng ở BE-003:
`INVALID_APP_KEY` (401), `VALIDATION_ERROR` (400), `NOT_FOUND` (404), `METHOD_NOT_ALLOWED` (405),
`ENTITLEMENT_REQUIRED` (402), `SERVER_ERROR` (500). Không body lỗi tự chế, không lộ traceback.

## KHÔNG thuộc BE-003 (giữ đúng ranh giới)

- Mọi route `/admin/*` (gồm `/admin/tags`, `/admin/collections`, admin wallpapers) → **BE-004**.
- `/iap/*` (verify-receipt, webhook, subscription-status) → **BE-005**.
- Presigned upload, transcode/thumbnail/scan → **BE-004**.
- Entitlement thật tại download-url (verify `transaction_id` với Apple/Google) → **BE-005**.

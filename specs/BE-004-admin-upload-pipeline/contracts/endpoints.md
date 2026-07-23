# Contracts: Admin Upload Pipeline (BE-004)

> BE-004 **thay đổi contract** (khác BE-003 vốn chỉ implement): bump `contracts/openapi.yaml` +
> `.claude/api-context.md` **v0.3.2 → v0.4.0** theo research D9, cập nhật
> `docs/screen-inventory.md` TRƯỚC, và sync mobile (kèm trả nợ v0.3.2) TRƯỚC KHI code endpoint
> (Constitution I). File này ánh xạ surface v0.4.0 ↔ implementation để viết contract test.

## Surface MỚI trong v0.4.0

| # | Method & Path | View (dự kiến) | Auth | Ghi chú |
|---|---|---|---|---|
| 1 | `POST /admin/auth/login` | `core` `AdminLoginView` | Không (credential trong body) | `{username,password}` → `{access, refresh, expires_in}`. Sai credential → 401 `UNAUTHORIZED_ADMIN`; đúng credential nhưng non-staff/disabled → 403 `FORBIDDEN_ADMIN_ROLE`. Audit cả success/fail. |
| 2 | `POST /admin/auth/refresh` | `core` `AdminRefreshView` | Không (refresh trong body) | `{refresh}` → `{access, refresh, expires_in}` — refresh cũ bị blacklist (rotate). Hết hạn/blacklisted → 401 `UNAUTHORIZED_ADMIN`. |
| 3 | `POST /admin/uploads/presign` | `apps/uploads` `PresignView` | AdminBearer | `{filename, content_type}` → `{upload_url, upload_key, expires_at}`. content_type ngoài whitelist → 400 `VALIDATION_ERROR`. |
| 4 | `POST /admin/wallpapers` | `apps/wallpapers` `AdminWallpaperListCreateView` | AdminBearer | Body theo contract v0.3.x (§POST /admin/wallpapers). 201 → Wallpaper `status=processing`, media fields null. `TAG_NOT_FOUND` / `VALIDATION_ERROR` / slot đã dùng / object chưa upload → 400. **HEAD-check lúc register**: Content-Length > 500MB → **422 `FILE_REJECTED` đồng bộ**; lỗi nội dung (sniff/transcode) surface bất đồng bộ qua `status=failed` (remediation A1). |
| 5 | `GET /admin/wallpapers` | (cùng view #4) | AdminBearer | Cursor + `?status=processing\|published\|failed`; item kèm `failure_reason` (chỉ tier admin). |
| 6 | `DELETE /admin/wallpapers/{id}` | `AdminWallpaperDetailView` | AdminBearer | 204 soft-delete; 404 `NOT_FOUND`. |
| 7 | `POST /admin/tags` · `GET /admin/tags` · `DELETE /admin/tags/{id}` | `AdminTagView*` | AdminBearer | Create: slug `all` reserved + trùng slug → 400/409. GET kèm `wallpaper_count`. DELETE tag đang dùng → 409 `TAG_IN_USE`. |
| 8 | `POST/GET /admin/collections` · `PATCH/DELETE /admin/collections/{id}` | `AdminCollectionView*` | AdminBearer | `wallpaper_ids` ordered; `WALLPAPER_NOT_FOUND`, `COLLECTION_SLUG_CONFLICT`; cover qua `cover_upload_key` (slot image). PATCH reorder = thay thế atomic. |

## Surface SỬA HÀNH VI trong v0.4.0

| Method & Path | Trước (v0.3.2) | Sau (v0.4.0) |
|---|---|---|
| `GET /wallpapers/{id}/download-url` | non-premium → 200 **mock**; premium → 402 | non-premium → 200 `{download_url: <presigned S3/R2, TTL ≤ 300s>, expires_at}`; premium → 402 `ENTITLEMENT_REQUIRED` (không đổi — gate mở ở BE-005); `processing/failed/deleted` → 404 |

⚠️ **Ghi chú cho mobile (đưa vào api-context.md)**: `download_url` trỏ **S3/R2 API endpoint**
(presign không hoạt động qua CDN domain — research R4), khác domain với `thumbnail_url`/
`preview_video_url` (CDN). Client không được hardcode/so sánh domain.

## Không đổi

- Toàn bộ public tier còn lại (categories/tags/collections/wallpapers list-detail-batch) giữ nguyên shape v0.3.2.
- **Không error code mới** — dùng nguyên catalog: `UNAUTHORIZED_ADMIN`, `FORBIDDEN_ADMIN_ROLE`,
  `VALIDATION_ERROR`, `TAG_NOT_FOUND`, `TAG_IN_USE`, `WALLPAPER_NOT_FOUND`,
  `COLLECTION_SLUG_CONFLICT`, `FILE_REJECTED`, `ENTITLEMENT_REQUIRED`, `NOT_FOUND`.
- Health endpoints ngoài contract (như cũ).

## Ràng buộc cách ly tier (test bắt buộc — SC-004)

Với **từng** route admin (#3–#8): gửi `X-App-Key` hợp lệ (không Bearer) → 401 `UNAUTHORIZED_ADMIN`.
Với route app-tier bất kỳ (vd `GET /wallpapers`): gửi Bearer admin hợp lệ (không X-App-Key) →
401 `INVALID_APP_KEY`. Không endpoint nào chấp nhận cả hai.

## Async contract (không phải HTTP nhưng là hành vi hợp đồng)

- Sau `POST /admin/wallpapers` 201: trạng thái quan sát được qua `GET /admin/wallpapers?status=...`
  chuyển `processing → published` (media fields chuyển null → giá trị thật, URL thuộc CDN domain)
  hoặc `processing → failed` (+`failure_reason`). Public tier không thấy item cho tới `published`.
- Backfill dùng đúng chuỗi trạng thái trên cho 397 item hiện có; hoàn tất khi
  `GET /wallpapers` không còn bất kỳ URL nào chứa domain Pexels (SC-002/FR-017).

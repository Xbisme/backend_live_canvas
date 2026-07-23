# Data Model: Admin Upload Pipeline (BE-004)

> Phase 1 — thay đổi schema so với BE-003. Tất cả migration **additive** (field nullable/model mới),
> không destructive (Constitution IX). Nguồn quyết định: [research.md](research.md) D1, D6, D7, D8.

## 1. `Wallpaper` — field mới (apps/wallpapers)

| Field | Type | Null | Ý nghĩa |
|---|---|---|---|
| `master_key` | `CharField(255)` | ✔ | Key object master H.264 trong bucket **private** (`masters/{uuid4}.mp4`). `NULL` = chưa có file tự host (điều kiện skip của backfill). Non-guessable (FR-007). |
| `staging_key` | `CharField(255)` | ✔ | Key file gốc đã upload (`staging/{uuid4}.{ext}`); giữ tới khi publish xong thì xóa object + clear field. Cho phép retry transcode. |
| `thumbnail_key` | `CharField(255)` | ✔ | Key JPEG trong bucket **public**; `thumbnail_url` = `CDN_BASE_URL + key` (đã tồn tại, tiếp tục là giá trị serve cho client). |
| `preview_key` | `CharField(255)` | ✔ | Key MP4 preview watermark trong bucket **public**; tương tự cho `preview_video_url`. |
| `failure_reason` | `TextField` | ✔ | Lý do `failed` (stderr ffmpeg rút gọn / "not a video" / "exceeds 500MB"). Chỉ admin thấy (GET /admin/wallpapers), không leak ra public tier. |

Giữ nguyên: `status` (`processing|published|failed` — enum có sẵn từ BE-003), `deleted_at`
(soft-delete), URL fields (nay được pipeline ghi đè từ `*_key`), provenance
(`source_url`, `license_type`).

**Invariant** (đã có từ BE-003, không đổi): public tier chỉ thấy `published() = status=published AND
deleted_at IS NULL`. Item `processing`/`failed` không bao giờ leak.

### State machine (FR-009/010)

```
                    ┌─────────── retry (re-enqueue từ staging) ───────────┐
                    ▼                                                     │
 [register/backfill] ──▶ processing ──(pipeline OK, atomic)──▶ published  │
                              │                                           │
                              └──(sniff fail | >500MB | ffmpeg err)──▶ failed ──┘
```

- `processing → published`: MỘT lần ghi DB atomic (update keys + urls + metadata + status trong
  1 transaction) — không có trạng thái nửa vời (Constitution VII).
- `failed`: giữ `staging_key` để inspect/retry; `failure_reason` bắt buộc có giá trị.
- Task idempotent: guard đầu task theo **`master_key` đã có** (= media tự host đã tồn tại) → no-op.
  KHÔNG guard theo `status==published` — item seeded vào backfill ở trạng thái published với URL
  tạm và vẫn phải được xử lý (phát hiện khi implement US2).

## 2. `UploadSlot` — model mới (apps/uploads)

| Field | Type | Constraint | Ý nghĩa |
|---|---|---|---|
| `key` | `CharField(255)` | unique | `staging/{uuid4hex}.{ext}` — sinh lúc presign |
| `purpose` | `CharField` choices `video|image` | | Video wallpaper hay cover collection |
| `content_type` | `CharField(100)` | | Loại client khai (chỉ để presign; KHÔNG tin khi xử lý — sniff lại) |
| `created_by` | FK `auth.User` PROTECT | | Admin đã xin slot |
| `created_at` | auto | | |
| `consumed_at` | `DateTimeField` | ✔ null | Set khi register thành công — **cùng transaction** tạo Wallpaper/Collection cover |

- **Single-use** (FR-008): register dùng `select_for_update()` trên slot; slot đã `consumed_at`
  → `VALIDATION_ERROR` ("upload already registered"). Unique `key` chặn trùng tuyệt đối.
- **Orphan** (edge case): `consumed_at IS NULL AND created_at < now()-24h` → liệt kê/xóa qua
  `manage.py purge_stale_uploads` (kèm xóa object staging). Không tự động chạy nền.

## 3. `AuditLogEntry` — model mới (apps/audit)

| Field | Type | Ý nghĩa |
|---|---|---|
| `actor` | FK `auth.User` SET_NULL, null | Null khi user đã bị xóa (record vẫn còn) hoặc login-fail chưa map user |
| `actor_label` | `CharField(150)` | Username snapshot tại thời điểm ghi (bền vững khi user đổi/xóa) |
| `action` | `CharField(60)` | Slug: `admin.login`, `admin.login_failed`, `wallpaper.create`, `wallpaper.delete`, `tag.create`, `tag.delete`, `collection.create`, `collection.update`, `collection.delete`, `upload.presign`, `upload.register`, `backfill.run` |
| `object_type` | `CharField(60)` | `wallpaper|tag|collection|upload_slot|auth|backfill` |
| `object_id` | `CharField(60)`, blank | Id đối tượng (string để chứa cả non-int) |
| `metadata` | `JSONField` default dict | Chi tiết nhẹ (vd. slug, title, count). **CẤM** chứa token/password/presigned URL (FR-019 — service `record()` là chốt chặn duy nhất, có test) |
| `created_at` | auto, db_index | |

- Append-only: không expose update/delete qua bất kỳ API/service nào; ghi **đồng bộ trong cùng
  transaction** với mutation (research D8).

## 4. Bảng của `token_blacklist` (simplejwt — third-party)

`OutstandingToken` + `BlacklistedToken` do app `rest_framework_simplejwt.token_blacklist` cung cấp
(migrate sẵn của package). Rotation 7-ngày + blacklist-after-rotation (research D1). Không model
tự viết.

## 5. Key scheme & zone (tham chiếu research D3/D6)

| Zone | Bucket env | Prefix | Truy cập |
|---|---|---|---|
| Staging | `AWS_STORAGE_BUCKET_NAME` (private) | `staging/` | presigned PUT (upload), worker GET |
| Master | `AWS_STORAGE_BUCKET_NAME` (private) | `masters/` | presigned GET ≤ 5' qua download-url |
| Thumbnail | `AWS_PUBLIC_BUCKET_NAME` | `thumbs/` | public-read, URL = `CDN_BASE_URL` + key |
| Preview | `AWS_PUBLIC_BUCKET_NAME` | `previews/` | public-read, URL = `CDN_BASE_URL` + key |
| Collection cover | `AWS_PUBLIC_BUCKET_NAME` | `covers/` | public-read; ảnh sniff image OK từ slot `purpose=image` chuyển thẳng vào đây (không qua pipeline video) |

## 6. Quan hệ tổng thể (mới so với BE-003)

```
auth.User (staff) ──┬── UploadSlot.created_by
                    ├── AuditLogEntry.actor
                    └── (simplejwt OutstandingToken.user)

UploadSlot ──(consumed bởi, logic — không FK)──▶ Wallpaper.staging_key = slot.key
Wallpaper ──(keys)──▶ objects trong 2 bucket (không FK — storage ngoài DB)
```

`UploadSlot` KHÔNG có FK sang Wallpaper: liên kết qua `staging_key` value — tránh vòng phụ thuộc
uploads↔wallpapers; uploads chỉ expose service `consume_slot(key)` cho wallpapers gọi
(Constitution V — cross-app qua public service).

## 7. Validation rules tập trung (từ FR)

| Rule | Nơi enforce | Error |
|---|---|---|
| `tag_ids` phải tồn tại | serializer admin wallpaper/collection | `TAG_NOT_FOUND` (400) |
| `wallpaper_ids` phải tồn tại | serializer admin collection | `WALLPAPER_NOT_FOUND` (400) |
| slug collection trùng | service create/update | `COLLECTION_SLUG_CONFLICT` (409) |
| tag slug `all` reserved | validator model (đã có BE-003) | `VALIDATION_ERROR` |
| xóa tag đang dùng | service delete tag | `TAG_IN_USE` (409) |
| slot single-use | `select_for_update` + `consumed_at` | `VALIDATION_ERROR` |
| content_type presign whitelist | serializer presign (`video/mp4`, `video/quicktime`, `image/jpeg|png|webp`) | `VALIDATION_ERROR` |
| ≤500MB (HEAD Content-Length) | serializer register — **đồng bộ**, không tải bytes | `FILE_REJECTED` (422) |
| object tồn tại lúc register | serializer register (HEAD) | `VALIDATION_ERROR` |
| sniff magic-bytes (nội dung thật) | Celery task (range-GET 2KB) — bất đồng bộ | `failed` + reason |
| reorder collection atomic | service update trong `transaction.atomic` (delete + bulk_create như seeder) | — |

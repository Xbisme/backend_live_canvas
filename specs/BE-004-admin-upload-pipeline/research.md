# Research: Admin Upload Pipeline (BE-004)

> Phase 0 — chốt các quyết định kỹ thuật còn mở sau spec + clarify. Mọi version tra trực tiếp
> PyPI ngày 2026-07-23 (Constitution XI). Không còn NEEDS CLARIFICATION nào tồn đọng.

## D1. Admin JWT: `djangorestframework-simplejwt` 5.5.1

- **Decision**: dùng `djangorestframework-simplejwt==5.5.1` + app `token_blacklist` của nó.
  Cấu hình: `ACCESS_TOKEN_LIFETIME=30min`, `REFRESH_TOKEN_LIFETIME=7days`,
  `ROTATE_REFRESH_TOKENS=True`, `BLACKLIST_AFTER_ROTATION=True` (khớp Clarify Q2).
  View login/refresh tự viết mỏng trong `core` (không dùng view mặc định của simplejwt) để:
  (a) ép check `is_staff` → `FORBIDDEN_ADMIN_ROLE`, (b) trả lỗi qua catalog handler
  (`UNAUTHORIZED_ADMIN`), (c) audit mọi attempt.
- **Rationale**: classifier xác nhận hỗ trợ Django 5.2 + DRF; rotation/blacklist có sẵn khỏi tự
  chế bảng; cộng đồng lớn, API ổn định.
- **Alternatives considered**: PyJWT tự wrap (phải tự làm refresh rotation + blacklist — reinvent);
  `django-rest-knox` (token DB-backed, không phải JWT — lệch contract "Bearer <jwt>"); session auth
  (Constitution II cấm — đó là tier Django admin nội bộ).

## D2. Task queue: `celery[redis]` 5.6.3 + redis client 6.4.0 (kombu cap), KHÔNG result backend

- **Decision**: Celery 5.6.3, broker Redis (container dev / managed prod). Client `redis` KHÔNG pin
  riêng trong `.in`: kombu 5.6 caps `redis <6.5` nên PyPI redis 8.x chưa dùng được — resolver chốt
  `redis==6.4.0` trong `.txt` lock (phát hiện khi compile 2026-07-23).
  Không cài `django-celery-results` — kết quả task phản ánh vào `Wallpaper.status`
  (`processing|published|failed`) + `failure_reason`; đó là nguồn sự thật duy nhất.
  Test chạy `task_always_eager=True`.
- **Rationale**: trạng thái nghiệp vụ đã có chỗ đứng trong DB theo contract; result backend là bảng
  thứ hai kể cùng một câu chuyện → drift. Redis đằng nào cũng cần cho broker.
- **Alternatives considered**: `django-celery-results` (thừa, xem trên); RQ (nhẹ hơn nhưng
  constitution VII đã chỉ định Celery, retry/acks semantics tốt hơn); Celery beat (chưa cần —
  không có job định kỳ trong scope).

## D3. Two-zone storage trên R2/MinIO: **2 bucket**, không phải 1 bucket + ACL

- **Decision**: 2 bucket riêng: `<prefix>-private` (staging/ + masters/, chỉ presigned GET/PUT) và
  `<prefix>-public` (thumbs/ + previews/, public-read qua CDN). `apps/uploads/storage.py` bọc 2
  boto3 client/bucket, expose: `presign_upload(key)`, `presign_download(key, ttl≤300s)`,
  `public_url(key)` (= `CDN_BASE_URL` + key), `upload_file(path, key, bucket)`.
- **Rationale**: **R2 không hỗ trợ per-object ACL kiểu S3** — public access ở R2 bật theo bucket
  (custom domain / r2.dev). Vậy mô hình 2 vùng của Clarify Q1 map tự nhiên thành 2 bucket; MinIO
  dev mirror y hệt (bucket public gắn anonymous download policy lúc init). Cùng một code path cho
  cả 2 flavor, chỉ khác env.
- **Alternatives considered**: 1 bucket + prefix ACL (không làm được trên R2); 1 bucket private +
  presign cả thumbnail (đã bác ở Clarify Q1 — phá CDN cache, ký N URL mỗi list request);
  Cloudflare Worker làm gate (thêm hạ tầng ngoài scope backend).
- **Env mới** (cả `.env.dev.example` + `.env.prod.example`):
  `AWS_STORAGE_BUCKET_NAME` (private — giữ tên cũ BE-002), `AWS_PUBLIC_BUCKET_NAME`,
  `CDN_BASE_URL` (đã có), `CELERY_BROKER_URL`, `UPLOAD_MAX_BYTES=524288000`,
  `BACKFILL_DATASET_DIR` (dev-only, trỏ thư mục livewallpapers local).

## D4. MIME sniffing: `python-magic` 0.4.27 (libmagic)

- **Decision**: `python-magic==0.4.27`, sniff 2048 byte đầu của object (S3 range-GET) TRƯỚC khi tải
  cả file về worker; chấp nhận `video/mp4`, `video/quicktime`; cover image chấp nhận
  `image/jpeg|png|webp`. Sai loại hoặc `Content-Length > 500 MB` → `failed`/`FILE_REJECTED`
  không tải tiếp.
- **Rationale**: libmagic là chuẩn de-facto cho content sniffing (Constitution VII yêu cầu "real
  MIME"); range-GET giúp từ chối sớm file rác không tốn băng thông.
- **Alternatives considered**: `puremagic` (pure-python, không cần lib hệ thống nhưng DB chữ ký
  nghèo hơn rõ rệt); `ffprobe` làm sniffer (chạy được nhưng chậm hơn và lỗi khó phân loại — vẫn
  dùng ffprobe ở bước sau để lấy metadata); tin `content_type` client (bị VII cấm thẳng).
- **Hệ quả môi trường**: dev macOS `brew install libmagic ffmpeg`; prod image cài `libmagic1` +
  `ffmpeg` (ghi vào quickstart + README).

## D5. ffmpeg pipeline (subprocess, không thư viện binding)

- **Decision**: gọi `ffmpeg`/`ffprobe` qua `subprocess.run` (timeout, capture stderr làm
  `failure_reason`), wrapper tại `apps/uploads/ffmpeg.py`:
  1. **probe**: `ffprobe -print_format json` → width/height/duration/codec (điền metadata + orientation check).
  2. **master normalize**: `-c:v libx264 -profile:v high -preset medium -crf 20 -pix_fmt yuv420p -movflags +faststart -an`
     — giữ nguyên resolution, bỏ audio (wallpaper không cần), faststart cho progressive download.
  3. **thumbnail**: frame tại giây 1 → JPEG, scale cạnh dài 1080 (`-vf scale='min(1080,iw)':-2 -frames:v 1 -q:v 3`).
  4. **preview**: scale cạnh ngắn 720 (portrait 2160×3840 → 720×1280), watermark **drawtext**
    (`LiveCanvas`, alpha 0.35, góc dưới phải, fontsize theo chiều cao), `-crf 28 -preset veryfast -t 10`
    (cắt 10s đầu — preview không cần full độ dài), `-an`.
- **Rationale**: subprocess giữ dependency Python = 0 cho media; drawtext khỏi cần asset PNG
  (câu hỏi outstanding từ clarify — chốt tại đây); tham số CRF 20/28 là cân bằng chuẩn
  chất lượng/dung lượng cho H.264.
- **Alternatives considered**: `ffmpeg-python` binding (thêm dep chỉ để build chuỗi string);
  watermark PNG overlay (cần quản lý asset, làm sau nếu cần brand thật); HEVC master (nhỏ hơn
  ~30% nhưng license/compat rủi ro trên Android cũ — spec đã chốt H.264).

## D6. Key scheme & vòng đời object

- **Decision**:
  - Staging (private): `staging/{uuid4hex}.{ext}` — sinh lúc presign, ghi vào `UploadSlot`.
  - Master (private): `masters/{uuid4hex}.mp4` — uuid MỚI, không suy ra được từ id/slug (FR-007).
  - Public: `thumbs/{uuid4hex}.jpg`, `previews/{uuid4hex}.mp4`.
  - `UploadSlot` 1-1 với lần presign: `key`, `content_type`, `purpose(video|image)`, `created_by`,
    `created_at`, `consumed_at` — register set `consumed_at` trong cùng transaction tạo Wallpaper
    (chặn double-register, FR-008); slot chưa consume sau 24h = orphan (lệnh `purge_stale_uploads`
    liệt kê/xóa — chốt câu hỏi outstanding "orphan cleanup": chỉ management command, KHÔNG cron).
  - Staging object bị xóa sau khi publish thành công (master đã là bản chuẩn hoá).
- **Rationale**: uuid4 128-bit chặn enumeration; tách staging/master cho phép retry transcode từ
  staging mà không đụng master đang phục vụ; slot table cho single-use + orphan visibility.
- **Alternatives considered**: key theo `wallpapers/{id}/master.mp4` (đoán được từ id public —
  IDOR risk, vi phạm III); TTL lifecycle rule trên bucket (R2 hỗ trợ nhưng dev MinIO cấu hình
  lệch — command chủ động minh bạch hơn).

## D7. Backfill: idempotency theo trạng thái Wallpaper, không bảng riêng

- **Decision**: `manage.py backfill_media --dataset-dir=... [--limit N] [--dry-run]`:
  đọc fixture đã commit (nguồn `local_path` ↔ `source_url`), với mỗi wallpaper
  `master_key IS NULL AND deleted_at IS NULL`: upload file gốc → staging, tạo/consume UploadSlot
  nội bộ, enqueue **đúng task `process_wallpaper`** như upload thường. Wallpaper có `master_key`
  → skip (resume tự nhiên); file thiếu trên disk → log + skip + đếm vào summary; kết thúc in
  `processed/skipped-done/skipped-missing/failed`.
- **Rationale**: "đã có master_key" chính là định nghĩa "hoàn tất" — thêm bảng tracking là
  double-bookkeeping (khớp FR-015/016: một đường xử lý duy nhất, resumable).
- **Alternatives considered**: bảng BackfillRun/BackfillItem (thừa — xem trên); upload thẳng
  master không qua pipeline (vi phạm FR-015 "same pipeline", mất normalize/watermark).
- **Lưu ý**: pipeline set `thumbnail_url`/`preview_video_url` từ public bucket → tự nhiên thay
  URL Pexels (FR-017); `source_url`/`license_type`/fixture author giữ nguyên (không đụng).

## D8. Audit log: app mới `apps/audit`, ghi đồng bộ trong transaction

- **Decision**: model `AuditLogEntry(actor FK User SET_NULL, action slug, object_type, object_id,
  metadata JSONField, created_at)` — append-only (không update/delete API); service duy nhất
  `audit.services.record(actor, action, obj, **meta)`; gọi đồng bộ trong cùng DB transaction của
  mutation (không Celery — audit không được lạc mất khi broker chết). Login thất bại ghi
  `action="admin.login_failed"` với username submitted (KHÔNG ghi password — FR-019).
- **Rationale**: đồng bộ + cùng transaction = audit và mutation atomic; JSONField đủ linh hoạt
  cho diff nhẹ mà không thiết kế schema event phức tạp.
- **Alternatives considered**: `django-auditlog` package (kéo middleware + signal magic, nhiều hơn
  cần — scope chỉ cần mutations admin chủ động); ghi qua logging JSON (không query được, không
  bền vững bằng DB row).

## D9. Contract v0.4.0 — surface thay đổi (thực hiện TRƯỚC code, Constitution I)

- **Decision**: bump `contracts/openapi.yaml` + `.claude/api-context.md` lên **v0.4.0**:
  1. **Thêm** `POST /admin/auth/login` `{username,password}` → `{access, refresh, expires_in}`;
     lỗi: 401 `UNAUTHORIZED_ADMIN` (sai credential), 403 `FORBIDDEN_ADMIN_ROLE` (non-staff).
  2. **Thêm** `POST /admin/auth/refresh` `{refresh}` → `{access, refresh, expires_in}` (rotate);
     401 `UNAUTHORIZED_ADMIN` khi refresh hết hạn/blacklist.
  3. **Sửa mô tả** `GET /wallpapers/{id}/download-url`: bỏ ghi chú mock; free → presigned URL thật
     ≤5'; premium → 402 (không đổi shape).
  4. `docs/screen-inventory.md`: thêm mục "Admin tooling (không phải màn hình app)" ghi nhu cầu
     auth admin — giữ đúng thứ tự screen-inventory → contract.
  - **Không error code mới** — catalog v0.3.2 đã đủ (xác nhận từng code ở Constitution Check IV).
  - Sync mobile: copy verbatim v0.4.0 (kèm trả nợ v0.3.2 chưa sync) — 1 lần sync duy nhất.
- **Rationale**: gộp nợ sync cũ + mới thành một thao tác; shape login/refresh theo chuẩn simplejwt
  đỡ translate; không thêm code lỗi mới giữ catalog ổn định.
- **Alternatives considered**: đặt auth ngoài contract vì "mobile không dùng" (bác — contract là
  nguồn sự thật cho MỌI client kể cả admin tool tương lai; Constitution I không phân biệt).

## Risks

- **R1 — Python 3.14 local vs Celery classifiers (≤3.13)**: venv dev đang CPython 3.14.3;
  Celery 5.6.3 chưa declare 3.14. Mitigation: smoke-test worker ngay task đầu (quickstart bước 5);
  nếu vỡ → pin venv dev về 3.13 (constitution yêu cầu 3.11+, không yêu cầu 3.14). KHÔNG downgrade
  Celery đời cũ.
- **R2 — ffmpeg/libmagic là dependency hệ thống**: không pin được qua pip. Mitigation: ghi version
  check vào quickstart (`ffmpeg -version` ≥ 6), CI cài qua apt, README cập nhật.
- **R3 — Backfill 22.4 GB một phiên**: upload phụ thuộc mạng máy operator. Mitigation: command
  resumable từng item (D7), `--limit` để chạy theo lô.
- **R4 — R2 presigned URL + custom domain**: presign chỉ hoạt động trên S3 API endpoint
  (`<account>.r2.cloudflarestorage.com`), KHÔNG qua CDN domain. Download-url trả endpoint S3 —
  chấp nhận (link 5 phút không cần cache CDN); ghi rõ trong endpoints.md để mobile không bất ngờ
  domain khác nhau giữa preview (CDN) và download (R2 endpoint).

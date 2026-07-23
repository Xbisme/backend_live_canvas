# Quickstart: Admin Upload Pipeline (BE-004)

> Hướng dẫn dựng dev stack và **chứng minh feature chạy end-to-end**. Chi tiết schema →
> [data-model.md](data-model.md); surface API → [contracts/endpoints.md](contracts/endpoints.md).

## 0. Prerequisites

```bash
# Binary hệ thống (macOS dev)
brew install ffmpeg libmagic          # ffmpeg -version ≥ 6
# Python deps (sau khi tasks cập nhật requirements/*.in và compile)
uv pip sync requirements/dev.txt
cp .env.dev.example .env.dev          # điền các biến MỚI (xem dưới)
```

Biến env mới trong `.env.dev` (đầy đủ trong `.env.dev.example` sau khi implement):

```dotenv
AWS_S3_ENDPOINT_URL=http://localhost:9000     # MinIO
AWS_STORAGE_BUCKET_NAME=livecanvas-private
AWS_PUBLIC_BUCKET_NAME=livecanvas-public
AWS_ACCESS_KEY_ID=minioadmin
AWS_SECRET_ACCESS_KEY=minioadmin
CDN_BASE_URL=http://localhost:9000/livecanvas-public/
CELERY_BROKER_URL=redis://localhost:6380/0
UPLOAD_MAX_BYTES=524288000                    # 500 MB
BACKFILL_DATASET_DIR=/Users/<you>/Documents/database/crawl_script/livewallpapers
```

## 1. Dựng hạ tầng dev

```bash
docker compose up -d db redis minio           # minio init tự tạo 2 bucket, bucket public gắn anonymous-download policy
python manage.py migrate
python manage.py createsuperuser              # staff user để login admin
python manage.py seed_content                 # nếu DB trống (397 wallpapers, URL Pexels tạm)
```

## 2. Chạy 2 process

```bash
python manage.py runserver                    # terminal 1 — API
celery -A config worker -l info               # terminal 2 — worker (smoke-test risk R1: phải boot sạch trên Python local)
```

## 3. Kịch bản 1 — Admin upload end-to-end (User Story 1)

```bash
# 3.1 Login (→ access/refresh; access sống 30')
curl -s -X POST localhost:8000/admin/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"username":"<admin>","password":"<pass>"}'
export TOK=<access>

# 3.2 Presign
curl -s -X POST localhost:8000/admin/uploads/presign \
  -H "Authorization: Bearer $TOK" -H 'Content-Type: application/json' \
  -d '{"filename":"test.mp4","content_type":"video/mp4"}'
# → {upload_url, upload_key, expires_at}

# 3.3 PUT thẳng file lên MinIO (API không đụng bytes)
curl -s -X PUT --upload-file /path/to/portrait.mp4 -H 'Content-Type: video/mp4' "<upload_url>"

# 3.4 Đăng ký (phản hồi < 2s, status=processing, media fields null)
curl -s -X POST localhost:8000/admin/wallpapers \
  -H "Authorization: Bearer $TOK" -H 'Content-Type: application/json' \
  -d '{"title":"Quickstart Clip","category_id":1,"tag_ids":[1],"orientation":"portrait",
       "is_premium":false,"source_url":"https://example.com/qs","license_type":"Test",
       "upload_key":"<upload_key>"}'

# 3.5 Theo dõi worker xử lý → published
curl -s -H "Authorization: Bearer $TOK" "localhost:8000/admin/wallpapers?status=processing"
curl -s -H "Authorization: Bearer $TOK" "localhost:8000/admin/wallpapers?status=published" | head
# Kỳ vọng: item mới có thumbnail_url/preview_video_url thuộc CDN_BASE_URL, resolution/duration thật
```

**Kiểm tra fail-path**: lặp 3.2–3.4 với một file `.txt` đổi tên `.mp4` → worker phát hiện qua
magic-bytes, item vào `?status=failed` với `failure_reason`, KHÔNG xuất hiện ở public tier.

## 4. Kịch bản 2 — Cách ly 2 tầng auth (SC-004)

```bash
curl -s -H "X-App-Key: dev-app-key" localhost:8000/admin/wallpapers   # → 401 UNAUTHORIZED_ADMIN
curl -s -H "Authorization: Bearer $TOK" localhost:8000/wallpapers      # → 401 INVALID_APP_KEY
```

## 5. Kịch bản 3 — Bulk backfill (User Story 2)

```bash
python manage.py backfill_media --limit 5      # chạy thử lô nhỏ
python manage.py backfill_media                # full 397 (resumable — Ctrl-C rồi chạy lại: item xong bị skip)
python manage.py backfill_media                # lần 2 → toàn bộ skip, summary 0 processed

# Verify không còn Pexels (SC-002/FR-017):
curl -s -H "X-App-Key: dev-app-key" "localhost:8000/wallpapers?limit=100" | grep -c pexels.com   # → 0 (qua các trang)
```

## 6. Kịch bản 4 — Download-url thật (User Story 3)

```bash
# Free wallpaper → presigned URL sống ≤5'
curl -s -H "X-App-Key: dev-app-key" localhost:8000/wallpapers/<free_id>/download-url
curl -sI "<download_url>" | head -1            # → 200; sau 5 phút → lỗi chữ ký
# Premium → vẫn đóng
curl -s -H "X-App-Key: dev-app-key" "localhost:8000/wallpapers/<premium_id>/download-url?transaction_id=x"  # → 402
```

## 7. Kịch bản 5 — Curated CRUD + audit (User Story 4–5)

```bash
curl -s -X POST localhost:8000/admin/tags -H "Authorization: Bearer $TOK" \
  -d '{"slug":"test-tag","name":"Test"}'                       # 201; slug "all" → 400
curl -s -X DELETE localhost:8000/admin/tags/<đang-dùng> -H "Authorization: Bearer $TOK"  # → 409 TAG_IN_USE
python manage.py shell -c "from apps.audit.models import AuditLogEntry; print(AuditLogEntry.objects.values_list('action', flat=True)[:10])"
# Kỳ vọng: admin.login, upload.presign, upload.register, tag.create... — không record nào chứa token/URL ký
```

## 8. Gates trước commit (Constitution — như mọi spec)

```bash
ruff check . && ruff format --check .
pytest                                          # storage/ffmpeg/magic mock; celery eager
python manage.py makemigrations --check --dry-run
```

## Expected outcomes tổng hợp

| Check | Kỳ vọng |
|---|---|
| Upload end-to-end | processing → published tự động, URL thuộc CDN dev, đăng ký < 2s |
| File giả dạng | failed + reason, không leak public |
| Cách ly tier | 2 chiều đều 401 đúng code catalog |
| Backfill ×2 | lần 1 xử lý hết, lần 2 full-skip; 0 URL Pexels |
| Download free/premium | presigned ≤5' / 402 |
| Audit | đủ action, sạch secret |

# LiveCanvas Backend

Backend cho app hình nền động **LiveCanvas** — Django + Django REST Framework.
Cung cấp API public (wallpaper / category / tag / collection), API admin (upload
nội dung, quản lý tag/collection) và xác thực IAP tự viết (verify-receipt trực
tiếp với Apple/Google, **không** dùng RevenueCat).

- **Không có hệ thống user/account** — entitlement premium xác định qua
  `transaction_id` của store.
- **2 tầng auth tách biệt tuyệt đối**: `X-App-Key` (app, cho public + IAP) và
  `Authorization: Bearer <jwt>` (admin, cho `/admin/*`).
- App mobile nằm ở repo riêng (`livecanvas-mobile`), độc lập hoàn toàn — chỉ đồng
  bộ qua contract (`contracts/openapi.yaml` + `.claude/api-context.md`).

> **Nguyên tắc dự án**: xem [`.specify/memory/constitution.md`](.specify/memory/constitution.md).
> Kế hoạch spec: [`.claude/sdd-roadmap.md`](.claude/sdd-roadmap.md).
> Trạng thái hiện tại: [`.claude/project-context.md`](.claude/project-context.md).

---

## ⚠️ Trạng thái hiện tại

Đã ship: **BE-001** (bootstrap 2-flavor) · **BE-002** (DRF foundation, X-App-Key,
error envelope) · **BE-003** (public content API + seed 397 wallpaper thật) ·
**BE-004** (admin JWT tier, storage 2 vùng MinIO/R2, pipeline Celery+ffmpeg,
admin CRUD + audit log, bulk backfill, download-url presigned thật).
Kế tiếp: **BE-005** (IAP verify & entitlement).

---

## Yêu cầu môi trường

- **Python** 3.11+
- **PostgreSQL** 14+ — `docker compose up -d db`
- **Redis** (broker Celery) — `docker compose up -d redis` (host port **6380**)
- **MinIO** (storage 2 vùng cho dev) — `docker compose up -d minio` (bucket tự tạo qua `minio-init`; console http://localhost:9001)
- **ffmpeg** + **libmagic** (transcode + MIME sniffing): `brew install ffmpeg libmagic` (macOS) / `apt install ffmpeg libmagic1` (Linux). Watermark chữ trên preview cần build ffmpeg có **libfreetype** (bản brew đầy đủ); build thiếu sẽ tự fallback sang dải mờ `drawbox`. ClamAV: hoãn tới BE-006.
- Tài khoản S3-compatible + CDN (chỉ cần cho `prod` — Cloudflare R2; `dev` dùng MinIO local)

---

## Flavor: chỉ có `dev` và `prod`

Toàn repo **chỉ có đúng 2 flavor**, không có `staging` hay bất kỳ flavor nào khác:

| Flavor | Settings module        | Env file    | Đặc điểm |
|--------|------------------------|-------------|----------|
| `dev`  | `config.settings.dev`  | `.env.dev`  | `DEBUG=True`, DB local, log verbose, CORS mở |
| `prod` | `config.settings.prod` | `.env.prod` | `DEBUG=False`, `ALLOWED_HOSTS` chặt, security headers, S3+CDN thật |

Flavor được chọn qua biến môi trường `DJANGO_SETTINGS_MODULE`. `manage.py` mặc
định là `dev`.

---

## Setup

```bash
# 1. Clone
git clone git@github.com:Xbisme/backend_live_canvas.git
cd backend_live_canvas

# 2. Virtualenv
python -m venv .venv
source .venv/bin/activate            # Windows: .venv\Scripts\activate

# 3. Cài dependencies theo flavor
pip install -r requirements/dev.txt   # dev
# pip install -r requirements/prod.txt # prod

# 4. Tạo env file từ template (KHÔNG commit file .env thật)
cp .env.dev.example .env.dev
# sửa .env.dev: DATABASE_URL, X_APP_KEY, SECRET_KEY, S3/CDN, ...

# 5. Migrate DB
python manage.py migrate

# 6. Chạy
python manage.py runserver
```

> Secrets đọc từ `.env.dev` / `.env.prod` qua `django-environ`. Chỉ commit các
> file `.env.*.example`; `.env.dev` và `.env.prod` đã được `.gitignore` chặn.

---

## Run

### Dev

```bash
# manage.py mặc định dev — không cần set gì thêm
python manage.py runserver
```

### Prod

```bash
export DJANGO_SETTINGS_MODULE=config.settings.prod
# đảm bảo .env.prod đã cấu hình đầy đủ
python manage.py migrate
python manage.py collectstatic --noinput
gunicorn config.wsgi:application            # ví dụ WSGI server
```

### Celery worker (pipeline upload — BE-004)

```bash
celery -A config worker -l info     # cùng codebase với API; broker theo CELERY_BROKER_URL
```

### Nội dung & vận hành (BE-004)

```bash
python manage.py seed_content        # nạp catalog 397 wallpaper từ fixture
python manage.py backfill_media      # upload dataset local → storage + chạy pipeline (idempotent, resumable)
python manage.py purge_stale_uploads # liệt kê slot upload mồ côi >24h (--delete để xóa)
```

---

## Kiểm thử & chất lượng mã

```bash
ruff check . && ruff format --check .   # lint + format (zero warnings)
pytest                                  # chạy test
python manage.py makemigrations --check --dry-run   # phát hiện schema drift
```

Chi tiết các cổng chất lượng bắt buộc: xem mục *Development Workflow* trong
[constitution](.specify/memory/constitution.md).

---

## Cấu trúc dự án (mục tiêu sau BE-001/BE-002)

```
config/                  # Django project
├── settings/
│   ├── base.py          # cấu hình chung
│   ├── dev.py           # flavor dev
│   └── prod.py          # flavor prod  (KHÔNG có staging.py)
├── celery.py
├── wsgi.py
└── asgi.py

apps/
├── wallpapers/          # Category, Tag, Wallpaper, Collection + public API
├── uploads/             # admin upload, presign, transcode pipeline
└── iap/                 # verify-receipt, webhook Apple/Google, entitlement

requirements/
├── base.txt
├── dev.txt              # -r base.txt
└── prod.txt             # -r base.txt

contracts/openapi.yaml   # API contract — đồng bộ tay với repo mobile
specs/                   # output speckit theo từng spec BE-NNN
manage.py
```

---

## Contract Sync (quan trọng)

API là **contract-first**. Mọi thay đổi API phải theo thứ tự:

1. Cập nhật `docs/screen-inventory.md` (màn hình cần gì) **trước tiên**.
2. Sửa `contracts/openapi.yaml` **và** `.claude/api-context.md` cùng lúc, bump
   `version`.
3. Copy nguyên văn 2 file sang repo `livecanvas-mobile`.
4. Mới implement code server theo contract đã chốt.

---

## Quy trình phát triển (speckit SDD)

```
/speckit.specify → /speckit.clarify → /speckit.plan → /speckit.tasks → /speckit.implement
```

Branch: `BE-NNN-feature-name` · folder `specs/BE-NNN-feature-name/`.

**Communication**: Tiếng Việt giữa người dùng và Claude · Tiếng Anh cho
code / comment / commit message.

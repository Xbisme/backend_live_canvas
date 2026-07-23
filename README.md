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

Repo đang ở giai đoạn **bootstrap** — mới có tài liệu (contract, roadmap,
constitution) và scaffolding speckit. **Chưa có mã Django** (`manage.py`,
`config/`, `apps/` chưa tồn tại).

Phần **Setup & Run** dưới đây mô tả quy trình **sẽ có hiệu lực sau khi hoàn thành
spec `BE-001` (Project Bootstrap & 2-Flavor Setup)**. Trước khi BE-001 merge, các
lệnh `python manage.py …` chưa chạy được.

---

## Yêu cầu môi trường

- **Python** 3.11+
- **PostgreSQL** 14+ (khuyến nghị; `dev` có thể dùng SQLite tuỳ chọn)
- **Redis** (cho Celery — dùng ở pipeline upload, BE-004 trở đi)
- **ffmpeg** và **ClamAV** (transcode + malware scan; chỉ cần khi chạy pipeline)
- Tài khoản S3-compatible + CDN (chỉ cần cho `prod`; `dev` có thể dùng MinIO local)

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

### Celery worker (pipeline upload — BE-004+)

```bash
# dev
celery -A config worker -l info
# (nếu cần) beat cho task định kỳ
celery -A config beat -l info
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

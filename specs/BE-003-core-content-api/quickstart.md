# Quickstart & Validation: Core Content API (BE-003)

> Hướng dẫn chạy + kịch bản kiểm chứng end-to-end chứng minh feature hoạt động. Chi tiết schema xem
> [data-model.md](data-model.md); hành vi endpoint xem [contracts/endpoints.md](contracts/endpoints.md).
> Không chứa code hiện thực — phần đó thuộc `tasks.md` + giai đoạn implement.

## Prerequisites

```bash
uv venv && uv pip sync requirements/dev.txt
cp .env.dev.example .env.dev            # đảm bảo X_APP_KEY có giá trị dev
docker compose up -d db
python manage.py migrate                # gồm 0001_initial của apps.wallpapers
python manage.py seed_content           # nạp fixture nội dung cố định (FR-016)
python manage.py runserver              # dev flavor (mặc định)
```

`X-App-Key` dev = giá trị `X_APP_KEY` trong `.env.dev`. Dưới đây đặt `KEY="$(grep X_APP_KEY .env.dev | cut -d= -f2)"`.

## Smoke test thủ công (curl)

```bash
BASE=http://127.0.0.1:8000
KEY=<giá trị X_APP_KEY dev>

# 1. Curated lists — không phân trang
curl -s $BASE/categories   -H "X-App-Key: $KEY"     # → 200 array + wallpaper_count
curl -s $BASE/tags         -H "X-App-Key: $KEY"     # → 200; [0] là thẻ ảo {id:0,slug:"all",...}
curl -s $BASE/collections  -H "X-App-Key: $KEY"     # → 200 array meta (không items)

# 2. Auth thất bại
curl -s -o /dev/null -w '%{http_code}\n' $BASE/categories                     # → 401 (thiếu key)
curl -s $BASE/categories -H "X-App-Key: wrong"                                # → {"error":{"code":"INVALID_APP_KEY",...}}

# 3. Collection detail — items đúng thứ tự position
curl -s $BASE/collections/1 -H "X-App-Key: $KEY"    # → 200, có "items":[...] đúng thứ tự curate

# 4. Wallpapers — cursor + filter
curl -s "$BASE/wallpapers?limit=2" -H "X-App-Key: $KEY"                       # → {items,next_cursor,has_more}
curl -s "$BASE/wallpapers?tags=neon,city" -H "X-App-Key: $KEY"                # → chỉ wallpaper có CẢ 2 tag
curl -s "$BASE/wallpapers?tags=all" -H "X-App-Key: $KEY"                      # → toàn bộ (slug "all" bị bỏ qua)
curl -s "$BASE/wallpapers?category=urban&orientation=portrait&is_premium=false" -H "X-App-Key: $KEY"
curl -s "$BASE/wallpapers?search=neon" -H "X-App-Key: $KEY"                   # → title khớp
curl -s "$BASE/wallpapers?limit=999" -H "X-App-Key: $KEY"                     # → 400 VALIDATION_ERROR
curl -s "$BASE/wallpapers?cursor=@@bad@@" -H "X-App-Key: $KEY"                # → 400 VALIDATION_ERROR

# 5. Detail + batch
curl -s $BASE/wallpapers/1 -H "X-App-Key: $KEY"                               # → collections[] populate
curl -s $BASE/wallpapers/999999 -H "X-App-Key: $KEY"                          # → 404 NOT_FOUND
curl -s -X POST $BASE/wallpapers/batch -H "X-App-Key: $KEY" -H 'Content-Type: application/json' \
     -d '{"ids":[1,999999]}'                                                  # → chỉ trả id 1

# 6. download-url tạm
curl -s $BASE/wallpapers/<id_non_premium>/download-url -H "X-App-Key: $KEY"   # → 200 {download_url,expires_at}
curl -s $BASE/wallpapers/<id_premium>/download-url    -H "X-App-Key: $KEY"    # → 402 ENTITLEMENT_REQUIRED
```

## Kiểm chứng tự động (bắt buộc trước commit)

```bash
ruff check . && ruff format --check .
pytest apps/wallpapers
python manage.py makemigrations --check --dry-run   # không có schema drift
```

### Ánh xạ test ↔ user story / bất biến

| Test file | Bao phủ | User story / invariant |
|---|---|---|
| `test_categories_tags.py` | list + count published + 401 + 405; **thẻ ảo "All" [0]** + slug `all` bị strip trong filter | US1; FR-005, FR-006, FR-006a, FR-014 |
| `test_collections.py` | list meta; detail `items` đúng thứ tự; premium vẫn trả; 404 | US4; SC-006, invariant 2 |
| `test_wallpapers_list.py` | cursor (gồm invalid → 400), tags AND, filter combo, search, ổn định khi chèn | US1; SC-002/003, invariant 4,5 |
| `test_wallpaper_detail.py` | detail populate collections; 404; ẩn không rò rỉ | US2; FR-010/013, SC-005 |
| `test_wallpaper_batch.py` | batch bỏ qua id thiếu; ≤100 → 400; ẩn không trả | US3; FR-011/013, SC-005 |
| `test_download_url.py` | non-premium 200 shape; premium 402; không tồn tại 404 | US5; FR-012, invariant 6 |
| `test_seed_command.py` | seed idempotent; chạy 2 lần không nhân bản; source_url/license_type set | FR-016 |

## Định nghĩa "Done" cho feature

- [ ] 8 endpoint trả đúng shape contract v0.3.2 (test hợp đồng xanh).
- [ ] Nội dung `status!=published` / `deleted_at!=null` không rò rỉ ở bất kỳ endpoint public nào.
- [ ] `GET /collections/{id}.items` đúng thứ tự `position`.
- [ ] Cursor pagination ổn định (không trùng/nhảy) khi chèn bản ghi mới.
- [ ] `seed_content` idempotent, mobile dùng được data thật (điểm đồng bộ MO-002).
- [ ] Probe tạm `_probe/*` của BE-002 đã gỡ.
- [ ] `ruff`, `pytest`, `makemigrations --check` đều sạch.
- [ ] Không mở endpoint tầng admin nào (Constitution II).
```

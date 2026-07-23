# Screen Inventory — LiveCanvas

> **Vai trò**: Đây là bước làm TRƯỚC khi chốt API — liệt kê màn hình/luồng chính, data mỗi màn cần, action mỗi màn có. `contracts/openapi.yaml` và `.claude/api-context.md` được suy ra từ file này, không phải ngược lại. Khi thêm/sửa 1 màn hình → sửa file này trước → rồi mới sửa contract.
>
> File này tồn tại độc lập ở CẢ 2 REPO (đồng bộ tay giống `api-context.md`).
>
> Last updated: 2026-07-23 · Contract version tương ứng: `v0.3.2`

---

## Danh sách màn hình

| # | Màn hình | Data cần | Action | Endpoint liên quan |
|---|---|---|---|---|
| 1 | **Browse** (trang chủ, grid theo category) | Thumbnail, title, category, tags, is_premium, orientation — cuộn vô hạn | Scroll load thêm (cursor), tap → Detail, đổi category | `GET /wallpapers` |
| 2 | **Category Detail** (list theo 1 category) | Giống Browse, filter cố định 1 category | Scroll load thêm, filter phụ orientation/tag | `GET /wallpapers?category=...` |
| 3 | **Search** | Giống Browse, filter theo từ khóa + tag chọn thêm | Scroll load thêm, chọn tag gợi ý | `GET /wallpapers?search=...&tags=...`, `GET /tags` |
| 4 | **Tag Filter Chips** (dùng ở Browse/Search) | Danh sách tag có sẵn (curated), **có chip "All" (Tất cả) đứng đầu, chọn mặc định** | Chọn "All" = bỏ mọi filter tag (lấy toàn bộ, mới→cũ); chọn/bỏ chọn tag khác | `GET /tags` |
| 5 | **Collections** (tab "Bộ sưu tập", list cover card) | Mỗi collection: cover_url, title, author, wallpaper_count, is_premium — danh sách nhỏ curated | Tap → Collection Detail | `GET /collections` |
| 6 | **Collection Detail** (1 bộ sưu tập curated) | Meta collection (cover_url, accent_color, title, author, description, is_premium, wallpaper_count) + **danh sách wallpaper thuộc bộ** (đúng thứ tự curate) | Tap wallpaper → Detail, Favorite toggle, "Tải tất cả", "Mở khoá bộ sưu tập" nếu premium & chưa mua | `GET /collections/{id}` |
| 7 | **Wallpaper Detail** | Full info + preview_video_url, license info, danh sách tag đầy đủ, **(các) bộ sưu tập chứa wallpaper này** (để nhảy tới Collection Detail) | Play preview, Favorite toggle, Tải/Set (trigger download-url), Mua nếu premium, tap "Từ bộ sưu tập ·…" → Collection Detail | `GET /wallpapers/{id}`, `GET /wallpapers/{id}/download-url` |
| 8 | **Favorites** | List wallpaper đã lưu local (theo ID) — cần fetch lại data mới nhất mỗi lần mở | Bỏ favorite, tap → Detail | `POST /wallpapers/batch` |
| 9 | **Paywall/Premium** | Danh sách gói (giá lấy từ Store, KHÔNG từ backend) | Mua, Restore purchase, gửi receipt verify | `POST /iap/verify-receipt` |
| 10 | **Set Wallpaper Confirm** (Android) / **Hướng dẫn Shortcuts** (iOS) | Không cần thêm API — dùng `download_url` đã có từ Detail | Native action | — |
| 11 | **Admin: Upload Wallpaper** | Danh sách category + tag có sẵn để chọn | Chọn file, chọn category, chọn tag (curated — không gõ tự do), submit | `GET /admin/tags` hoặc `GET /tags`, `POST /admin/uploads/presign`, `POST /admin/wallpapers` |
| 12 | **Admin: Quản lý Tag** | Danh sách tag + số wallpaper đang dùng mỗi tag | Tạo tag mới, xóa tag không dùng | `GET /admin/tags`, `POST /admin/tags`, `DELETE /admin/tags/{id}` |
| 13 | **Admin: Quản lý Bộ sưu tập** | Danh sách collection + wallpaper thuộc mỗi bộ (curated) | Tạo/sửa collection (title, cover, author, description, is_premium), thêm/bớt/sắp xếp wallpaper, xóa | `GET/POST/PATCH/DELETE /admin/collections`, `POST /admin/uploads/presign` (cover) |

## Quyết định đã chốt (ảnh hưởng trực tiếp tới response schema)

- **Pagination**: cursor-based (keyset) cho mọi endpoint list wallpaper — không dùng `page`/`page_size` kiểu offset. Lý do: tránh lệch trang khi admin thêm/xóa liên tục, và ổn định hơn cho UI cuộn vô hạn.
- **Favorites**: không cache toàn bộ data lúc favorite — chỉ lưu local mảng ID, mỗi lần mở màn Favorites gọi `POST /wallpapers/batch` để lấy data mới nhất (tránh hiển thị data cũ nếu wallpaper đã bị admin sửa/xóa).
- **Tag**: curated — admin chỉ chọn từ tag có sẵn khi upload, tạo tag mới phải qua màn hình quản lý tag riêng (#12). Giúp tránh tag rác, search/filter chính xác theo `tag_id` thay vì so khớp chuỗi.
  - **Chip "All" (Tất cả)**: là **tag ảo do API sinh**, KHÔNG lưu trong DB và KHÔNG gắn vào từng wallpaper. `GET /tags` chèn phần tử `{ id: 0, slug: "all", name: "Tất cả", wallpaper_count: <tổng wallpaper published> }` ở **đầu** mảng để client render chip mặc định. Chọn "All" = gọi `GET /wallpapers` **không** truyền `tags` (đã sẵn trả toàn bộ, sắp xếp mới→cũ). Slug `all` là **reserved**: `GET /wallpapers?tags=` bỏ qua slug `all` (coi như không ràng buộc tag) và admin/seed KHÔNG được tạo tag thật slug `all`. Lý do làm tag ảo thay vì tag DB: tránh phải gắn tag vào mọi wallpaper, tránh lệch `wallpaper_count`, giữ curated integrity.
- **Collection (Bộ sưu tập)**: curated bởi admin, giống Category/Tag nhưng là **tập hợp wallpaper có thứ tự** kèm cover/author/description riêng.
  - Quan hệ **many-to-many có thứ tự** giữa `Collection` ↔ `Wallpaper` (1 wallpaper có thể nằm trong nhiều bộ; thứ tự trong bộ do admin quyết).
  - `GET /collections` **KHÔNG phân trang** (curated, số lượng nhỏ như categories/tags) — chỉ trả meta + `wallpaper_count`, không nhúng items.
  - `GET /collections/{id}` trả meta + **nhúng thẳng `items: Wallpaper[]`** đúng thứ tự curate, **KHÔNG phân trang** (tập bounded, soft-cap ≤100 wallpaper/bộ). Lý do: màn Collection Detail render cả grid 1 lần, không cần cursor.
  - **"Tải tất cả"**: không có endpoint riêng — client lặp gọi `GET /wallpapers/{id}/download-url` cho từng item. **Entitlement vẫn quyết duy nhất ở `download-url`** (kể cả bộ premium): cover/detail chỉ hiển thị nút "Mở khoá" theo `collection.is_premium`, gate thật vẫn ở download-url từng file.
  - `Wallpaper` thêm field `collections: CollectionRef[]` (mini: id/slug/title/cover_url/is_premium) để Detail nhảy vào bộ. Chỉ đảm bảo populate ở `GET /wallpapers/{id}`; ở list lớn có thể rỗng để tiết kiệm payload (client Detail luôn có dữ liệu cần).

## Giả định chưa xác nhận (cần bạn confirm trước khi implement)

- **Onboarding/Splash**: giả định KHÔNG cần data riêng từ backend — mở thẳng vào Browse (trang 1, category mặc định = tất cả). Nếu sau này cần mục "Nổi bật/Trending" riêng, sẽ cần thêm field `is_featured` hoặc endpoint riêng — báo mình khi cần.

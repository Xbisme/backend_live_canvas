# Screen Inventory — LiveCanvas

> **Vai trò**: Đây là bước làm TRƯỚC khi chốt API — liệt kê màn hình/luồng chính, data mỗi màn cần, action mỗi màn có. `contracts/openapi.yaml` và `.claude/api-context.md` được suy ra từ file này, không phải ngược lại. Khi thêm/sửa 1 màn hình → sửa file này trước → rồi mới sửa contract.
>
> File này tồn tại độc lập ở CẢ 2 REPO (đồng bộ tay giống `api-context.md`).
>
> Last updated: 2026-07-29 · Contract version tương ứng: `v0.7.0`
>
> **v0.7.0 (BE-008)**: màn #1 **Browse** đổi từ lưới cursor phẳng sang **section curated có tiêu đề** — admin bật collection lên home + đặt thứ tự, app lấy cả màn bằng 1 lần gọi `GET /home` (tối đa 10 section × 10 wallpaper, không phân trang). `Wallpaper.description` (khai từ v0.6.0) **nay backend implement thật**, và admin sửa được mô tả của wallpaper đã tồn tại qua `PATCH /admin/wallpapers/{id}`.
>
> **v0.6.0 (mobile-driven)**: màn #7 Wallpaper Detail cần thêm **`description`** (mô tả ngắn của wallpaper) cho mục "Mô tả" + mục **"Hình nền liên quan"** (suy theo tag đầu tiên, không endpoint riêng). `description` là field MỚI trên `Wallpaper` — backend implement ở BE-008 (v0.7.0).

---

## Danh sách màn hình

| # | Màn hình | Data cần | Action | Endpoint liên quan |
|---|---|---|---|---|
| 1 | **Browse** (trang chủ) | **Các section curated có tiêu đề (v0.7.0)**: mỗi section = 1 collection admin bật lên home, có title/cover/accent_color/is_premium + ≤10 wallpaper theo đúng thứ tự curate; tối đa 10 section, sắp theo thứ tự admin đặt. Khi lọc theo tag thì quay về lưới phẳng cuộn vô hạn (thumbnail, title, category, tags, is_premium, orientation) | Tap wallpaper → Detail, "Xem tất cả" 1 section → Collection Detail, chọn tag → lưới phẳng (scroll load thêm bằng cursor) | `GET /home` (section), `GET /wallpapers` (lưới phẳng khi lọc tag) |
| 2 | **Category Detail** (list theo 1 category) | Giống Browse, filter cố định 1 category | Scroll load thêm, filter phụ orientation/tag | `GET /wallpapers?category=...` |
| 3 | **Search** | Giống Browse, filter theo từ khóa + tag chọn thêm | Scroll load thêm, chọn tag gợi ý | `GET /wallpapers?search=...&tags=...`, `GET /tags` |
| 4 | **Tag Filter Chips** (dùng ở Browse/Search) | Danh sách tag có sẵn (curated), **có chip "All" (Tất cả) đứng đầu, chọn mặc định** | Chọn "All" = bỏ mọi filter tag (lấy toàn bộ, mới→cũ); chọn/bỏ chọn tag khác | `GET /tags` |
| 5 | **Collections** (tab "Bộ sưu tập", list cover card) | Mỗi collection: cover_url, title, author, wallpaper_count, is_premium — danh sách nhỏ curated | Tap → Collection Detail | `GET /collections` |
| 6 | **Collection Detail** (1 bộ sưu tập curated) | Meta collection (cover_url, accent_color, title, author, description, is_premium, wallpaper_count) + **danh sách wallpaper thuộc bộ** (đúng thứ tự curate) | Tap wallpaper → Detail, Favorite toggle, "Tải tất cả", "Mở khoá bộ sưu tập" nếu premium & chưa mua | `GET /collections/{id}` |
| 7 | **Wallpaper Detail** | Full info + preview_video_url, **`description` (mô tả — v0.6.0, backend chưa có)**, license info, danh sách tag đầy đủ, stats (download_count/like_count/resolution), **(các) bộ sưu tập chứa wallpaper này** (để nhảy tới Collection Detail) + **hình nền liên quan** (suy theo tag đầu tiên) | Play preview, Favorite toggle, Tải/Set (trigger download-url), Mua nếu premium, tap "Từ bộ sưu tập ·…" → Collection Detail, tap hình liên quan → Detail khác | `GET /wallpapers/{id}`, `GET /wallpapers/{id}/download-url`, `GET /wallpapers?tags=<tag>` (liên quan) |
| 8 | **Favorites** | List wallpaper đã lưu local (theo ID) — cần fetch lại data mới nhất mỗi lần mở | Bỏ favorite, tap → Detail | `POST /wallpapers/batch` |
| 9 | **Paywall/Premium** | Danh sách gói (giá lấy từ Store, KHÔNG từ backend) + trạng thái subscription hiện tại (nếu đã có `transaction_id` lưu local) | Mua, Restore purchase, gửi receipt verify, kiểm tra lại trạng thái khi mở màn | `POST /iap/verify-receipt`, `GET /iap/subscription-status` |
| 10 | **Set Wallpaper Confirm** (Android) / **Hướng dẫn Shortcuts** (iOS) | Không cần thêm API — dùng `download_url` đã có từ Detail | Native action | — |
| 11 | **Admin: Upload Wallpaper** | Danh sách category + tag có sẵn để chọn | Chọn file, chọn category, chọn tag (curated — không gõ tự do), **nhập mô tả (optional, v0.7.0)**, submit; **sửa/xoá mô tả của wallpaper đã tồn tại (v0.7.0)** | `GET /admin/tags` hoặc `GET /tags`, `POST /admin/uploads/presign`, `POST /admin/wallpapers`, `PATCH /admin/wallpapers/{id}` |
| 12 | **Admin: Quản lý Tag** | Danh sách tag + số wallpaper đang dùng mỗi tag | Tạo tag mới, xóa tag không dùng | `GET /admin/tags`, `POST /admin/tags`, `DELETE /admin/tags/{id}` |
| 13 | **Admin: Quản lý Bộ sưu tập** | Danh sách collection + wallpaper thuộc mỗi bộ (curated) | Tạo/sửa collection (title, cover, author, description, is_premium), thêm/bớt/sắp xếp wallpaper, xóa, **bật/tắt hiện trên Browse + đặt thứ tự section (v0.7.0)** | `GET/POST/PATCH/DELETE /admin/collections`, `POST /admin/uploads/presign` (cover) |
| 14 | **Admin: Đăng nhập** (admin tooling — không phải màn hình app end-user) | Form username/password của staff account; phiên làm việc cần token ngắn hạn tự gia hạn | Đăng nhập → nhận access (30') + refresh (7 ngày, rotate); mọi màn admin #11–13 gắn `Authorization: Bearer <access>`; hết hạn → refresh tự động, refresh hết hạn → đăng nhập lại | `POST /admin/auth/login`, `POST /admin/auth/refresh` |

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

- **Browse sections (v0.7.0)**: màn #1 render các **section curated có tiêu đề**. Section **KHÔNG phải resource mới** — nó là `Collection` đã có, được admin bật `show_on_home` + đặt `home_position`; mọi thứ section cần (title, cover_url, accent_color, is_premium, danh sách wallpaper có thứ tự) collection đã mang sẵn.
  - `GET /home` trả **cả màn trong 1 lần gọi**, KHÔNG phân trang, bounded cứng **≤10 section × ≤10 wallpaper/section** — trần áp **lúc đọc**: admin bật dư thì phần dư bị bỏ qua im lặng (không lỗi, không chặn thao tác admin).
  - Section sắp theo `home_position` tăng dần; trùng vị trí thì thứ tự vẫn **ổn định giữa các request** (tie-break theo id).
  - Chỉ chứa wallpaper published; section không còn wallpaper nào hiển thị được thì **bị bỏ hẳn và KHÔNG chiếm slot** (section kế tiếp lấp vào). Chưa bật collection nào → `sections: []` + 200, không phải 404.
  - "Xem tất cả" của 1 section = dùng `collection_id` gọi `GET /collections/{id}` đã có — không có phân trang bên trong section.
  - Section premium **chỉ hiển thị badge**; entitlement vẫn quyết duy nhất ở `download-url` (không đổi).
  - `show_on_home`/`home_position` là **input của admin**, KHÔNG xuất hiện trong payload công khai `GET /collections`.
- **Mô tả wallpaper (v0.7.0)**: `Wallpaper.description` nay có thật (nullable). Đặt lúc đăng ký qua `POST /admin/wallpapers`, sửa/xoá sau qua `PATCH /admin/wallpapers/{id}` (**chỉ sửa được mô tả**, không đụng media/status/tag/category/collection). Chuỗi rỗng hoặc toàn khoảng trắng → lưu `null`, để client ẩn mục "Mô tả" chỉ bằng phép kiểm tra null.
- **Admin auth (v0.4.0)**: các màn admin #11–13 xác thực bằng **Bearer JWT** (access 30 phút / refresh 7 ngày rotate) đổi từ credential staff qua `POST /admin/auth/login` — tách tuyệt đối khỏi `X-App-Key` của app end-user. Backend không thêm hệ thống user mới: tài khoản admin là Django staff user sẵn có.
- **Download thật (v0.4.0)**: `GET /wallpapers/{id}/download-url` từ v0.4.0 trả **presigned URL thật** (hết hạn ≤5 phút) cho wallpaper free thay vì mock. Lưu ý client: domain của `download_url` (S3/R2 endpoint) **khác** domain thumbnail/preview (CDN) — không hardcode/so sánh domain.
- **Entitlement thật (v0.5.0)**: gate premium ở `download-url` đã hết vô điều kiện — client gửi `transaction_id` (query) và backend tra entitlement thật.
  - **Client cần lưu bền `transaction_id`** (đã verify thành công) ở local, và gửi kèm ở **mọi** `GET /wallpapers/{id}/download-url` của wallpaper premium (kể cả từng item trong "Tải tất cả" ở bộ premium). Free thì bỏ qua field này.
  - Entitlement định danh theo **original transaction id** của store → mọi `transaction_id` trong chuỗi renewal đều tra ra đúng 1 entitlement; client KHÔNG cần cập nhật id đã lưu sau mỗi kỳ gia hạn.
  - **Còn quyền tải** khi `status ∈ {active, in_grace_period}` và chưa quá `expires_at`. `in_grace_period` (store đang retry thu tiền) vẫn tải được — client KHÔNG tự chặn. Tắt auto-renew mà còn trong kỳ → `status=active` + `auto_renew=false`, vẫn tải được (đừng coi là mất quyền).
  - `402 ENTITLEMENT_REQUIRED` = chưa/không còn entitlement → điều hướng Paywall (#9). `404 NOT_FOUND` được đánh giá **trước** gate entitlement, nên 404 nghĩa là wallpaper không khả dụng chứ không phải thiếu quyền.
  - **Restore trên máy mới**: chỉ cần verify lại receipt từ store → nhận lại `transaction_id`; `device_id` backend chỉ ghi nhận để phát hiện lạm dụng, KHÔNG chặn máy mới.
  - Màn Paywall dùng `GET /iap/subscription-status?transaction_id=...` để hiển thị/refresh trạng thái (read-only, không gia hạn gì).

## Giả định chưa xác nhận (cần bạn confirm trước khi implement)

- **Onboarding/Splash**: giả định KHÔNG cần data riêng từ backend — mở thẳng vào Browse (trang 1, category mặc định = tất cả). Nếu sau này cần mục "Nổi bật/Trending" riêng, sẽ cần thêm field `is_featured` hoặc endpoint riêng — báo mình khi cần.

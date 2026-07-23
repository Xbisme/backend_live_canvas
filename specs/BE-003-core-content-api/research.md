# Phase 0 Research: Core Content API

> Mọi mục "NEEDS CLARIFICATION" ở tầng nghiệp vụ đã chốt trong spec (fixture seed; hoãn `/admin/tags`;
> download-url tạm). Phần dưới là các **quyết định kỹ thuật** phát sinh khi lập kế hoạch, mỗi mục
> theo format Decision / Rationale / Alternatives.

## R1 — Cursor pagination ổn định với `created_at` không duy nhất

**Decision**: `GET /wallpapers` order theo tuple `("-created_at", "-id")` qua một subclass mỏng của
`EnvelopeCursorPagination` (override `ordering`). Thêm DB index `(-created_at, -id)` (hoặc
`(created_at, id)`) trên `Wallpaper`.

**Rationale**: `EnvelopeCursorPagination` (BE-002) mặc định `ordering = "-created_at"`. Nếu nhiều
wallpaper trùng `created_at`, keyset cursor một-cột có thể lặp/nhảy item khi chèn bản ghi mới —
vi phạm SC-002 & Constitution VI. DRF `CursorPagination` hỗ trợ tuple ordering và tự thêm `id` làm
tiebreaker ổn định. Index khớp thứ tự giữ truy vấn index-friendly.

**⚠️ Invalid cursor MUST → 400 `VALIDATION_ERROR` (Constitution VI, FR-008)**: DRF
`CursorPagination.paginate_queryset` raise `rest_framework.exceptions.NotFound` khi cursor hỏng/hết
hạn → mặc định ra **404**, và exception_handler (BE-002) map 404→`NOT_FOUND`. Điều này **vi phạm**
yêu cầu 400. Cách xử lý: subclass override để bắt cursor lỗi và raise lỗi 400 `VALIDATION_ERROR`
(vd override `decode_cursor`, hoặc bọc `paginate_queryset` chuyển `NotFound` → `ValidationError`/
`AppError` với code `VALIDATION_ERROR`). Bắt buộc có test invalid cursor → 400 (T012).

**Alternatives**:
- Chỉ `-created_at`: đơn giản nhưng không ổn định khi trùng timestamp (bị loại).
- Order theo `-id` thuần: ổn định nhưng thứ tự hiển thị không phản ánh "mới nhất trước" mượt khi
  seed nhiều bản ghi cùng lúc; kém trực giác cho client (bị loại — dùng tuple là đủ và đúng hơn).

## R2 — Lọc & tìm kiếm không thêm dependency

**Decision**: Hiện thực filter/search bằng ORM trực tiếp trong một hàm service
(`build_wallpaper_queryset`), **không** dùng `django-filter`. Search = `title__icontains`.
`tags` (nhiều slug, AND) = chuỗi `.filter(tags__slug=...)` lặp cho từng slug (mỗi lần thu hẹp),
đảm bảo ngữ nghĩa AND thực sự.

**Rationale**: Constitution XI ưu tiên "boring composition", chỉ thêm abstraction/dep khi thật cần.
Bộ filter ở đây nhỏ và cố định (category slug, tags-AND, orientation, is_premium, search) — vài dòng
ORM rõ ràng hơn và ít bề mặt phụ thuộc hơn một thư viện filter. AND cho M2M **phải** dùng nhiều
`.filter()` nối tiếp; một `.filter(tags__slug__in=[...])` sẽ ra OR (sai) → tài liệu hoá rõ trong service.

**Alternatives**:
- `django-filter`: tiện cho filter lớn/động, nhưng thêm dep + phải lookup PyPI + cấu hình backend; thừa
  cho nhu cầu tĩnh này (bị loại).
- Postgres full-text search (`SearchVector`): mạnh hơn cho tìm kiếm ngôn ngữ tự nhiên nhưng SC-003 chỉ
  yêu cầu khớp tiêu đề; để dành nếu sau này cần (không cho BE-003).

## R3 — Publish status & soft-delete, ẩn nội dung khỏi public

**Decision**: `Wallpaper` mang `status` (`processing` | `published` | `failed`, mặc định `published`
cho bản ghi seed/BE-003) và soft-delete qua `deleted_at: datetime|null`. Một custom manager/queryset
`published()` = `status="published", deleted_at__isnull=True`; **mọi** view public + batch +
collection items dùng nó. `wallpaper_count` annotate chỉ đếm tập `published()`.

**Rationale**: FR-013 & SC-005 cấm rò rỉ nội dung chưa publish/đã xoá. Đưa `status` vào ngay (dù
pipeline ở BE-004) để BE-004 chỉ việc chuyển trạng thái, tránh migration phá vỡ sau này (Constitution
IX). Contract admin `GET /admin/wallpapers` đã có filter `status` (processing/published/failed) → field
này là hợp đồng, không phải phát minh thừa. Soft-delete để download/reference degrade mượt (Constitution IX).

**Alternatives**:
- Chỉ boolean `is_published`: không biểu diễn được trạng thái `failed` mà contract admin yêu cầu (bị loại).
- Hard delete: vi phạm khuyến nghị soft-delete của Constitution IX (bị loại).

## R4 — Serializer 2 biến thể cho `Wallpaper.collections`

**Decision**: Hai serializer: `WallpaperListSerializer` (field `collections` trả `[]` — tiết kiệm
payload ở list lớn) và `WallpaperDetailSerializer` (populate `collections` đầy đủ dạng `CollectionRef`).
Batch dùng biến thể detail-lite (có collections) hay list? → dùng **list serializer** (collections rỗng)
cho batch để nhẹ; màn Favorites không cần collections. Detail (`GET /wallpapers/{id}`) dùng detail
serializer.

**Rationale**: Contract (api-context §GET /wallpapers/{id}) nói rõ `collections` "được đảm bảo populate
ở detail", "ở list lớn có thể rỗng". Tách 2 serializer là cách trực tiếp nhất và tránh N+1 ở list.

**Alternatives**:
- Một serializer luôn populate collections: N+1 hoặc prefetch nặng ở list lớn, phí payload (bị loại).
- Field động theo query param: phức tạp hoá không cần thiết (bị loại).

## R5 — `wallpaper_count` (Category/Tag/Collection)

**Decision**: Annotate qua `Count` với `filter=Q(...)` giới hạn ở `published()` (published & chưa xoá),
trong service/queryset khi serialize danh sách. Không lưu cột đếm phi chuẩn hoá.

**Rationale**: FR-005 yêu cầu count phản ánh chỉ nội dung published. Annotate lúc đọc luôn đúng, tránh
lệch đồng bộ của counter cache. Các list này bounded (<100) nên chi phí annotate không đáng kể.

**Alternatives**:
- Cột `wallpaper_count` phi chuẩn hoá + cập nhật qua signal: nhanh hơn cực nhỏ nhưng dễ lệch, thêm độ
  phức tạp (bị loại cho quy mô này).

## R6 — download-url tạm (không có storage presign)

**Decision**: `GET /wallpapers/{id}/download-url` trong service `build_download_url`:
- Wallpaper không tồn tại / không `published()` → `Http404` (→ `NOT_FOUND`).
- `is_premium=True` → raise `EntitlementRequired` (mã `ENTITLEMENT_REQUIRED`, 402) — **luôn**, vì chưa
  có hệ thống verify `transaction_id` (đến BE-005).
- `is_premium=False` → trả `{ "download_url": <mock>, "expires_at": <now+5min ISO8601> }`, trong đó
  `download_url` dựng từ `CDN_BASE_URL` + key/nguồn của wallpaper (hoặc chính `source_url` khi thiếu CDN).

**Rationale**: Giữ đúng shape contract để mobile hoàn thiện điều hướng (SC-001) mà **không rò rỉ** file
premium (Constitution III: premium phải gate). Dùng `ENTITLEMENT_REQUIRED` — mã đã có trong catalog —
thay vì tạo mã "NOT_IMPLEMENTED" ngoài hợp đồng. `expires_at ≤ 5 phút` khớp Constitution III.
Cần thêm lớp exception `EntitlementRequired(AppError)` vào `core.errors` (mã đã khai báo sẵn, chỉ thiếu
class) — không đổi contract.

**Alternatives**:
- Trả `501`: không có mã catalog tương ứng, phá nguyên tắc "status khớp code" (bị loại).
- Trả mock URL cho cả premium: rò rỉ nội dung premium, vi phạm Constitution III (bị loại).

## R7 — Nạp nội dung mẫu (fixture cố định)

**Decision**: Một fixture JSON commit trong `apps/wallpapers/fixtures/seed_content.json` (đủ
Category/Tag/Wallpaper/Collection + quan hệ ordered) và management command `seed_content` **idempotent**
(nạp bằng `update_or_create` theo `slug`/natural key, không nhân bản khi chạy lại). Mỗi Wallpaper mang
`source_url` + `license_type` từ nguồn công khai (Pixabay/Pexels/Mixkit).

**Rationale**: FR-016 (đã chốt) — deterministic cho dev/CI/test/mobile, không phụ thuộc mạng/API bên
thứ ba lúc chạy. `update_or_create` giữ tính idempotent (Constitution — an toàn chạy lại). Command tách
khỏi `loaddata` thô để kiểm soát thứ tự M2M `position` và annotate quan hệ.

**Alternatives**:
- `loaddata` thuần với fixture: khó biểu diễn `position` của bảng nối ordered một cách rõ ràng và idempotent
  (bị loại — command tường minh hơn).
- Gọi API nguồn lúc seed: không deterministic, cần API key, hỏng CI (đã loại ở clarification).

## R8 — Dọn probe tạm của BE-002

**Decision**: Gỡ 4 route `_probe/*` và các view `AppTierProbeView/ProbeValidationView/ProbeNotFoundView/
ProbeBoomView` khỏi `core/urls.py` + `core/views.py` (BE-002 đã đánh dấu "removed in BE-003"). Test tương
ứng chuyển thành test thật trên endpoint content, hoặc gỡ nếu đã được cover bởi test mới.

**Rationale**: Comment trong `core/urls.py` ghi rõ các probe này "removed in BE-003". Giờ đã có endpoint
thật để kiểm chứng app-tier auth + envelope lỗi, nên probe hết vai trò. Giữ lại là rác bề mặt (Constitution
XI).

**Alternatives**:
- Giữ probe: bề mặt thừa ngoài contract, dễ gây nhầm (bị loại).

## R9 — Thẻ ảo "All" (Tất cả) ở `GET /tags` (contract v0.3.2)

**Decision**: "All" là **thẻ ảo do API sinh**, không lưu DB. `GET /tags` prepend
`{ id: 0, slug: "all", name: "Tất cả", wallpaper_count: <tổng Wallpaper published> }` vào đầu mảng
(tổng hợp trong serializer/service). `id=0` + `slug="all"` reserved (validate cấm tạo tag thật trùng).
`build_wallpaper_queryset` **strip** slug `all` khỏi tham số `tags` trước khi áp AND. Chọn "All" trên
client = gọi `GET /wallpapers` không truyền `tags` → toàn bộ published, mới→cũ (thứ tự mặc định R1).

**Rationale**: Đây là contract change (v0.3.1→v0.3.2), đã đi đúng thứ tự contract-first
(`screen-inventory.md` → `openapi.yaml` + `api-context.md` → spec/plan). Làm thẻ ảo thay vì record DB
gán vào mọi wallpaper: tránh nghĩa vụ gắn tag cho từng wallpaper mới, tránh `wallpaper_count` trùng
tổng và lệch, giữ **curated integrity** (Constitution IX — Tag là curated, không rác). Backend gần như
không phải làm gì thêm cho hành vi "lấy toàn bộ" vì list mặc định đã trả toàn bộ + sắp xếp mới→cũ.

**Alternatives**:
- Tag thật slug "all" gắn mọi wallpaper: phản mẫu — maintenance + lệch count + bẩn dữ liệu curated (loại).
- Thuần client-side (không đụng contract): sạch nhất nhưng người dùng đã chọn phương án API-sinh để
  mobile không phải hardcode danh sách; đã chốt qua clarification (loại).

## Tổng hợp phụ thuộc

- **Không thêm package mới** → không cần lookup PyPI (Constitution XI thoả mãn hiển nhiên).
- Toàn bộ nền tái sử dụng từ BE-002: `core.api.AppTierAPIView`, `core.pagination.EnvelopeCursorPagination`,
  `core.exception_handler`, `core.errors` (bổ sung 1 class `EntitlementRequired` — mã đã có).

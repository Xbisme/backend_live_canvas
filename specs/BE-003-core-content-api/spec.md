# Feature Specification: Core Content API

**Feature Branch**: `BE-003-core-content-api`

**Created**: 2026-07-23

**Status**: Draft

**Input**: User description: "BE-003 Core Content API — Public content API cho LiveCanvas backend, khớp contract v0.3.2. Chuyển repo mobile từ mock server sang API thật (điểm đồng bộ MO-002)."

## Overview

Đây là lớp API public đầu tiên phục vụ dữ liệu nội dung thật cho ứng dụng LiveCanvas. Nó
biến các bảng nội dung được biên tập (danh mục, thẻ, hình nền, bộ sưu tập) thành các endpoint
đọc mà app di động tiêu thụ để duyệt, lọc, tìm kiếm và xem chi tiết hình nền — thay thế mock
server mà mobile đang dùng (điểm đồng bộ MO-002).

Tất cả endpoint public được xác thực ở **tầng app** bằng `X-App-Key` (không có khái niệm user/
account). Quyền truy cập nội dung premium **không** được quyết ở tầng danh sách/chi tiết mà ở
mép `download-url` từng file — phần entitlement thật hoàn thiện ở BE-005; spec này chỉ dựng
đường đi (edge) đó ở dạng tạm.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Duyệt & khám phá hình nền (Priority: P1)

Người dùng app mở màn Browse và thấy lưới hình nền động thật (thumbnail + preview), cuộn vô
hạn mượt mà theo lô, có thể lọc theo danh mục, thẻ, hướng màn hình (dọc/ngang/vuông), trạng thái
premium, và tìm kiếm theo từ khoá.

**Why this priority**: Đây là giá trị cốt lõi của app và là lý do điểm đồng bộ MO-002 tồn tại —
không có nó thì mobile không thể rời mock server. Là MVP tối thiểu chạy được một mình.

**Independent Test**: Seed vài danh mục + hình nền, gọi `GET /wallpapers` với các tổ hợp filter
và phân trang cursor, xác nhận trả đúng tập, đúng thứ tự, đúng envelope phân trang; và
`GET /categories`, `GET /tags` trả toàn bộ danh sách curated.

**Acceptance Scenarios**:

1. **Given** có 50 hình nền đã publish, **When** app gọi `GET /wallpapers` với `limit=20`,
   **Then** nhận đúng 20 item, `has_more: true`, và một `next_cursor` không rỗng.
2. **Given** có `next_cursor` từ lần gọi trước, **When** app gọi lại `GET /wallpapers?cursor=<next_cursor>`,
   **Then** nhận trang kế tiếp không trùng item nào với trang trước.
3. **Given** hình nền được gắn thẻ `neon` và `city`, **When** app gọi `GET /wallpapers?tags=neon,city`,
   **Then** chỉ trả những hình nền có **cả hai** thẻ (AND).
4. **Given** filter `category=urban&orientation=portrait&is_premium=false`, **When** app gọi
   `GET /wallpapers`, **Then** chỉ trả hình nền khớp đồng thời mọi điều kiện.
5. **Given** từ khoá tìm kiếm khớp tiêu đề, **When** app gọi `GET /wallpapers?search=<kw>`,
   **Then** trả các hình nền có tiêu đề khớp.
5b. **Given** danh sách thẻ chip, **When** app gọi `GET /tags`, **Then** phần tử đầu tiên là thẻ ảo
   "Tất cả" (`id: 0`, `slug: "all"`, `wallpaper_count` = tổng hình nền published), theo sau là các
   thẻ curated thật.
5c. **Given** người dùng chọn chip "All", **When** app gọi `GET /wallpapers` **không** truyền `tags`
   (hoặc `tags=all`), **Then** trả **toàn bộ** hình nền published, sắp xếp **mới→cũ**.
6. **Given** thiếu hoặc sai `X-App-Key`, **When** gọi bất kỳ endpoint public nào,
   **Then** nhận `401` với `error.code = INVALID_APP_KEY`.
7. **Given** `cursor` bị hỏng/không giải mã được hoặc `limit > 100`, **When** gọi `GET /wallpapers`,
   **Then** nhận `400` với `error.code = VALIDATION_ERROR`.

---

### User Story 2 - Xem chi tiết một hình nền (Priority: P1)

Người dùng chạm vào một hình nền để mở màn Detail: xem đầy đủ metadata (độ phân giải, thời
lượng, dung lượng, lượt tải/thích, nguồn/giấy phép) và biết hình này thuộc bộ sưu tập nào để
nhảy vào bộ sưu tập đó.

**Why this priority**: Là bước bắt buộc trước khi tải; cùng P1 với duyệt vì màn Detail là điểm
người dùng quyết định tải/mở khoá.

**Independent Test**: Gọi `GET /wallpapers/{id}` cho một hình nền thuộc ≥1 bộ sưu tập, xác nhận
field `collections` được populate đầy đủ (mini ref); gọi với id không tồn tại nhận `404 NOT_FOUND`.

**Acceptance Scenarios**:

1. **Given** hình nền id tồn tại và thuộc bộ sưu tập "neon-nights", **When** gọi `GET /wallpapers/{id}`,
   **Then** trả object đầy đủ với `collections` chứa ref bộ "neon-nights".
2. **Given** id không tồn tại (hoặc đã xoá mềm), **When** gọi `GET /wallpapers/{id}`,
   **Then** nhận `404` với `error.code = NOT_FOUND`.

---

### User Story 3 - Đồng bộ danh sách Yêu thích (Priority: P2)

Người dùng đã lưu (local) một danh sách id hình nền yêu thích; app cần lấy lại data mới nhất
cho đúng những id đó trong một lần gọi, để làm tươi màn Favorites và tự phát hiện item nào đã
bị gỡ khỏi kho.

**Why this priority**: Cần cho màn Favorites nhưng không chặn luồng duyệt cốt lõi; có thể ship sau P1.

**Independent Test**: Gọi `POST /wallpapers/batch` với hỗn hợp id tồn tại và không tồn tại, xác
nhận chỉ trả những id tồn tại (bỏ qua âm thầm id thiếu), và enforce trần 100 id.

**Acceptance Scenarios**:

1. **Given** `ids=[101, 999999]` với 101 tồn tại, 999999 không, **When** gọi `POST /wallpapers/batch`,
   **Then** trả mảng chỉ chứa hình nền 101 (không lỗi cho id thiếu).
2. **Given** `ids` rỗng hoặc chứa > 100 phần tử, **When** gọi `POST /wallpapers/batch`,
   **Then** nhận `400` với `error.code = VALIDATION_ERROR`.

---

### User Story 4 - Duyệt bộ sưu tập được biên tập (Priority: P2)

Người dùng mở tab "Bộ sưu tập" xem các bộ được biên tập (curated) — mỗi bộ có ảnh bìa, mô tả,
màu nhấn, cờ premium và số lượng hình. Mở một bộ để xem toàn bộ hình nền trong bộ theo đúng
thứ tự biên tập.

**Why this priority**: Tính năng khám phá có giá trị nhưng không phải luồng tối thiểu; đi sau
duyệt/chi tiết.

**Independent Test**: Seed một bộ sưu tập với các hình nền theo thứ tự cụ thể, gọi `GET /collections`
(danh sách meta, không nhúng items) và `GET /collections/{id}` (nhúng `items` đúng thứ tự).

**Acceptance Scenarios**:

1. **Given** có 3 bộ sưu tập curated, **When** gọi `GET /collections`, **Then** trả toàn bộ 3 bộ
   (không phân trang), mỗi bộ kèm `wallpaper_count`, **không** nhúng `items`.
2. **Given** bộ sưu tập id chứa hình nền theo thứ tự [8, 5, 7, 6], **When** gọi `GET /collections/{id}`,
   **Then** trả object bộ kèm `items` là mảng hình nền **đúng thứ tự** [8, 5, 7, 6].
3. **Given** bộ premium (`is_premium: true`), **When** gọi `GET /collections/{id}`, **Then** vẫn
   trả đầy đủ meta + items (gate premium **không** nằm ở đây mà ở download-url từng file).
4. **Given** id bộ sưu tập không tồn tại, **When** gọi `GET /collections/{id}`, **Then** `404 NOT_FOUND`.

---

### User Story 5 - Lấy link tải một hình nền (đường đi tạm) (Priority: P3)

Người dùng chạm "Tải" trên màn Detail; app gọi endpoint download-url. Trong phạm vi spec này,
đường đi này chỉ được dựng khung để mobile hoàn thiện điều hướng — entitlement thật + presigned
URL ngắn hạn hoàn thiện ở BE-005.

**Why this priority**: Chỉ là placeholder giữ hình dạng contract cho mobile; logic thật thuộc spec sau.

**Independent Test**: Gọi `GET /wallpapers/{id}/download-url` cho hình non-premium nhận mock `200`
đúng shape contract; cho hình premium nhận `402 ENTITLEMENT_REQUIRED`; id không tồn tại trả `404`.

**Acceptance Scenarios**:

1. **Given** hình nền non-premium id tồn tại, **When** gọi `GET /wallpapers/{id}/download-url`,
   **Then** trả `200` với `{ download_url, expires_at }` đúng shape contract (URL mock/tạm).
2. **Given** hình nền premium (`is_premium: true`), **When** gọi endpoint, **Then** trả `402` với
   `error.code = ENTITLEMENT_REQUIRED` (chưa có hệ thống verify transaction — hoàn thiện ở BE-005).
3. **Given** id không tồn tại, **When** gọi endpoint, **Then** `404 NOT_FOUND`.

---

### Edge Cases

- **Thẻ không tồn tại trong filter**: `GET /wallpapers?tags=khong-ton-tai` → trả danh sách rỗng
  (không lỗi), vì đây là filter chứ không phải tra cứu resource.
- **Nhiều thẻ AND rỗng giao**: hai thẻ hợp lệ nhưng không hình nào có cả hai → danh sách rỗng.
- **wallpaper_count nhất quán**: số đếm trên Category/Tag/Collection chỉ tính hình nền đã publish,
  chưa xoá mềm.
- **Hình nền chưa publish / đã xoá mềm**: không bao giờ xuất hiện ở bất kỳ endpoint public nào
  (list, detail, batch, collection items).
- **Ổn định cursor khi có bản ghi mới chèn vào**: cursor keyset phải không nhảy/lặp item khi có
  hình nền mới được thêm giữa các lần lật trang.
- **`is_premium` trong filter**: nhận cả `true`/`false`; giá trị không hợp lệ → `400 VALIDATION_ERROR`.
- **Bộ sưu tập rỗng**: `GET /collections/{id}` cho bộ chưa có hình nào → `items: []` hợp lệ, không lỗi.

## Requirements *(mandatory)*

### Functional Requirements

**Nội dung & mô hình dữ liệu**

- **FR-001**: Hệ thống MUST mô hình hoá 4 loại nội dung biên tập — Category, Tag, Wallpaper,
  Collection — với các thuộc tính đúng như contract v0.3.2 (`.claude/api-context.md` + `contracts/openapi.yaml`).
- **FR-002**: Tag MUST là **curated** và có quan hệ nhiều-nhiều với Wallpaper; không cho tạo thẻ
  tự do (free-form) từ bất kỳ endpoint public nào.
- **FR-003**: Collection MUST có quan hệ nhiều-nhiều **có thứ tự** với Wallpaper (thứ tự biên tập
  được lưu bền, ví dụ qua bảng nối có `position`); `GET /collections/{id}` MUST trả `items` đúng
  thứ tự đó.
- **FR-004**: Mỗi Wallpaper MUST lưu `source_url` và `license_type` (xuất xứ/giấy phép) để tuân
  thủ điều khoản nguồn (Pixabay/Pexels/Mixkit…).
- **FR-005**: `wallpaper_count` trên Category/Tag/Collection MUST phản ánh chỉ số hình nền đã
  publish, chưa xoá mềm.

**Endpoint public (tầng app, `X-App-Key`)**

- **FR-006**: Hệ thống MUST expose `GET /categories`, `GET /tags`, `GET /collections` trả **toàn
  bộ** danh sách (không phân trang); `GET /collections` chỉ trả meta + `wallpaper_count`, **không**
  nhúng items.
- **FR-006a**: `GET /tags` MUST chèn một **thẻ ảo "Tất cả"** (`{ id: 0, slug: "all", name: "Tất cả",
  wallpaper_count: <tổng hình nền published> }`) ở **đầu** mảng, do API sinh — **KHÔNG** lưu trong DB
  và **KHÔNG** gắn vào từng hình nền. Slug `all` là **reserved**: admin/seed MUST NOT tạo thẻ thật
  với slug `all`. Trong filter `GET /wallpapers?tags=`, slug `all` MUST bị bỏ qua (coi như không ràng
  buộc thẻ) — chọn "All" = trả toàn bộ published, sắp xếp mới→cũ (thứ tự mặc định của list).
- **FR-007**: Hệ thống MUST expose `GET /collections/{id}` trả meta bộ **kèm** `items` là mảng
  Wallpaper đầy đủ, đúng thứ tự biên tập; premium collection vẫn trả đầy đủ (không gate ở đây).
- **FR-008**: Hệ thống MUST expose `GET /wallpapers` với **cursor pagination keyset** (query
  `cursor`, `limit` mặc định 20 / tối đa 100) và envelope `{ items, next_cursor, has_more }`;
  **không** dùng offset `page`/`page_size`.
- **FR-009**: `GET /wallpapers` MUST hỗ trợ lọc theo `category` (slug), `tags` (nhiều slug phân
  tách phẩy, ngữ nghĩa **AND**), `orientation`, `is_premium`, và `search` (khớp tiêu đề).
- **FR-010**: Hệ thống MUST expose `GET /wallpapers/{id}` trả một Wallpaper với field `collections`
  được **populate đầy đủ** (ở list lớn field này có thể rỗng để tiết kiệm payload).
- **FR-011**: Hệ thống MUST expose `POST /wallpapers/batch` nhận `{ ids: [...] }` (tối đa 100),
  trả mảng Wallpaper cho các id tồn tại và **bỏ qua âm thầm** id không tồn tại.
- **FR-012**: Hệ thống MUST expose `GET /wallpapers/{id}/download-url` như đường đi tạm: hình
  **non-premium** trả `200` với `{ download_url, expires_at }` đúng shape contract (URL mock/tạm);
  hình **premium** trả `402 ENTITLEMENT_REQUIRED` (chưa có hệ thống verify transaction); id không
  tồn tại trả `404 NOT_FOUND`. Presigned URL ngắn hạn + verify entitlement thật hoàn thiện ở BE-005.
- **FR-013**: Mọi endpoint public MUST **không** để lộ hình nền chưa publish hoặc đã xoá mềm.

**Xác thực, lỗi & ranh giới**

- **FR-014**: Toàn bộ endpoint public/batch MUST được xác thực tầng app bằng `X-App-Key`; thiếu/
  sai key MUST trả `401` với `INVALID_APP_KEY`. Endpoint MUST **không** có bất kỳ khái niệm user/
  account nào (account-less).
- **FR-015**: Mọi phản hồi lỗi MUST theo envelope `{ "error": { "code", "message" } }` với `code`
  lấy từ error-code catalog, sinh qua exception handler tập trung — không body lỗi tự chế, không
  lộ traceback. Các mã dùng ở spec này: `INVALID_APP_KEY`, `VALIDATION_ERROR`, `NOT_FOUND`,
  `METHOD_NOT_ALLOWED`, `ENTITLEMENT_REQUIRED`, `SERVER_ERROR`.
- **FR-016**: Hệ thống MUST cung cấp một **fixture nội dung cố định commit vào repo** (danh mục,
  thẻ, hình nền, bộ sưu tập — mỗi hình nền có `source_url` + `license_type` từ nguồn công khai
  Pixabay/Pexels/Mixkit) nạp được qua một lệnh quản trị (management command), để dev/CI/test và
  mobile luôn có cùng một tập dữ liệu thật, deterministic, **không** phụ thuộc mạng hay API bên
  thứ ba lúc chạy.
- **FR-017**: Quản lý thẻ curated qua endpoint admin (`/admin/tags`) **KHÔNG thuộc BE-003** —
  hoãn hẳn sang BE-004 cùng các admin endpoint khác (khi có admin Bearer JWT đúng tầng). BE-003
  chỉ dựng model Tag + `GET /tags` public; thẻ mới được tạo qua fixture seed hoặc Django admin
  nội bộ (session auth, staff), không qua bất kỳ API tầng admin nào.
- **FR-018**: Việc tạo/biên tập nội dung (thêm hình nền, gán thẻ, dựng bộ sưu tập) trong phạm vi
  spec này MUST thực hiện qua kênh nội bộ sẵn có (Django admin nội bộ / fixture seed / data
  migration), **không** mở bất kỳ endpoint ghi công khai hay endpoint tầng admin nào ngoài các
  endpoint đọc public đã liệt kê.

### Key Entities *(include if feature involves data)*

- **Category**: nhóm phân loại hình nền cấp cao, curated. Thuộc tính: định danh, slug, tên,
  icon, số hình nền. Một hình nền thuộc đúng một danh mục.
- **Tag**: nhãn curated gắn lên hình nền để lọc/khám phá. Thuộc tính: định danh, slug, tên, số
  hình nền. Quan hệ nhiều-nhiều với Wallpaper.
- **Wallpaper**: đơn vị nội dung trung tâm (video hình nền động). Thuộc tính: định danh, tiêu đề,
  danh mục, các thẻ, hướng, thumbnail, preview video, cờ premium, độ phân giải, thời lượng, dung
  lượng, lượt tải, lượt thích, nguồn, loại giấy phép, các bộ sưu tập chứa nó, thời điểm tạo,
  trạng thái publish, cờ xoá mềm.
- **Collection**: bộ sưu tập hình nền được biên tập, curated. Thuộc tính: định danh, slug, tiêu
  đề, tác giả, mô tả, ảnh bìa, màu nhấn, cờ premium, số hình nền, thời điểm tạo. Quan hệ nhiều-
  nhiều **có thứ tự** với Wallpaper (lưu vị trí sắp xếp).

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Mobile chuyển được màn Browse/Detail/Favorites/Collections từ mock server sang API
  này mà **không cần đổi contract** (0 thay đổi `openapi.yaml` phát sinh khi tích hợp) — điểm đồng
  bộ MO-002 hoàn tất.
- **SC-002**: Một người dùng lật hết toàn bộ kho hình nền qua phân trang cursor mà **không gặp
  item trùng hoặc bị nhảy sót**, kể cả khi có nội dung mới được thêm giữa các lần lật.
- **SC-003**: Mọi tổ hợp filter (danh mục, thẻ-AND, hướng, premium, tìm kiếm) trả đúng tập kết
  quả kỳ vọng trong 100% ca kiểm thử tự động.
- **SC-004**: 100% phản hồi lỗi tuân theo envelope catalog (không có body lỗi tự chế, không lộ
  traceback) khi kiểm thử các ca 401/400/404/405.
- **SC-005**: Nội dung chưa publish hoặc đã xoá mềm **không bao giờ** rò rỉ ra bất kỳ endpoint
  public nào (list, detail, batch, collection items) — xác nhận bằng test.
- **SC-006**: `GET /collections/{id}` trả `items` đúng 100% thứ tự biên tập đã cấu hình.

## Assumptions

- **Kế thừa BE-002**: Xác thực `X-App-Key` (`core.api.AppTierAPIView` + `core.authentication.AppKeyAuthentication`),
  phân trang cursor (`core.pagination`), exception handler + error catalog (`core.errors`,
  `core.exception_handler`) đã có và được tái sử dụng — spec này không dựng lại.
- **Contract đóng băng**: contract v0.3.2 là nguồn sự thật; spec này chỉ **hiện thực**, không đổi
  hình dạng API. Nếu phát sinh nhu cầu đổi, phải quay lại quy trình contract-first
  (`docs/screen-inventory.md` → contract → sync 2 repo) ở một thay đổi riêng.
- **Account-less**: không có model user/account; không có trạng thái "đăng nhập" ở tầng app.
- **Entitlement để sau**: quyết định premium thật nằm ở `download-url` và hoàn thiện ở BE-005;
  ở list/detail/collection chỉ phơi cờ `is_premium` để client hiển thị.
- **Nguồn media**: các file media thật (video/thumbnail/preview) và pipeline xử lý (transcode/
  thumbnail/scan) thuộc BE-004; ở BE-003 các URL media có thể trỏ tới dữ liệu seed/nguồn công khai.
- **Ngoài scope**: Celery/transcode/upload pipeline (BE-004); IAP verify + entitlement thật
  (BE-005); mọi endpoint tầng admin có auth Bearer — gồm `/admin/tags`, CRUD wallpaper/collection
  (BE-004); "Nổi bật/Trending" (`is_featured`) chưa chốt ở product-context — không đưa vào spec này.

# Contract Delta — v0.6.0 → v0.7.0 (BE-008)

The exact edits to apply to `.claude/openapi.yaml` + `.claude/api-context.md` **before** any
code lands (Constitution I), then copy verbatim into `livecanvas-mobile`
(`.claude/` + `contracts/openapi.yaml`).

**⚠️ This bump changes shape, not just wording** — a new path and a new response schema. Unlike
v0.5.0 and v0.6.0, the mobile client **must** be regenerated (`scripts/generate_api.sh`).

---

## 0. Order of edits (constitution order — do not shortcut)

1. `.claude/screen-inventory.md` — screen #1 Browse, screen #11 admin (below)
2. `.claude/openapi.yaml` — `info.version` → `0.7.0` + `info.description` note + new path +
   new schemas + `Wallpaper.description` unchanged (already declared at v0.6.0)
3. `.claude/api-context.md` — header version, "Đổi so với v0.6.0" note, new endpoint sections
4. code
5. copy all three into the mobile repo + changelog entry there

## 1. `screen-inventory.md`

- **Row #1 Browse** — data needed gains: *các section curated có tiêu đề (do admin bật, có thứ
  tự) — mỗi section ≤10 wallpaper, "Xem tất cả" nhảy sang Collection Detail*; endpoint column
  gains `GET /home`.
- **Row #11 Admin: Upload Wallpaper** — action gains *sửa mô tả wallpaper đã tồn tại*; endpoint
  column gains `PATCH /admin/wallpapers/{id}`.
- **Row #13 Admin: Quản lý Bộ sưu tập** — action gains *bật/tắt hiển thị trên Browse + đặt thứ
  tự section*.
- New bullet under "Quyết định đã chốt": **Browse sections (v0.7.0)** — section = Collection có
  `show_on_home`, KHÔNG có resource mới; trần 10 section × 10 wallpaper áp lúc đọc; section
  rỗng bị bỏ qua và KHÔNG chiếm slot; premium chỉ hiển thị badge, gate vẫn ở `download-url`.

## 2. `openapi.yaml`

### 2.1 `info`

```yaml
info:
  description: >
    …(giữ nguyên các đoạn cũ)…

    v0.7.0 (BE-008): Browse có section curated. Thêm `GET /home` (app tier, KHÔNG phân
    trang) trả tối đa 10 section, mỗi section tối đa 10 wallpaper theo thứ tự curate.
    Section = Collection được admin bật `show_on_home` + `home_position` — KHÔNG có
    resource mới. Section rỗng (không còn wallpaper hiển thị được) bị bỏ qua và không
    chiếm slot. Premium chỉ hiển thị badge; gate entitlement vẫn duy nhất ở
    `download-url`. Thêm `PATCH /admin/wallpapers/{id}` (chỉ sửa `description`).
    Admin bật section qua `show_on_home` + `home_position` trong body
    `POST|PATCH /admin/collections` — payload công khai của `/collections` KHÔNG đổi.
    Không error code mới. ⚠️ Đổi schema/path → mobile PHẢI regenerate client.
  version: "0.7.0"
```

### 2.2 New path `GET /home`

```yaml
  /home:
    get:
      tags: [Public]
      summary: >
        Màn Browse dạng section curated. KHÔNG phân trang, bounded cứng: tối đa 10
        section × tối đa 10 wallpaper/section (trần áp lúc đọc — admin bật dư thì phần
        dư bị bỏ qua im lặng, không lỗi). Section sắp theo `home_position` tăng dần,
        trùng vị trí thì tie-break theo id (ổn định giữa các request). Chỉ chứa
        wallpaper published; section không còn wallpaper nào thì bị bỏ hẳn khỏi mảng
        (và không chiếm slot). Không có section nào → `sections: []` + 200 (KHÔNG 404).
        "Xem tất cả" của 1 section = gọi `GET /collections/{collection_id}` đã có.
      responses:
        '200':
          description: OK
          content:
            application/json:
              schema: { $ref: '#/components/schemas/HomeResponse' }
        '401':
          description: INVALID_APP_KEY
          content:
            application/json:
              schema: { $ref: '#/components/schemas/ErrorResponse' }
```

### 2.3 New schemas

```yaml
    HomeResponse:
      type: object
      required: [sections]
      properties:
        sections:
          type: array
          maxItems: 10
          items: { $ref: '#/components/schemas/HomeSection' }

    HomeSection:
      type: object
      required: [key, title, collection_id, is_premium, items]
      properties:
        key:
          type: string
          description: Slug của collection — định danh ổn định cho client (đổi title không đổi key).
        title: { type: string }
        collection_id:
          type: integer
          description: Target của "Xem tất cả" → `GET /collections/{id}`.
        cover_url: { type: string }
        accent_color: { type: string, nullable: true }
        is_premium:
          type: boolean
          description: Chỉ để hiển thị badge/nút "Mở khoá" — KHÔNG phải gate.
        items:
          type: array
          maxItems: 10
          description: Wallpaper published theo đúng thứ tự curate; `collections` rỗng như mọi list khác.
          items: { $ref: '#/components/schemas/Wallpaper' }
```

### 2.4 `show_on_home` / `home_position` — CHỈ trong body admin, KHÔNG vào schema `Collection`

⚠️ **KHÔNG thêm 2 field này vào `components.schemas.Collection`.** Schema đó dùng chung cho
`GET /collections` **công khai** (openapi.yaml:409) lẫn các response admin (:781/:797/:819) và
được `CollectionDetail` `allOf` (:194) — khai ở đó nghĩa là hứa trả chúng trên app tier, trong
khi `CollectionMetaSerializer` không trả (và mobile cũng không cần: client đọc section qua
`GET /home`, không tự suy từ `/collections`). Khai mà không trả = server lệch contract đã đóng
băng → vi phạm Constitution I.

Chỉ thêm vào **request body** của `POST /admin/collections` và
`PATCH /admin/collections/{id}` (cả hai optional):

```yaml
                show_on_home:
                  type: boolean
                  default: false
                  description: (v0.7.0) Cho collection này hiện thành section ở màn Browse.
                home_position:
                  type: integer
                  default: 0
                  minimum: 0
                  description: >
                    (v0.7.0) Vị trí section trên Browse, tăng dần. KHÔNG unique — trùng vị trí
                    thì tie-break theo id. Bỏ qua khi show_on_home=false.
```

Nếu sau này app thật sự cần đọc 2 field này ngoài `/home`, đó là một contract bump riêng **kèm
task expose ở `CollectionMetaSerializer`** — không làm lén ở đây.

### 2.5 New path `PATCH /admin/wallpapers/{id}`

```yaml
  /admin/wallpapers/{id}:
    patch:
      tags: [Admin]
      summary: >
        Sửa mô tả của wallpaper đã tồn tại (v0.7.0). CHỈ nhận `description` — không sửa
        được bất kỳ thuộc tính nào khác (media/status/tag/category/collection giữ luồng
        riêng). Chuỗi rỗng hoặc toàn khoảng trắng → lưu thành `null`.
      security: [ { AdminBearer: [] } ]   # tên scheme thật trong openapi.yaml:59 — KHÔNG phải "AdminJWT"
      parameters:
        - name: id
          in: path
          required: true
          schema: { type: integer }
      requestBody:
        required: true
        content:
          application/json:
            schema:
              type: object
              properties:
                description: { type: string, nullable: true }
      responses:
        '200':
          description: OK
          content:
            application/json:
              schema: { $ref: '#/components/schemas/Wallpaper' }
        '401': { description: UNAUTHORIZED_ADMIN }
        '403': { description: FORBIDDEN_ADMIN_ROLE }
        '404': { description: NOT_FOUND }
```

(`DELETE /admin/wallpapers/{id}` đã tồn tại ở path này — chỉ thêm verb `patch`.)

⚠️ Response dùng **`Wallpaper`**, KHÔNG phải `AdminWallpaper` — schema đó **không tồn tại**;
`POST /admin/wallpapers` hiện cũng trả `Wallpaper` (openapi.yaml:674). Server trả
`AdminWallpaperSerializer` (thêm `status` + `failure_reason`), tức contract đang mô tả thiếu ở
chỗ này **từ BE-004**, không phải lỗi do BE-008 tạo ra — giữ nguyên độ chính xác hiện có thay vì
sửa lệch một mình verb mới. Muốn khai đúng thì định nghĩa schema `AdminWallpaper`
(`allOf: [Wallpaper, {status, failure_reason}]`) và áp cho **cả** POST/GET/PATCH trong một lần —
việc đó nằm ngoài phạm vi BE-008, ghi lại làm nợ contract.

### 2.6 `POST /admin/wallpapers`

Thêm `description` (optional, nullable) vào request body.

## 3. `api-context.md`

- Header: `Last updated: <ngày ship>` · `Contract version: **v0.7.0**`
- Thêm khối **"Đổi so với v0.6.0 (BE-008)"** ngay dưới header, nội dung tóm tắt như §2.1 +
  cảnh báo regenerate client.
- **Public Endpoints**: thêm mục `### GET /home` — header `X-App-Key`, không phân trang, **nêu
  rõ 2 con số trần (10 section × 10 wallpaper)** để client tự cỡ UI (FR-020), quy tắc bỏ section
  rỗng, tie-break, ví dụ response JSON.
- **Admin Endpoints**: thêm `### PATCH /admin/wallpapers/{id}`; cập nhật
  `POST /admin/wallpapers` (thêm `description`) và `POST|PATCH /admin/collections` (thêm
  `show_on_home`, `home_position` **vào body — không đụng response**).
- **Mục `GET /collections`**: ghi 1 dòng rằng payload KHÔNG đổi ở v0.7.0, để người đọc không
  tưởng section làm đổi luôn list collection.
- **Error Code Catalog**: KHÔNG đổi — không có mã mới.

## 4. Sync sang mobile (bắt buộc trước khi đóng spec)

```bash
cp .claude/openapi.yaml        ../flutter_live_canvas/.claude/openapi.yaml
cp .claude/openapi.yaml        ../flutter_live_canvas/contracts/openapi.yaml
cp .claude/api-context.md      ../flutter_live_canvas/.claude/api-context.md
cp .claude/screen-inventory.md ../flutter_live_canvas/.claude/screen-inventory.md
```

Rồi thêm entry vào `flutter_live_canvas/.claude/changelog.md` nêu rõ: **v0.7.0 đổi
schema/path → BẮT BUỘC chạy `scripts/generate_api.sh`** (khác v0.5.0/v0.6.0), `GET /home` là
màn Browse mới, `PATCH /admin/wallpapers/{id}` cho mô tả.

## 5. Contract-test checklist (Constitution X)

- `GET /home` không app key → 401 `INVALID_APP_KEY`, đúng error envelope
- Response chỉ chứa đúng các key ở §2.3 — không thừa field nào
- `sections: []` + 200 khi chưa bật collection nào
- `items[*]` khớp đúng shape `Wallpaper` của list (có `description`, `collections: []`)
- `PATCH /admin/wallpapers/{id}` với app key thay vì admin JWT → 401 `UNAUTHORIZED_ADMIN`
  (kiểm tra ở `core/tests/test_tier_isolation.py`)
- Toàn bộ contract test cũ vẫn xanh **mà không phải sửa file test nào** (FR-023 / SC-011)
- `GET /collections` KHÔNG mọc thêm `show_on_home`/`home_position` (§2.4 — chúng chỉ ở body admin)

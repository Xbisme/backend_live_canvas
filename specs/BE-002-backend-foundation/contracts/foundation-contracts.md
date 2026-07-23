# Foundation Contracts: BE-002

These are the cross-cutting request/response contracts every later endpoint inherits. They are the
*internal enforcement* view; the product-facing catalog lives in `.claude/api-context.md` +
`contracts/openapi.yaml`. Health endpoints (BE-001) and the temporary probe route are **not** part of
the product contract.

---

## C1 — App-Tier Authentication (`X-App-Key`)

**Applies to**: all public + IAP endpoints (via `core.api.AppTierAPIView`). **NOT** to
`/health*`, Django `/admin/`, or (future) `/admin/*` API.

| Condition | Response |
|---|---|
| `X-App-Key` header absent | `401` · `{ "error": { "code": "INVALID_APP_KEY", "message": "..." } }` |
| `X-App-Key` present but ≠ configured | `401` · `INVALID_APP_KEY` |
| Only `Authorization: Bearer …` present, no valid `X-App-Key` | `401` · `INVALID_APP_KEY` (no cross-tier fallback) |
| Server `X_APP_KEY` empty/unset (misconfig) | **deny every request** `401` · `INVALID_APP_KEY`; `prod` refuses to boot |
| `X-App-Key` == configured (non-empty) | pass to view (probe → `200 {"ok": true}`) |

**Guarantees**: constant-time key comparison; identical response for absent vs wrong key (no
info-leak); key value never logged; admin Bearer credential never authenticates this tier; an empty
configured key is a fail-closed misconfiguration (never an open door), and `prod` fails fast at
startup if `X_APP_KEY` is missing/empty (FR-021). Health endpoints and Django `/admin/` are never
subject to this gate (FR-015).

---

## C2 — Structured Error Envelope

Every error from any DRF view is rendered by `core.exception_handler.structured_exception_handler`:

```json
{ "error": { "code": "<CODE>", "message": "<safe human text>" } }
```

**Mapping (BE-002 active subset)**:

| Trigger | HTTP | `code` |
|---|---|---|
| `Http404` / DRF `NotFound` | 404 | `NOT_FOUND` |
| DRF `ValidationError` / `ParseError` / invalid cursor | 400 | `VALIDATION_ERROR` |
| Missing/wrong `X-App-Key` (`InvalidAppKey`) | 401 | `INVALID_APP_KEY` |
| DRF `MethodNotAllowed` | 405 | `METHOD_NOT_ALLOWED` *(new in v0.3.1)* |
| Any unhandled exception | 500 | `SERVER_ERROR` *(new in v0.3.1)* |

**Guarantees**: no stack trace / Django debug page / raw DRF body reaches a client in either flavor;
unhandled exceptions logged server-side via `logger.exception`; HTTP status ⇔ code agreement.

---

## C3 — Cursor Pagination Envelope

Emitted by `core.pagination.EnvelopeCursorPagination` (the `DEFAULT_PAGINATION_CLASS`):

```json
{ "items": [ /* … */ ], "next_cursor": "<opaque|null>", "has_more": <bool> }
```

| Param | Rule |
|---|---|
| `limit` | default 20, max 100; `>100` → `400 VALIDATION_ERROR` |
| `cursor` | opaque keyset token; invalid/expired → `400 VALIDATION_ERROR` |
| end-of-data | `next_cursor: null` and `has_more: false` |

**Guarantees**: no `page`/offset params anywhere; envelope shape matches the frozen contract's Cursor
Pagination section. (Behaviorally exercised once list endpoints exist in BE-003; BE-002 asserts config
+ response-builder shape.)

---

## C4 — Contract Catalog Delta (v0.3.0 → v0.3.1)

Two foundation error codes added to `.claude/api-context.md` + `contracts/openapi.yaml`:

| Code | HTTP | Meaning |
|---|---|---|
| `SERVER_ERROR` | 500 | Unexpected server-side failure (generic; no internal detail leaked) |
| `METHOD_NOT_ALLOWED` | 405 | HTTP method not supported on this resource |

**Sync obligation**: after editing both backend contract files + bumping the version header, copy them
verbatim into `livecanvas-mobile` (flagged handoff — that repo is not in this workspace).

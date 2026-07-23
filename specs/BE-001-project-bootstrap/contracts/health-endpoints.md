# Contract: Operational Health Endpoints

> **Scope note**: These are **operational** endpoints for developers and orchestration. They
> are intentionally **NOT** part of the product API contract (`contracts/openapi.yaml`), which
> stays screen-driven per Constitution Principle I. They carry **no** `X-App-Key` in this spec
> (the app-tier middleware does not exist until BE-002; health paths will be exempted then).

## `GET /health` — Liveness

Confirms the process is up and able to serve HTTP. Does **not** touch the database or any
dependency.

- **Auth**: none
- **Request**: no params, no body
- **200 OK** (always, when the process serves):
  ```json
  { "status": "ok" }
  ```

## `GET /health/ready` — Readiness

Confirms the service can reach its database dependency. Used to gate traffic / deploys.

- **Auth**: none
- **Request**: no params, no body
- **Behavior**: executes a trivial `SELECT 1` against the default database connection.
- **200 OK** (DB reachable):
  ```json
  { "status": "ready" }
  ```
- **503 Service Unavailable** (DB unreachable / query raises):
  ```json
  { "status": "unavailable" }
  ```

## Acceptance mapping

| Scenario | Endpoint | Expected |
|---|---|---|
| Process running (US1 #1) | `GET /health` | 200 `{"status":"ok"}` |
| DB reachable (US1 #2) | `GET /health/ready` | 200 `{"status":"ready"}` |
| DB unavailable (US1 #3) | `GET /health/ready` | 503 `{"status":"unavailable"}` |
| DB down, liveness unaffected (US1 #3) | `GET /health` | 200 `{"status":"ok"}` |

## Test notes

- The **503 readiness** path is unit-tested by forcing the DB check to raise (patching the
  connection/cursor), so no real database outage is required (deterministic — Principle X).
- CI runs a Postgres service container so the **200 readiness** path passes end-to-end.

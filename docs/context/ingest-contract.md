# Ingest contract — `POST /internal/events`

The backend (`backend/`) accepts telemetry from the Juice Shop middleware
(`juiceshop/telemetry/telemetry.ts`, wired by `juiceshop/patches/server-telemetry.patch`).
Implementation: `backend/rootlane_toolbox/api/ingest.py`.

## Endpoint and auth

- `POST https://api.rootlane.xyz/internal/events`, `Content-Type: application/json`.
- `Authorization: Bearer <INGEST_TOKEN>`; the toolbox compares it with its own `INGEST_TOKEN`
  in constant time.
- `503` when the toolbox has no `INGEST_TOKEN` configured, `401` when the header is missing,
  malformed or wrong, `422` when the body is not an event, a list or `{"events": [...]}`.

## Body

What the middleware sends is one batch per flush (every second or at 100 rows):

```json
{"events": [ { ...event }, { ...event } ]}
```

The endpoint also accepts a bare JSON list and a single event object.

## Event fields

| Field | Type | Required | Stored in |
| --- | --- | --- | --- |
| `ts` | ISO-8601 string (`2026-10-09T21:00:31.120Z`) | yes | `http_requests.ts` |
| `trace_id` | string | yes | `http_requests.trace_id` |
| `method` | string | yes | `http_requests.method` |
| `route` | string (route template, e.g. `/rest/basket/:id`) | yes | `http_requests.route` |
| `status` | integer 0-65535 | yes | `http_requests.status` |
| `latency_ms` | integer >= 0 | yes | `http_requests.latency_ms` |
| `ip` | string | yes | `http_requests.ip` |
| `principal_id` | string, default `""` | no | `http_requests.principal_id` |
| `auth_outcome` | string, default `"none"` | no | `http_requests.auth_outcome` |
| `param_flags` | array of strings, default `[]` | no | `http_requests.param_flags` |
| `jwt_alg` | string | no | `auth_events.jwt_alg` |
| `claimed_identity` | string | no | `auth_events.claimed_identity` |
| `principal_resolved` | boolean | no | `auth_events.principal_resolved` |

`auth_events` receives one row (with `event` = `auth_outcome`) only for events that carry at
least one of `jwt_alg`, `claimed_identity` or `principal_resolved`.

The middleware additionally sends `path`, `user_agent` and `has_token`. They are valid input
but have no column, so they are dropped. Any other field is dropped too.

## Response

`200 {"accepted": <stored events>, "rejected": <events that failed validation>}`. A batch is
never rejected as a whole because of one bad event.

## Never sent, never stored

Passwords, tokens or credentials of any kind, `Authorization` and `Cookie` values, request or
response bodies, and parameter values. The middleware derives `param_flags` markers locally and
never sends the values. The endpoint stores only the fields in the table above, so a client
that sends `password`, `token`, `authorization`, `cookie` or `body` keys is still accepted and
those keys never reach the database.

## Gaps against the middleware

- `jwt_alg`, `claimed_identity` and `principal_resolved` are not sent by the middleware, so
  `auth_events` stays empty until it sends them. `principal_id` is the identity the app acts as
  (claimed from the unverified token), not a resolved one.
- `path`, `user_agent`, `has_token` are sent but not stored.

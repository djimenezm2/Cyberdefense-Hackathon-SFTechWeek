# Rootlane dashboard — contract for the UI team

The dashboard lives at `https://app.rootlane.xyz` as its own deployment (Vite + React, static build).
It calls the API at `https://api.rootlane.xyz` (base URL from `VITE_API_BASE_URL`); the API allows CORS
from the dashboard origin. During development point the app at the fixtures in `frontend/fixtures/` (same
shapes as the live API) or at `http://localhost:8000` once the toolbox runs.

Copy is in English (judges). Times are ISO-8601 UTC strings; render them in local time.
Live updates come from the Server-Sent Events stream below; fall back to polling every 2 s if the
stream drops.

## Screens

1. **Overview** — live traffic chart (requests, errors, rejected auth per 10 s), the analyzer's
   latest verdicts stream (ignore / watch / escalate with a one-line rationale), open incidents list,
   agent status pill (idle / investigating).
2. **Incident** — header (title, severity, status), timeline of the related requests, the agent's
   steps as they happen, hypothesis with cited evidence, verification panel (replica before vs.
   after, regression tests, Semgrep old vs. new), the proposed diff, the Semgrep rule, and the
   approval box (approver name + Approve / Reject). After apply: PR link and production check.
3. **Audit** — table of every agent action (time, operation, outcome, duration, on behalf of).

## Endpoints

| Method | Path | Fixture |
|---|---|---|
| GET | `/api/overview` | `overview.json` |
| GET | `/api/events?since=<ts>&limit=100` | `events.json` |
| GET | `/api/windows?limit=20` | `windows.json` |
| GET | `/api/incidents` | `incidents.json` |
| GET | `/api/incidents/{id}` | `incident-detail.json` |
| GET | `/api/actions?incident_id=<id>` | `actions.json` |
| POST | `/api/incidents/{id}/approve` body `{"approver": "Name"}` | returns updated incident detail |
| POST | `/api/incidents/{id}/reject` body `{"approver": "Name", "reason": "..."}` | returns updated incident detail |

POST requests send header `X-Admin-Token` (value from the login prompt of the dashboard; the
toolbox compares it with `ADMIN_TOKEN`). 401 → ask for the token again.

## Enumerations

- Incident `status`: `investigating`, `not_reproduced`, `fix_failed`, `pending_approval`, `rejected`, `applying`, `applied`.
- `severity`: `low`, `medium`, `high`, `critical`.
- Analyzer `verdict`: `ignore`, `watch`, `escalate`.
- Agent step `kind`: `query`, `read_source`, `semgrep`, `context`, `replay`, `verify`, `propose`, `approval`, `apply`, `lesson`.
- Step `outcome`: `ok`, `error`, `refused`.

## Shapes

See the fixtures; every field there is part of the contract. Fields may be `null` until the agent
reaches that stage (e.g. `proposal` is `null` while `status` is `investigating`).

## Live stream (SSE)

`GET /api/stream` — `text/event-stream`, consumed with `new EventSource(`${API}/api/stream`)`.
Each message has an `event:` name and a JSON `data:` line (see `stream-events.json`):

| event | data |
|---|---|
| `verdict` | one analyzer window (same shape as an item of `windows.json`) |
| `step` | `{incident_id, ts, kind, summary, outcome}` (same shape as an item of `incident-detail.steps`) |
| `incident_update` | `{id, status, severity, title}` |
| `ping` | `{}` every 15 s to keep the connection open |

On `incident_update` re-fetch `/api/incidents/{id}` for the full detail.

## Optional: chat with the agent

Build only after the three screens work. Lets a viewer ask the agent about one incident; the
toolbox forwards the message to that incident's Guild session.

| Method | Path | Fixture |
|---|---|---|
| GET | `/api/incidents/{id}/messages` | `messages.json` |
| POST | `/api/incidents/{id}/messages` body `{"text": "..."}` | returns the stored user message; the agent's reply arrives as a new item on the next GET (and as a `step` event with `kind: "chat"`) |

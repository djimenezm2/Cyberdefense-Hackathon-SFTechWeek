# Rootlane dashboard — contract for the UI team

The dashboard lives at `https://app.rootlane.xyz` as its own deployment (Vite + React, static build).
It calls the API at `https://api.rootlane.xyz` (base URL from `VITE_API_BASE_URL`); the API allows CORS
from the dashboard origin. During development point the app at the fixtures in `ui/fixtures/` (same
shapes as the live API) or at `http://localhost:8000` once the toolbox runs.

Copy is in English (judges). Times are ISO-8601 UTC strings; render them in local time.
Poll every 2 s for live data; no websockets.

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

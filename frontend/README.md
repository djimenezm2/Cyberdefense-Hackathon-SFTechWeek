# Rootlane dashboard (`frontend/`)

Vite + React + Tailwind. Implements `docs/ui/dashboard-contract.md`: Overview, Incident, Audit screens, plus sign-in and a Guardrails page.

## Run

```bash
cd frontend
npm install
npm run dev            # http://localhost:5173
```

- **Demo mode** (no `VITE_API_BASE_URL`): simulated data with the exact fixture shapes. About 30 s after sign-in, the `inc_01` attack plays out on its own. Press **A** to trigger it at any time. *Approve and apply* finishes the incident.
- **Live mode**: `VITE_API_BASE_URL=https://api.rootlane.xyz npm run dev` (or set it in `.env`).
- **Against the fixtures, no backend**: `node scripts/fixture-server.mjs` serves `fixtures/` on `:8000`. Then run `VITE_API_BASE_URL=http://localhost:8000 npm run dev`.

## How it talks to the toolbox

| What | Where in code |
|---|---|
| Endpoint paths | `src/lib/contract.js` → `ENDPOINTS` |
| Response → UI shape | `src/lib/adapters.js` |
| Loading, SSE `/api/stream` (`verdict`, `step`, `incident_update`, `ping`), 2 s polling fallback, approve/reject with `X-Admin-Token` | `src/lib/useAgent.js` |
| Demo simulation | `src/lib/mock.js` |

`/api/events` is polled every 2 s with `since=`, because events are not part of the stream. Sign-in stores the approver name and admin token in `localStorage`. A `401` on approve or reject asks for the token again.

### Shapes beyond the fixtures

`approval` and `apply` follow the backend models in `docs/superpowers/plans/2026-10-09-rootlane-backend.md`:

- `Approval`: `approver`, `decision`, `ts`, `reason`, `proposal_hash`
- `ApplyResult`: `pr_url`, `production_status`, `production_summary`, `variants`

## Build and deploy

```bash
npm run build          # static files in dist/
```

Deployed on **Vercel** with Root Directory `frontend/`, framework Vite and env `VITE_API_BASE_URL`. It redeploys on every push to `main`. Until the API is live, leave `VITE_API_BASE_URL` empty so the app runs in demo mode. `app.rootlane.xyz` is a CNAME to `cname.vercel-dns.com`.

## Components worth knowing

- `src/components/ui/code-curtain.jsx` is the sign-in hero: code as cloth that gets attacked, turns red, and is patched.
- `src/components/LiveTerrain.jsx` is the live map of routes, traffic and the agent on the Overview.
- `src/components/ui/compare.jsx` and `CodeCompare.jsx` show the patch before and after, on hover.
- `src/components/ApprovalBox.jsx` is the approval gate (approver plus Approve or Reject).

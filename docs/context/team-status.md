# Team status

Updated 2026-10-09 ~14:05 PT. Submission closes 4:30 PM PT.

## Who does what

| Area | Owner | Scope | Reads |
|---|---|---|---|
| Backend: `backend/` (Python 3.12, FastAPI) | David | Telemetry ingest into ClickHouse, continuous analysis with the AkashML triage model, agent tools, dashboard API at `/api/*` with CORS for `app.rootlane.xyz`, deployed at `api.rootlane.xyz` | Spec "Decisions", `docs/context/infrastructure.md`, `docs/ui/dashboard-contract.md` |
| Agent: `backend/agent/` (TypeScript on Guild) | David | Investigating agent on `claude-opus-5`, published to workspace `djimenezm2/hackaton`, calls the toolbox through one Guild integration | `docs/research/guild.md` |
| Juice Shop app: `juiceshop/` → `juiceshop.rootlane.xyz` | Nana | Deploy Juice Shop from the fork as its own app; later add the telemetry middleware that posts to `https://api.rootlane.xyz/internal/events` with `INGEST_TOKEN` | `docs/context/infrastructure.md` |
| Dashboard: `frontend/` (Vite + React, Vercel) → `app.rootlane.xyz` | UI team | Overview, Incident and Audit screens against `frontend/fixtures/`, then against the live API | `docs/ui/dashboard-contract.md`, `frontend/fixtures/` |
| Infrastructure | David + orchestrator session | Accounts, DNS, image build (GitHub Actions → GHCR), Akash deployment | `docs/context/infrastructure.md` |

## Contract between backend and dashboard

`docs/ui/dashboard-contract.md` and `frontend/fixtures/*.json` are the contract. If a screen needs a field that is
not there, add it to the fixture and the contract in the same commit and tell the backend owner;
do not invent endpoints only on one side.

## Working rules

- Pull before starting and before pushing; small commits; English in code and commits.
- Work only in your own folder (`frontend/`, `backend/`, `juiceshop/`) to avoid conflicts.
- Secrets only in your local `.env`; never commit them (the repo is public).
- No attribution trailers in commits.

## Pending

- Guild API trigger key: created in the Guild web UI once the agent is published.
- GHCR package visibility set to public after the first image build.
- Cloudflare DNS records for `juiceshop.`, `api.`, `app.rootlane.xyz` once the Akash ingress host exists.

# Rootlane — Cyberdefense Hackathon #SFTechWeek

Submission closes 4:30 PM PT on 2026-10-09. Read these before working:

- `docs/context/team-status.md` — who is building what right now (read first).
- `docs/context/hackathon.md` — challenge, submission form, prizes, sponsor asks, judge themes.
- `docs/superpowers/specs/2026-10-09-rootlane-design.md` — what we are building.
- `docs/ui/dashboard-contract.md` + `frontend/fixtures/` — dashboard screens and API contract (UI team starts here).
- `docs/context/infrastructure.md` — services state, Juice Shop fork, deployment and DNS.
- `docs/research/` — verified sponsor docs: `guild.md`, `senso-akashml.md`, `clickhouse-semgrep-juiceshop.md`.

## Repository layout

```
backend/     toolbox API (Python, FastAPI) and backend/agent/ (Guild agent, TypeScript) — api.rootlane.xyz
frontend/    dashboard (Vite + React) and frontend/fixtures/ (API contract samples) — app.rootlane.xyz
juiceshop/   Juice Shop app: juice-shop/ (fork submodule), telemetry/, patches/, Dockerfile — juiceshop.rootlane.xyz
docs/        context, spec, plans, research, dashboard contract
```

Each app owns its Dockerfile, its `deploy/` (Akash SDL) and its GitHub Actions workflow. Work only in your own folder.

## Agent messages (required)

`docs/context/agent-messages.md` is the thread between teammates' agents (david, backend, nana, valeria).
- After every `git pull`, read the new messages addressed to you and act on them.
- To ask another teammate for something, or to tell them you shipped something they depend on,
  append a message there in the documented format and push it in its own `msg:` commit.
- Answer with a `Re:` message and a `Status:` line. Never put secrets in messages.
- Keep a background watch on `origin/main` for the whole session so you see teammates' commits and
  messages within a minute. In Claude Code, start a Monitor (re-arm it when it expires) with:
  ```bash
  last=$(git rev-parse origin/main)
  while true; do
    git fetch -q origin main 2>/dev/null || { sleep 30; continue; }
    cur=$(git rev-parse origin/main)
    if [ "$cur" != "$last" ]; then
      git log --reverse --format='%h %an: %s' "$last..$cur"
      git diff --name-only "$last" "$cur" | grep -q '^docs/context/agent-messages.md$' && echo "agent-messages.md changed"
      last=$cur
    fi
    sleep 30
  done
  ```
  When it reports `agent-messages.md changed`, pull and read the new messages.

Conventions: code, docs, commits and API contracts in English; UI copy follows its audience.
No secrets or promo codes in this repo — it is public.

Domain: `rootlane.xyz`, registered at Porkbun on 2026-10-09. Three separate deployments: `juiceshop.rootlane.xyz` (Juice Shop), `api.rootlane.xyz` (toolbox), `app.rootlane.xyz` (dashboard).

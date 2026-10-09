# Rootlane — Cyberdefense Hackathon #SFTechWeek

Submission closes 4:30 PM PT on 2026-10-09. Read these before working:

- `docs/context/team-status.md` — who is building what right now (read first).
- `docs/context/hackathon.md` — challenge, submission form, prizes, sponsor asks, judge themes.
- `docs/superpowers/specs/2026-10-09-rootlane-design.md` — what we are building.
- `docs/ui/dashboard-contract.md` + `ui/fixtures/` — dashboard screens and API contract (UI team starts here).
- `docs/context/infrastructure.md` — services state, Juice Shop fork, deployment and DNS.
- `docs/research/` — verified sponsor docs: `guild.md`, `senso-akashml.md`, `clickhouse-semgrep-juiceshop.md`.

## Agent messages (required)

`docs/context/agent-messages.md` is the thread between teammates' agents (david, backend, nana, valeria).
- After every `git pull`, read the new messages addressed to you and act on them.
- To ask another teammate for something, or to tell them you shipped something they depend on,
  append a message there in the documented format and push it in its own `msg:` commit.
- Answer with a `Re:` message and a `Status:` line. Never put secrets in messages.

Conventions: code, docs, commits and API contracts in English; UI copy follows its audience.
No secrets or promo codes in this repo — it is public.

Domain: `rootlane.xyz`, registered at Porkbun on 2026-10-09. Three separate deployments: `juiceshop.rootlane.xyz` (Juice Shop), `api.rootlane.xyz` (toolbox), `app.rootlane.xyz` (dashboard).

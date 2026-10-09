# Rootlane

**An autonomous security agent that continuously watches a live app, investigates what looks wrong, and proposes a verified fix that a human approves.**

| | |
| --- | --- |
| Dashboard | https://app.rootlane.xyz |
| App under watch (our own OWASP Juice Shop instance) | https://juiceshop.rootlane.xyz |
| Toolbox API health | https://api.rootlane.xyz/healthz |

## The problem

The OWASP Top 10:2025 ranks Broken Access Control #1 and states that "100% of the applications tested were found to have some form of broken access control" (40 CWEs mapped, average incidence 3.74%). Source: [OWASP A01:2025 Broken Access Control](https://top10.owasp.org/2025/A01_2025-Broken_Access_Control).

Security teams already have tools. What they lack is closure:

- **Alerts don't fix anything.** A detector raises a flag and a human still has to find the root cause.
- **Patches without proof are guesses.** A fix that was never reproduced and re-tested may not close the hole, or may break the app.
- **Knowledge is scattered.** Policies, runbooks and past incidents live in places the responder never opens mid-incident.
- **Agents act without traces.** An autonomous tool that changes code without an audit trail is a new risk, not a defense.

## How it works

Rootlane runs a five-phase loop:

| Phase | What happens | Model / tool |
| --- | --- | --- |
| 1. Observe (always on) | Telemetry from the live app is summarized every ~10 s into behavioural features per principal and per IP; a cheap open model answers `ignore`, `watch` or `escalate` with a rationale. | AkashML `zai-org/GLM-5.3`, ClickHouse |
| 2. Investigate (only on `escalate`) | A frontier-model agent queries telemetry, reads the source, runs Semgrep and pulls verified policy context, then forms a hypothesis and a patch. | Guild agent on `claude-opus-5`, Senso, Semgrep |
| 3. Prove | The attack is reproduced on an isolated replica, the patch is applied, the attack is replayed and a regression suite runs. | Toolbox replicas, Semgrep |
| 4. Decide | A human reviews the evidence and approves or rejects in the dashboard. | Dashboard |
| 5. Ship + learn | The approved fix becomes a PR on the app's repository; the incident and its lesson are kept for the next investigation. | GitHub, Senso |

Nothing in the analyzer or the agent is written for a specific vulnerability: detection is generic behavioural features plus model judgement.

![Internal pipeline](docs/diagrams/5-internal-pipeline.png)

![System architecture](docs/diagrams/1-system-architecture.png)

![Incident lifecycle](docs/diagrams/3-incident-lifecycle.png)

More diagrams and their Mermaid sources: [docs/diagrams/](docs/diagrams/README.md).

## How the systems connect

| # | Component | Runs on | Connects to | How |
| --- | --- | --- | --- | --- |
| 1 | Juice Shop + telemetry middleware | Akash | Toolbox API `POST /internal/events` | Batched derived events, authenticated with `INGEST_TOKEN` |
| 2 | Toolbox API (Python, FastAPI) | Akash (`api.rootlane.xyz`) | ClickHouse Cloud | Stores requests, auth events, windows, verdicts, incidents and the audit log |
| 3 | Analyzer (inside the toolbox) | Akash | AkashML `zai-org/GLM-5.3` | Every ~10 s: window features in, verdict `ignore` / `watch` / `escalate` out |
| 4 | Dashboard (Vite + React) | Vercel (`app.rootlane.xyz`) | Toolbox API | Server-Sent Events (`/api/stream`) for verdicts and agent steps, polling fallback |
| 5 | Escalation trigger | Toolbox | Guild API | An `escalate` verdict opens an incident and starts a session of `rootlane-agent` |
| 6 | `rootlane-agent` (TypeScript, `claude-opus-5`) | Guild | Guild integration `rootlane-toolbox` | Scoped `TOOLBOX_API_KEY`; read-only queries, source reading, Semgrep scans |
| 7 | Policy context | Guild | Senso MCP | Verified policy and runbook answers the agent cites as evidence |
| 8 | Proposal and approval | Toolbox + dashboard | Human approver | Approve / reject requires `ADMIN_TOKEN` |
| 9 | Ship | Toolbox | GitHub fork `djimenezm2/juice-shop` | Approved fix opens a PR on the fork |
| 10 | Audit | Toolbox | ClickHouse `agent_actions` | Every agent tool call is recorded with its Guild session |
| 11 | DNS and HTTPS | Cloudflare | `rootlane.xyz` hosts | Proxied DNS and TLS for the three public hosts |
| 12 | Build | GitHub Actions | GHCR | Container images for the toolbox and the Juice Shop app |

## Sponsor tools and how we use them

| Sponsor | How Rootlane uses it |
| --- | --- |
| **Guild** | Hosts and runs the investigating agent; the toolbox is imported as one scoped integration (API key, least privilege); every run leaves a session trace; an API trigger starts the agent when the analyzer escalates. |
| **ClickHouse** | Real-time telemetry store, sliding-window detection features computed in SQL, incidents and the audit trail of every agent action. |
| **Akash** | Hosts the watched app (Juice Shop) and the toolbox API. |
| **AkashML** | The always-on triage model (`zai-org/GLM-5.3`) that reads every window and decides whether a frontier-model investigation is worth starting. |
| **Senso** | Verified context: four documents (authentication, input handling, object-level authorization policies and the incident runbook) the agent searches and cites; lessons from closed incidents. |
| **Semgrep** | Scans the code under investigation, verifies the patch closes the finding, and supplies a prevention rule. Semgrep Guardian also guarded the code we wrote today. |
| Pi | Not used: no product access was available at the event. |

## What is live vs. what is demo

We separate what runs in production today from what is shown with sample data.

**Live now**

- The three public apps: dashboard, Juice Shop, toolbox API.
- Telemetry from Juice Shop flowing into ClickHouse.
- Continuous analysis with real model verdicts from AkashML, streamed to the dashboard.
- The Guild agent, published and connected to the toolbox integration and to Senso; its tool calls are verified against the live API.
- The audit trail: every agent tool call is stored in ClickHouse with its session.

**Implemented and tested, disabled on the public deployment**

- Replica reproduce and verify. It is disabled in public on purpose: the replica would run agent-written code next to the toolbox secrets. It needs an unprivileged replica user before it is switched on.

**Demo mode**

- The dashboard has a demo mode (built without `VITE_API_BASE_URL`) that plays an incident end to end with sample data shaped like the API contract. It is used only where we say so; https://app.rootlane.xyz runs in live mode and shows only what the API reports.

## Security notes

- Telemetry stores derived fields only (status, route, timings, auth outcome, derived identity signals). Never passwords, tokens or request bodies.
- Secrets live only in environment variables on each deployment, never in git. This repository is public.
- The agent's tools are read-only by default; the only write path (shipping a fix) requires human approval with an admin token.
- Every agent action is audited.

## Repository layout

```
backend/     toolbox API (Python, FastAPI) and backend/agent/ (Guild agent, TypeScript)  -> api.rootlane.xyz
frontend/    dashboard (Vite + React) and frontend/fixtures/ (API contract samples)      -> app.rootlane.xyz
juiceshop/   Juice Shop fork (submodule), telemetry middleware, patches, Dockerfile        -> juiceshop.rootlane.xyz
docs/        context, design spec, plans, research, diagrams, dashboard contract
```

`backend/` and `juiceshop/` each own their Dockerfile, Akash SDL (`deploy/`) and GitHub Actions workflow; `frontend/` deploys on Vercel.

## Run locally

- Toolbox API and agent: [backend/README.md](backend/README.md)
- Dashboard (live or demo mode): [frontend/README.md](frontend/README.md)
- Design: [docs/superpowers/specs/2026-10-09-rootlane-design.md](docs/superpowers/specs/2026-10-09-rootlane-design.md)
- Dashboard API contract: [docs/ui/dashboard-contract.md](docs/ui/dashboard-contract.md)

## Product vision

Rootlane as a product connects to a company's stack at five points:

1. **Telemetry**: a lightweight SDK or an OpenTelemetry exporter sends derived request and auth events.
2. **Code**: a GitHub App gives read access to the source and opens fix PRs.
3. **Knowledge**: the company's security policies and runbooks are loaded into Senso as verified context.
4. **Deploy**: a deploy hook ships the approved fix through the company's own pipeline.
5. **Approvals**: named approvers decide in the dashboard; nothing reaches production without them.

![Product integration](docs/diagrams/4-product-integration.png)

# Rootlane

**An autonomous security agent that watches a live app, investigates what looks wrong, and proves
a fix before a human ships it.** It reads behaviour as it happens and escalates what does not add
up. A human gets the evidence, a verified patch and a prevention rule, and decides.

Python · FastAPI · TypeScript · React · ClickHouse · Guild · Akash · AkashML · Senso · Semgrep · Vercel · Cloudflare

[Dashboard](https://app.rootlane.xyz) · [Watched app (OWASP Juice Shop)](https://juiceshop.rootlane.xyz) · [Rootlane API](https://api.rootlane.xyz/healthz)

---

## What it does

```text
  Juice Shop (Akash)        every ~10 s                          on escalate
        │                        │                                    │
        ▼                        ▼                                    ▼
    telemetry  ──►  Rootlane API  ──►  ClickHouse  ──►  analyzer  ──►  incident
                      (Akash)                         AkashML, GLM-5.3
                                                      + deterministic identity rule
                                                                      │
        ┌─────────────────────────────────────────────────────────────┘
        ▼
   Guild agent (claude-opus-5)  ──►  read-only queries · source reads · Semgrep · Senso policies
        │
        ▼
   isolated replica  ──►  proposal  ──►  a human approves  ──►  a PR on the fork
   reproduce, verify                     on the dashboard
                                         (Vercel)
```

Two kinds of decision are made by an LLM: **the triage verdict** on each window of behaviour, and
**the investigation and the patch** once an incident is open. Everything around them is a fixed
pipeline — ingest, window features, the deterministic identity rule, the verification gates —
because those steps must behave the same on every run.

Detection, investigation and shipping are deliberately separate acts. The analyzer can open an
incident; the agent can only read, query and scan; only a named human approval ships a fix.
Nothing unverified is proposed.

---

## The problem

Broken Access Control is #1 in the OWASP Top 10:2025:

> "100% of the applications tested were found to have some form of broken access control."
> — [OWASP A01:2025 Broken Access Control](https://top10.owasp.org/2025/A01_2025-Broken_Access_Control)

Detectors raise alerts; someone still has to find the root cause, prove a fix and ship it.

---

## The live run, end to end

Incident `inc_20261009234748`, on the live system, 2026-10-09 23:47–23:50 UTC:

1. **Streamed** — telemetry from Juice Shop flowed into ClickHouse.
2. **Escalated** — the continuous analyzer fired on a deterministic identity rule: *authenticated
   responses for a principal with no prior login from that client*.
3. **Started** — an incident opened, and Guild started the investigating agent automatically
   through its API trigger.
4. **Queried** — the agent ran 4 read-only queries over the telemetry.
5. **Read** — 4 source files: `lib/insecurity.ts`, `routes/login.ts`, `routes/verify.ts`,
   `routes/userProfile.ts`.
6. **Scanned** — Semgrep returned 3 findings on that code.
7. **Reproduced** — the issue on an isolated replica (HTTP 200).
8. **Rejected** — the verifier refused the agent's first patch and rule drafts. That is the
   guardrail working: nothing ships unverified. Patch verification is the step we are hardening now.

Every tool call is audited in ClickHouse with its agent session id.

---

## How the pieces connect

| Component | What it does here |
| --- | --- |
| Juice Shop | The watched app, with a telemetry middleware, running on Akash. |
| Rootlane API | Ingests telemetry, runs the analyzer, opens incidents, streams them to the dashboard over Server-Sent Events, and exposes the scoped tools the agent calls. Runs on Akash with its replica sandbox. |
| ClickHouse | Telemetry, window features in SQL, verdicts, incidents and the agent audit log. |
| AkashML | Hosts GLM-5.3, which returns a verdict and a one-line rationale every ~10 s. |
| Guild | Hosts, scopes and traces the investigating agent on claude-opus-5; its API trigger starts a session on every escalation. |
| Senso | The verified policy and runbook documents the agent searches and cites. |
| Semgrep | Scans the code under investigation, checks the patch closes the finding, and backs the prevention rule. |
| Vercel | Hosts the dashboard, where a human reviews the evidence and approves or rejects. |
| Cloudflare | DNS and edge for the three `rootlane.xyz` hosts. |

The diagrams and their Mermaid sources are in [docs/diagrams/](docs/diagrams/README.md):
[internal pipeline](docs/diagrams/5-internal-pipeline.png) ·
[system architecture](docs/diagrams/1-system-architecture.png) ·
[incident lifecycle](docs/diagrams/3-incident-lifecycle.png) ·
[product integration](docs/diagrams/4-product-integration.png).

---

## Security by design

- **Derived telemetry only:** status, route, timings, auth outcome and identity signals. Never
  passwords, tokens or request bodies.
- **Read-only, scoped tools:** the agent holds one least-privilege key; queries, source reads and
  scans cannot write.
- **Human approval gate:** shipping a fix requires a named admin decision in the dashboard.
- **Full audit trail:** every agent tool call is stored with its agent session id.
- **Replica isolation:** reproductions and patches run on an ephemeral replica, never on the live app.
- **No secrets in git:** they live only in each deployment's environment. This repository is public.

---

## Repository

```text
backend/     Rootlane API (Python, FastAPI) + backend/agent/ (Guild agent, TypeScript)  -> api.rootlane.xyz
frontend/    dashboard (Vite + React) + fixtures/ (API contract samples)                -> app.rootlane.xyz
juiceshop/   Juice Shop fork (submodule), telemetry middleware, patches, Dockerfile      -> juiceshop.rootlane.xyz
docs/        design spec, diagrams, research, dashboard contract
```

| Document | What it covers |
| --- | --- |
| [`backend/README.md`](backend/README.md) | running the API and the agent |
| [`frontend/README.md`](frontend/README.md) | running the dashboard |
| [`docs/diagrams/README.md`](docs/diagrams/README.md) | every diagram and its Mermaid source |
| [`docs/superpowers/specs/2026-10-09-rootlane-design.md`](docs/superpowers/specs/2026-10-09-rootlane-design.md) | the design and the decisions behind it |

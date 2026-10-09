# Rootlane — design

From production evidence to a reproduced incident and a verified fix.

Date: 2026-10-09 · Event: Cyberdefense Hackathon #SFTechWeek · Submission: 4:30 PM PT

## Goal

An autonomous security agent, hosted on Guild, that watches a deployed web application through
ClickHouse, investigates an identity attack, reproduces it against an ephemeral replica, writes a
fix, proves the fix closes the attack without breaking the app, and — after a named human approves —
ships it: pull request, patched production, a Semgrep rule that blocks the pattern, and the lesson
stored in Senso.

Success for the demo: a judge watches a forged-token attack hit the live site, sees the incident
open on its own, follows the agent's evidence, clicks approve, and replays the same attack against
production to get `401` instead of `200`. Everything runs on public URLs under our domain.

## Out of scope today

Arbitrary incident types, cloning cloud accounts, multi-tenant onboarding, rebuilding container
images on approval (stretch), Langfuse (Guild's session log plus `agent_actions` cover tracing).

## Components

| Unit | Runs on | Responsibility |
|---|---|---|
| `target` | Akash, `juiceshop.rootlane.xyz` | OWASP Juice Shop from source (our fork) plus a telemetry middleware that ships every request and auth event to ClickHouse. |
| `toolbox` | Akash, `api.rootlane.xyz` | Public HTTPS API that is the agent's only way to act. Owns the sandbox replica, the incident store and the approval gate. Supervises the `target` and `sandbox` processes. |
| `detector` | inside `toolbox` | Runs detection SQL every few seconds, triages hits with an AkashML open model, opens an incident and starts a Guild session. |
| `agent` | Guild | `AUTO_MANAGED_STATE` TypeScript agent on Claude. Investigates, reproduces, patches, verifies, proposes, waits for approval, applies. |
| `ui` | `app.rootlane.xyz` | Incident console: live attack timeline, agent steps, evidence before/after, diff, approve button. |
| ClickHouse Cloud | managed | `http_requests`, `auth_events`, `detections`, `incidents`, `agent_actions`. |
| Senso | managed | Verified context: runbooks, auth policy, past incidents. Read before writing; lesson written after; report checked with `evals` (`kb_accuracy`). |
| Semgrep | CLI in `toolbox`, Guardian in our editors | Scan, patch verification, custom rule, variant hunt. |

`target` and `sandbox` run as two processes inside the `toolbox` deployment: `target` serves the
public site, `sandbox` is a throwaway copy on an internal port, rebuilt per verification from the
current production source plus the candidate diff. The demo calls it an ephemeral replica, not a
VM-level sandbox.

## The incident (one, end to end)

Juice Shop's "Unsigned JWT" flaw: `lib/insecurity.ts` verifies tokens without pinning the
algorithm, so a token with `alg: none` claiming another user's email is accepted.

- Attack: request an authenticated endpoint with an unsigned token for `jwtn3d@juice-sh.op`.
- Telemetry: the middleware decodes the presented token's header and claims (never trusting them)
  and records `jwt_alg`, `claimed_identity`, `principal_resolved`, status, route, IP, `trace_id`.
- Detection SQL: authenticated responses (`2xx`) whose token algorithm is not the server's signing
  algorithm, or whose claimed identity has no prior successful login.

## Toolbox API (imported into Guild as one integration, API-key auth)

| Operation | Contract |
|---|---|
| `POST /tools/query_events` | `{sql}` → rows. Read-only ClickHouse user, `max_result_rows=200`, `max_execution_time=5`. |
| `POST /tools/read_source` | `{path}` → file contents from production source (repo-relative, no `..`). |
| `POST /tools/semgrep_scan` | `{config?, paths?}` → findings (JSON). |
| `POST /tools/reproduce` | `{incident_id}` → runs the recorded exploit against a fresh sandbox of production: status, response excerpt. |
| `POST /tools/verify_patch` | `{incident_id, diff, rule_yaml}` → applies diff to a sandbox copy, rebuilds, runs exploit, regression smoke suite, `semgrep` with the new rule (must fire on old code, stay silent on new). Returns each result. |
| `POST /tools/propose` | `{incident_id, report, diff, rule_yaml}` → stores the proposal, status `pending_approval`. Refused unless the last `verify_patch` for this diff passed. |
| `POST /tools/apply` | `{incident_id}` → refused unless a human approved this exact proposal in the UI. Opens the PR on our fork, patches and restarts `target`, replays the exploit against production, runs the rule across the repo for variants. |

Every call writes an `agent_actions` row: Guild session id, operation, arguments hash, outcome, and
the identity it acted on behalf of.

The approval gate lives in `toolbox`, not in the prompt: `apply` checks the stored approval
(approver name, timestamp, proposal hash). The agent asks for approval with `task.ui.prompt` and
also polls proposal status, so a UI approval unblocks it whether or not a Guild follow-up event
reaches the pending prompt.

## Agent loop

1. Read the incident and the detection rows; pull the timeline with `query_events`.
2. Ask Senso for the auth policy and any related past incident before touching code.
3. Read the implicated source, run Semgrep, form a hypothesis with cited evidence.
4. `reproduce`. If the exploit does not reproduce, report that and stop.
5. Write diff and rule; `verify_patch`. Up to three attempts; on failure, report what failed and stop.
6. Check the report against Senso with `evals`; `propose`; ask for approval.
7. On approval, `apply`; write the lesson to Senso.

Outcomes are explicit: `not_reproduced`, `fix_failed`, `pending_approval`, `rejected`, `applied`.
The agent never claims a fix it did not verify.

## Sponsor use (submission text)

Guild hosts and runs the agent, holds the toolbox and Senso credentials, logs every call.
ClickHouse is the real-time backbone: ingest, detections, attack timeline, agent audit.
Akash hosts the target, toolbox and sandbox; AkashML triages detections before the expensive model wakes.
Semgrep scans, verifies the patch and ships a custom rule; Guardian guarded the code we wrote today.
Senso is the verified context the agent reads before it writes and where the lesson is kept.

## Deployment

Images built locally and pushed to a public registry; Akash SDL with `accept:` hostnames and
CNAMEs under `rootlane.xyz`. Secrets as Akash env vars. `ui` on Akash or Vercel, whichever is up first.

## Testing

- Exploit script: returns `200` on vulnerable code, `401` on patched — this is the acceptance test.
- Toolbox: unit tests for the read-only SQL guard, path guard, approval gate, propose-before-verify refusal.
- Detection SQL tested against recorded attack and benign traffic.
- Regression smoke suite: login, product search, basket, authenticated profile with a valid token.

## Open items

- DNS: move `rootlane.xyz` nameservers from Porkbun to a free Cloudflare zone (proxy + HTTPS in front of Akash).
- Accounts: ClickHouse (`SIGNUP100`, new email), Guild, Senso, AkashML, Akash Console, Anthropic key for Guild.
- Confirm with `guild agent capabilities` the generated tool names and whether a posted event answers `task.ui.prompt`.

## Decisions (2026-10-09, supersede earlier sections where they differ)

- **Stack.** `toolbox` in Python 3.12 + FastAPI, managed with `uv`. `agent` in TypeScript on Guild (the only runtime Guild hosts). Dashboard in Vite + React, deployed on its own.
- **Models.**
  - Investigating agent: Claude through Guild's managed LLM access (account has a 50M Guild-token balance; no own provider key needed). Model chosen in the agent's `llmPreferences`: `claude-opus-5` (the frontier tier listed in Guild's pricing table).
  - Continuous analysis: AkashML open model (`zai-org/GLM-5.3` via the OpenAI-compatible API at `https://api.akashml.com/v1`). Model and base URL come from env (`TRIAGE_BASE_URL`, `TRIAGE_MODEL`, `TRIAGE_API_KEY`) so it can switch to another provider without code changes.
- **Continuous analysis instead of fixed alerts.** Every `ANALYZE_INTERVAL_S` the toolbox computes generic behavioural features over a sliding window in ClickHouse (per principal and per IP) and sends the summary to the triage model, which answers `ignore`, `watch` or `escalate` with a rationale. Only `escalate` opens an incident and starts a Guild session. Every verdict is stored and shown on the dashboard.
- **Demo scenarios.** Three weaknesses already present in Juice Shop — one identity, one injection, one authorization. Nothing in the analyzer or the agent is specific to them.
- **Telemetry never stores passwords, tokens or request bodies**, only derived fields.
- **Image build.** GitHub Actions builds the Docker image and pushes it to GHCR (`ghcr.io/djimenezm2/rootlane`); no local Docker needed.
- **Dashboard API** is fixed by `docs/ui/dashboard-contract.md` and `ui/fixtures/`.
- **Three separate deployments**, each its own app and Akash deployment: `juiceshop.rootlane.xyz` (Juice Shop from our fork plus the telemetry middleware), `api.rootlane.xyz` (toolbox, which also holds the ephemeral replicas built from the fork source), `app.rootlane.xyz` (dashboard, static). The middleware sends telemetry to `https://api.rootlane.xyz/internal/events` authenticated with `INGEST_TOKEN`. The toolbox allows CORS from `https://app.rootlane.xyz`. Applying an approved fix opens the PR on the fork and redeploys the Juice Shop app from the patched source (new image tag, Akash deployment update); it no longer restarts a process inside the toolbox.
- **Live updates.** The dashboard receives the analyzer verdicts and the agent's steps as they happen over Server-Sent Events (`GET /api/stream`), falling back to polling every 2 s. All UI copy in English.
- **Chat with the agent** about an incident is optional, built only after the three core screens work.
- **Jev (TypeSafe AI)** may replace the triage decision if an API key is available today; AkashML then writes the one-line rationale. Without a key, AkashML does both.
- **Guild trigger key** can only be created in the web UI after the agent is published to workspace `djimenezm2/hackaton`.

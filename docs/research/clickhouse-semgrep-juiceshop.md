# ClickHouse / Semgrep / Juice Shop research

Research for the autonomous security incident agent (4-hour hackathon build). Every claim is
cited; items I could not verify from a documented contract are labelled `[UNVERIFIED]`.

---

## A. ClickHouse Cloud

### A1. Fastest path to get Node/Express HTTP + auth logs into ClickHouse Cloud in real time

**Recommendation for a 4-hour build: use `@clickhouse/client` (the official Node client) doing
batched async `insert` in `JSONEachRow` over HTTPS :8443.** It is the least moving parts: one
npm dependency, direct TLS insert to the Cloud endpoint, no collector/sidecar to deploy.

Client + insert contract (verified, Context7 `/websites/clickhouse`,
https://clickhouse.com/docs/integrations/javascript):

```ts
import { createClient } from '@clickhouse/client'

const client = createClient({
  url: 'https://<service>.clickhouse.cloud:8443', // Cloud HTTPS port is 8443 (secure=true)
  username: 'default',
  password: process.env.CLICKHOUSE_PASSWORD,
})

await client.insert({
  table: 'access_log',
  values: [{ ts: ..., method: 'POST', path: '/rest/user/login', status: 401, user: null }],
  format: 'JSONEachRow',
})
```

- Port 8443 = ClickHouse Cloud secure HTTPS interface (verified via the Airflow connector doc
  showing `"port": 8443, "secure": true` against `*.clickhouse.cloud`,
  https://clickhouse.com/docs/integrations/connectors/data-ingestion/etl-tools/airflow-and-clickhouse).
- For real-time throughput, enable client-side **async inserts** (set
  `async_insert: 1, wait_for_async_insert: 0` in client settings) so many small HTTP inserts are
  batched server-side. `[UNVERIFIED exact flag names for the JS client — confirm in the client
  async-insert docs; the server settings async_insert/wait_for_async_insert are standard.]`

The three alternatives, ranked for this build:

| Option | When it wins | Why NOT for 4h |
|---|---|---|
| `@clickhouse/client` direct JSONEachRow /8443 | **chosen** — raw HTTP access + auth events from our own Express middleware | — |
| Direct HTTP `POST ?query=INSERT ... FORMAT JSONEachRow` (no client lib) | zero deps, curl-able | you reimplement retries/compression/auth the client already gives you |
| OTel Collector ClickHouse exporter | you already emit OTLP | extra collector process to configure and run |
| ClickStack (HyperDX + OTel + ClickHouse + Mongo) | full observability UI wanted | 4 Docker images incl. Mongo; heavy for 4h (https://clickhouse.com/docs/use-cases/observability/clickstack) |

Note: our target app (Juice Shop) already writes **morgan `combined`** access logs to
`logs/access.log.%DATE%` (see C2). Simplest capture = our own thin Express middleware OR a tail of
that file shipped via the Node client. Avoid ClickStack unless we want the HyperDX UI as a demo
surface.

### A2. Real-time detection + firing an external webhook

**ClickHouse has NO native outbound webhook / push to an external URL.** Confirmed indirectly: the
official materialized-view and refreshable-MV docs describe only in-database transforms; the
alerting patterns that call webhooks all run an external worker. `[Confirmed-by-absence: no
official ClickHouse "webhook"/"HTTP sink from MV" feature found; the vendor alerting guides
(OneUptime, https://oneuptime.com/blog/post/2026-03-31-clickhouse-real-time-alerting/view) all put
the HTTP call in an app/script outside the DB.]`

Detection building blocks (docs):
- **Incremental materialized view** — fires on every INSERT into the source table, writes
  aggregates to a target table. Best for continuous per-event / rolling aggregation. Real-time.
  (https://clickhouse.com/docs/best-practices/use-materialized-views)
- **Refreshable materialized view** (`REFRESH EVERY <interval>`) — re-runs a full query on a
  schedule and atomically swaps results; introduced experimental in 23.12
  (https://clickhouse.com/blog/clickhouse-release-23-12). Good for periodic threshold evaluation,
  NOT sub-second. Status via `system.view_refreshes` (last_success_time, next_refresh_time,
  exception). On refresh failure the view keeps the last good data — so a detector can act on stale
  rows; monitor the status table.
- **Polling query** — simplest: external worker runs a detection SELECT on an interval.

**The common webhook pattern (recommended):** a small external worker (our Node/Guild agent
trigger) polls a detection query — or reads a refreshable-MV results table — on a short interval,
dedups already-fired alerts (keep a seen-set / mark rows), and does the HTTP POST to the agent's
webhook itself. The MV concentrates/flags; the worker fires. For a hackathon, a `setInterval`
poller over a detection view against the read-only user is enough.

### A3. Read-only user/role for the agent (verified, Context7 `/websites/clickhouse`)

Two documented ways:

```sql
-- Simplest: a readonly user
CREATE USER exporter IDENTIFIED WITH SHA256_PASSWORD BY 'password-here' SETTINGS readonly = 1;
GRANT SELECT ON db.table TO exporter;
```
(https://clickhouse.com/docs/get-started/migrate/oss-to-cloud/clickhouse-to-cloud)

```sql
-- Role-based, with query-complexity caps (good to bound the agent)
CREATE USER agent_ro IDENTIFIED WITH sha256_password BY '<pw>';
CREATE ROLE agent_reader SETTINGS max_result_rows = 1000;   -- bound result size
GRANT SELECT ON default.* TO agent_reader;
GRANT agent_reader TO agent_ro;
```
(https://clickhouse.com/docs/resources/support-center/knowledge-base/configuration-settings/about-quotas-and-query-complexity)

`SETTINGS readonly = 1` blocks writes and DDL; role SETTINGS (`max_result_rows`, and similarly
`max_execution_time`, `max_memory_usage`) bound what the agent can run — directly satisfies the
"read-only, bounded" requirement.

### A3b. ClickHouse Cloud remote MCP server (for the agent)

- Endpoint once enabled: **`https://mcp.clickhouse.cloud/mcp`**
  (https://clickhouse.com/docs/cloud/features/ai-ml/remote-mcp).
- **Enable per service** in the Cloud console: open the service → Connect → choose MCP → enable.
  It is a per-service toggle.
- **Auth = OAuth 2.0**: on first connect the client opens a browser to sign in with ClickHouse
  Cloud credentials; access is scoped to the orgs/services the signed-in user may use.
- Claude Code: add the server, then `/mcp` → authenticate → select the `clickhouse_cloud` server.
- `[UNVERIFIED currency: a 2025 AWS blog + a zh doc still call it private preview; the current
  English docs present it as a standard toggle. Treat the English docs as current.]`

For our agent we likely want the **read-only user over the normal client** for detection polling,
and optionally the remote MCP server as the agent's investigation query surface.

### A4. Langfuse (agent tracing; stores traces in ClickHouse)

- Langfuse **v3+ uses ClickHouse** as its trace store, and **ClickHouse Cloud is an officially
  supported option** (https://langfuse.com/self-hosting/infrastructure/clickhouse).
- Self-hosted Langfuse CAN point at ClickHouse Cloud. Required env is a **TCP** migration URL:
  `CLICKHOUSE_MIGRATION_URL=clickhouse://<host>:9440` (9440 = native TLS; 9000 = native plain) —
  note this is the native protocol, NOT the 8443 HTTPS port used for our own inserts. ClickHouse
  vars must be given to BOTH the `web` and `worker` containers. Optional `CLICKHOUSE_READ_ONLY_URL`
  (falls back to `CLICKHOUSE_URL`) is "primarily useful on ClickHouse Cloud / BYOC"
  (https://langfuse.com/self-hosting/configuration).
- Version/ClickHouse-version coupling: v3 needs ClickHouse 24.3+; v4 needs 25.12+ (26.4
  recommended). Check the Langfuse version before picking. `[verified from the v3 config +
  clickhouse self-hosting pages.]`

**Hackathon recommendation: use Langfuse Cloud, not self-host.** Self-hosting v3 means standing up
web + worker + ClickHouse + Redis + S3/MinIO — far too much for 4h. Langfuse Cloud has a free tier
and the same SDKs. Only self-host-against-Cloud-ClickHouse if a sponsor requirement forces all data
into our own ClickHouse. `[Langfuse Cloud free-tier existence is from general knowledge; confirm at
langfuse.com/pricing. UNVERIFIED.]`

- TS tracing: Langfuse ships a TypeScript SDK and is **OpenTelemetry-based** (v3/v4 SDK is built on
  OTel), so an OTel-instrumented TS agent exports spans to Langfuse. `[Integration exists; exact
  current SDK package/version UNVERIFIED — check langfuse.com/docs for the JS/TS SDK + OTel
  exporter setup.]`

---

## B. Semgrep

### B1. Semgrep Guardian (Claude Code plugin)

- **What it is:** a Claude Code plugin that bundles the **Semgrep MCP server + hooks + skills**.
  It scans every file the agent generates with Semgrep Code, Supply Chain, and Secrets
  (https://docs.semgrep.dev/semgrep-guardian/overview).
- **How findings surface:** a **post-tool hook** runs after each file write; when findings appear
  the agent is prompted (finding context returned into the session) to regenerate the code until
  Semgrep is clean, or you dismiss them. Skills interpret a finding and describe remediation.
- **Rulesets:** the default **remote** server uses the default Guardian ruleset (not configurable).
  A **local** setup scans with the rules enabled in your Semgrep org Policies.
- **Install:** docs/product show `/plugin marketplace add semgrep/guardian` then
  `/plugin install semgrep@semgrep-marketplace`, then log in to Semgrep. The brief's
  `claude plugin install semgrep@claude-plugins-official` is a different marketplace alias —
  `[UNVERIFIED which marketplace alias is current; try the brief's form first, fall back to the
  docs' `semgrep/guardian` marketplace.]`
- Raw finding JSON shape not documented on these pages. `[UNVERIFIED]`

For our story, Guardian is the "Semgrep runs inside Claude Code as the agent writes the fix" piece;
the CLI below is the "agent runs Semgrep as a tool / writes a custom rule" piece.

### B2. Semgrep CLI / OSS + custom rule + MCP

- **Install:** `python3 -m pip install semgrep` (also Homebrew, or Docker `semgrep/semgrep`)
  (https://docs.semgrep.dev/customize-semgrep-ce).
- **Run a custom rule:** `semgrep --config custom_rule.yaml <path>` (or `--config <dir>`).
- **JSON output:** `semgrep --config rule.yaml --json <path> > results.json` (SARIF also available).
  This is the machine-readable form the agent parses.
- **Test rules:** official form is `semgrep scan --test` (newer CLI uses the `scan` subcommand);
  older `semgrep --test --config rule.yaml <testdir>` still seen. Tests use `# ruleid:` and `# ok:`
  annotation comments next to lines that should / should not match.
  `[Conflicting forms across sources; check `semgrep --version` and use `semgrep scan --test` on
  recent builds.]`
- **Semgrep MCP server:** PyPI package **`semgrep-mcp`** (install via pip/pipx/uv; Docker:
  `docker run -i --rm semgrep/semgrep semgrep mcp -t stdio`). Default transport **stdio**;
  `-t streamable-http` listens on `127.0.0.1:8000/mcp` (SSE deprecated). Exposes scanning tools and
  resources incl. `semgrep://rule/schema` (rule YAML spec). Optional `SEMGREP_APP_TOKEN` env for
  AppSec Platform features. (https://github.com/semgrep/mcp per lobehub mirror — `[exact tool
  names UNVERIFIED from docs]`.)

### B3. Example custom rule — JWT verification flaw in Node

Targets the exact Juice Shop pattern: using `jws.decode`/`jwt.decode` (no signature check) for
authorization decisions, and not pinning `algorithms`. Written against the documented Semgrep rule
schema; **validate with `semgrep scan --test` before trusting it.** `[Rule authored from the schema
+ jsonwebtoken/jws API knowledge; UNVERIFIED by running.]`

```yaml
rules:
  - id: jwt-decode-used-for-authz
    languages: [typescript, javascript]
    severity: ERROR
    message: >
      JWT payload is read with decode() (no signature verification) and used for an
      authorization decision. Use jwt.verify()/jws.verify() with the signature checked,
      and pin algorithms. decode() must never gate access.
    patterns:
      - pattern-either:
          - pattern: jwt.decode(...)
          - pattern: jws.decode(...)

  - id: jwt-verify-algorithms-not-pinned
    languages: [typescript, javascript]
    severity: ERROR
    message: >
      jwt.verify() called without an algorithms allowlist. An attacker can downgrade to
      alg:none or confuse RS256/HS256. Pass { algorithms: ['RS256'] }.
    patterns:
      - pattern: jwt.verify($TOKEN, $KEY)
      - pattern-not: jwt.verify($TOKEN, $KEY, { ..., algorithms: [...], ... })
```

(Rule anatomy — id/languages/severity/message/pattern, pattern-either, pattern-not — per
https://docs.semgrep.dev/customize-semgrep-ce.)

---

## C. OWASP Juice Shop

### C1. JWT / identity challenges, where the flaw lives, how to exploit

Verified from `data/static/challenges.yml` and `lib/insecurity.ts` (raw on `master`):

| Challenge | key | diff | What it proves |
|---|---|---|---|
| **Forged Signed JWT** | `jwtForgedChallenge` | 6 | Forge an RSA-signed JWT impersonating `rsa_lord@juice-sh.op`. Hint: you need the public RSA key and must exploit a weakness in the JWT libraries, NOT the private key. (Disabled on Windows.) |
| **Unsigned JWT** | `jwtUnsignedChallenge` | 5 | Forge an essentially unsigned JWT impersonating `jwtn3d@juice-sh.op`. Hint: start from a valid token and use a signing option that disables encryption (`alg: none`). |

There is **no "Forged Unsigned JWT"** challenge; the two are *Forged Signed JWT* and *Unsigned JWT*.
They sit under the **Vulnerable Components** category, not a "JWT Issues" category.

**The flaw in `lib/insecurity.ts`** (line numbers approximate; counted from file top):
- `publicKey` loaded from `encryptionkeys/jwt.pub` (~L20); **`privateKey` is hardcoded in the
  source** (~L21) — anyone with the repo can sign RS256 tokens.
- `verify(token)` uses `jws.verify` against `publicKey` (~L55) and **does NOT pin the algorithm and
  does NOT check expiry**.
- `decode(token)` uses `jws.decode` — **reads the payload without verifying the signature** (~L56).
- Role checks `isAccounting` / `isDeluxe` / `isCustomer` (~L153–170) call `verify` then `decode`.
- `authorize` signs with `jwt.sign(..., { algorithm: 'RS256', expiresIn: '6h' })` (~L54).

Mechanism of the two exploits:
- **Unsigned JWT:** the `jws`/`jsonwebtoken` verify path accepts `alg: none` because no algorithm
  allowlist is enforced. Take a valid `Authorization: Bearer <h>.<p>.<s>`, rewrite the header to
  `{"alg":"none","typ":"JWT"}`, set payload `email` to `jwtn3d@juice-sh.op`, drop the signature
  (trailing dot, empty sig), resend. (Steps from the Juice Shop issue tracker,
  https://github.com/juice-shop/juice-shop/issues/1788; "none" acceptance background:
  https://portswigger.net/kb/issues/00200901_jwt-none-algorithm-supported.)
- **Forged Signed JWT:** classic **RS256→HS256 key-confusion** — because `algorithms` is not
  pinned, sign a token with **HS256 using the public key bytes (`jwt.pub`) as the HMAC secret**,
  payload `email = rsa_lord@juice-sh.op`; the server verifies HS256 with the public key as the
  secret and accepts it. (Challenge hint says "exploit a weakness in the JWT libraries," matching
  key confusion; general technique: https://pentesterlab.com/blog/jwt-vulnerabilities-attacks-guide.)
  `[Exact exploit for this specific challenge version UNVERIFIED end-to-end; mechanism is
  confirmed by the challenge hint + the unpinned-algorithm code.]`

Exploited endpoint: any authenticated REST route, e.g. `GET /rest/user/whoami` or any route behind
`isAuthorized`, carrying the forged `Authorization: Bearer <token>`. `[exact detection route for
each challenge UNVERIFIED — the challenge is marked solved by the impersonated email in the
payload, per issue #1788.]`

### C2. Does Juice Shop log access requests? (verified from `server.ts`)

**Yes — morgan.** `app.use(morgan('combined', { stream: accessLogStream }))` in `configureApp`,
after body parsers, before rate-limit/authz. Stream is `file-stream-rotator`:
- filename `logs/access.log.%DATE%` (absolute), `date_format YYYY-MM-DD`, `frequency daily`,
  `max_logs '2d'`, `audit_file logs/audit.json`.
- Logs also exposed over HTTP: `/support/logs` (dir listing) and `/support/logs/:file`.

**Capture to ClickHouse without forking heavily — options, easiest first:**
1. **Tail `logs/access.log.*`** with a tiny sidecar (Node `tail` or `tail -F | ...`) that parses the
   morgan `combined` line and inserts via `@clickhouse/client`. Zero source changes.
2. **Add one Express middleware** early in our own copy (small, surgical patch) that posts a
   structured JSON event (method, path, status, user from JWT, latency) to ClickHouse — richer than
   combined-format text, and lets us emit auth-specific events.
3. **Reverse proxy** (nginx/Caddy) in front writing JSON access logs, shipped to ClickHouse — no
   app changes but another process; heavier than (1).

For auth/identity *events* specifically (login success/fail, token issued), option 2 (a small
middleware around the login/authz paths) is the cleanest — morgan only sees HTTP lines, not
semantic auth outcomes.

### C3. Running from source vs Docker; build time

- Build toolchain is a standard `npm install` + `npm run build:*` (Angular frontend + TS server).
  Needs the Node version in `package.json engines` — `[not captured here; check package.json. Recent
  Juice Shop targets Node 20/22. UNVERIFIED exact range.]`
- **Docker** (`bkimminich/juice-shop` / `docker run -p 3000:3000`) is the fastest *to just run*,
  but the image is prebuilt — patching source then needs a rebuild of the image, which recompiles
  the Angular frontend (the slow part, minutes).
- **From source** is what we need since we patch `lib/insecurity.ts` and re-run. `npm install` is
  the one-time slow step (several minutes, large dep tree); after that, a server-only change can run
  with a TS watch/`npm start` quickly, but a **full `npm run build:frontend` is the multi-minute
  cost** on each frontend-affecting change. Our JWT fix is server-side (`lib/insecurity.ts`), so
  after the initial install+build, iterating on the fix is a server restart, not a frontend rebuild.
  `[Build-time figures are general-knowledge estimates; UNVERIFIED — measure the first install/build
  on our box and budget ~5–10 min for the initial full build.]`

---

## Key sources
- ClickHouse JS client / inserts: https://clickhouse.com/docs/integrations/javascript
- ClickHouse Cloud 8443/secure: https://clickhouse.com/docs/integrations/connectors/data-ingestion/etl-tools/airflow-and-clickhouse
- Read-only user/role: https://clickhouse.com/docs/get-started/migrate/oss-to-cloud/clickhouse-to-cloud ; https://clickhouse.com/docs/resources/support-center/knowledge-base/configuration-settings/about-quotas-and-query-complexity
- Materialized views: https://clickhouse.com/docs/best-practices/use-materialized-views ; refreshable MV release https://clickhouse.com/blog/clickhouse-release-23-12
- ClickHouse Cloud remote MCP: https://clickhouse.com/docs/cloud/features/ai-ml/remote-mcp
- ClickStack: https://clickhouse.com/docs/use-cases/observability/clickstack
- Langfuse self-host ClickHouse: https://langfuse.com/self-hosting/infrastructure/clickhouse ; config https://langfuse.com/self-hosting/configuration
- Semgrep Guardian: https://docs.semgrep.dev/semgrep-guardian/overview
- Semgrep customize/CLI: https://docs.semgrep.dev/customize-semgrep-ce
- Semgrep MCP: PyPI `semgrep-mcp` / https://github.com/semgrep/mcp
- Juice Shop source: lib/insecurity.ts, server.ts, data/static/challenges.yml (raw on master)
- Juice Shop JWT issue: https://github.com/juice-shop/juice-shop/issues/1788

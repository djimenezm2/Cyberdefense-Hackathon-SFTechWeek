# Senso and AkashML / Akash Network: research report

Researched 2026-10-09 from official docs. Context7 has no Senso library (resolve returned only
unrelated "Sensors" libraries); Senso facts come from docs.senso.ai (`llms-full.txt` and the
OpenAPI spec `specs/sdk-api.yaml` v0.2.0). AkashML facts come from akashml.com/docs (markdown pages
and `docs/llms-full.txt`). Akash Network facts come from Context7 `/websites/akash_network` and
akash.network/docs. Anything not verified is labelled **UNVERIFIED**.

---

## A. Senso

### A1. What it is

- A knowledge base ("context layer") that people and agents write to and search; answers cite the
  documents they came from. "Shared context is knowledge that people and their agents retrieve,
  use and improve together." https://docs.senso.ai/docs/shared-context
- Three surfaces: REST API, MCP server, CLI (+ "agent skills" that teach a coding agent to drive
  the CLI). https://docs.senso.ai/docs/mcp-server (table "When to use it")

### REST API

- Base URL: `https://apiv2.senso.ai/api/v1`. Auth header: `X-API-Key: <key>` (keys look like
  `tgr_...`). https://docs.senso.ai/docs/quickstart
- Check key: `GET /org/me` -> `{org_id, name, slug, is_free_tier, ...}`.
- A key has the full permissions of its org (ingest, search, generate, publish) unless restricted
  to folders/viewer. https://docs.senso.ai/docs/api-keys

Ingest markdown / raw text (the only way for markdown; md/txt are NOT accepted as file uploads):

```
POST /org/kb/raw
{"title": "Refund policy", "text": "<markdown>", "kb_folder_node_id": "<optional folder uuid>"}
-> 202 {"id": "<content_id>", "kb_node_id": "<node uuid>", "type": "raw", "title": "...", "processing_status": "processing"}
```

- Async: poll `GET /org/kb/nodes/{kb_node_id}` (~every 5 s) until `content.processing_status ==
  "complete"` (states pending/processing/complete/failed). Short docs: "within a few seconds".
- Identical text already stored -> `409 Conflict` (dedup). https://docs.senso.ai/docs/quickstart
- Files: `POST /org/kb/upload` (presigned S3 flow), max 10 files per call, formats PDF, TXT, CSV,
  DOC(X), XLS(X), PPT(X), HTML, JSON, XML. "Markdown and plain text: not accepted as a file
  upload — send as text through POST /org/kb/raw or the MCP server." https://docs.senso.ai/docs/limits
- Folders: `POST /org/kb/folders` (CLI `senso kb create-folder`); there is **no "ingest a local
  directory" command** in the CLI reference — a folder of markdown must be looped over
  `kb create-raw` by our code. https://docs.senso.ai/docs/cli-reference (KB section)

Search / answer with citations:

```
POST /org/search            {"query": "..."}  -> {"answer": "<markdown>", "results": [{content_id, title, chunk_text, score, rank}], "total_results"}
POST /org/search/context    {"query": "..."}  -> chunks only, no answer: {content_chunk_id, content_id, kb_node_id, version_id, chunk_text, score, title, ...}, "max_results": 5
POST /org/search/full | /org/search/content | /org/search/stream   (other modes)
```

- `content_id` in each result = the `id` returned at ingest -> citation trail.
- Header `X-Senso-Signals: off` keeps synthetic/test searches out of the "gaps" report.
  https://docs.senso.ai/docs/quickstart, https://docs.senso.ai/docs/mcp-server

Update / version a document:

```
PATCH /org/kb/nodes/{kb_node_id}/raw   {"text": "...", "title"?: "...", "summary"?: "...", "tag_ids"?: [...]}   (any of title/summary/text)
PUT   /org/kb/nodes/{kb_node_id}/raw   {"title": "...", "text": "..."}   (both required; full replace)
```

- Each edit cuts a new version and re-ingests; earlier versions readable (`GET /org/content/{id}/versions`,
  CLI `senso kb get-content <id> --rev 1`). Source: `specs/sdk-api.yaml` paths
  `/org/kb/nodes/{id}/raw`, https://docs.senso.ai/docs/shared-context ("Revise as things change").
- Tags: `senso kb tags set <id> --names "status:approved,owner:X"`; tags are a team convention,
  NOT enforced and NOT returned in search results — write status into the body.
  https://docs.senso.ai/docs/shared-context

Verify claims against the KB (useful for "grounded in truthful sources"):

- `POST /org/evals/text` `{"title","text","evaluator": "kb_accuracy" | "brand_alignment","label"?}`;
  CLI `senso evals text --text-file f --wait`; per-claim verdicts with evidence via
  `/org/evals/runs/{runId}`, `/org/evals/claims`. Spec `sdk-api.yaml` line ~1958; CLI ref
  https://docs.senso.ai/docs/cli-reference ("evals").

Rate limits: no published REST limit; MCP = 60 req/min per key; credits are the real budget
(`402` when out). https://docs.senso.ai/docs/limits

### CLI (`@senso-ai/cli`)

- Install `npm install -g @senso-ai/cli`; `senso setup` (installs agent skills); `senso login`
  (device flow via https://docs.senso.ai/device, produces an org-scoped key that **expires after
  7 days**); `senso login --interactive` takes an existing key; `SENSO_API_KEY` env var skips the
  stored config. https://docs.senso.ai/docs/connect-your-agent
- Commands mirror the API: `senso whoami`, `senso kb create-raw --data '{...}'`, `senso kb get <id>`,
  `senso kb patch-raw <id> --data '{"text": ...}'`, `senso search "<q>"`, `senso search context "<q>"`,
  `senso gaps list`, `senso credits balance`. https://docs.senso.ai/docs/quickstart,
  https://docs.senso.ai/docs/shared-context
- Note (rule-level, not a doc claim): the user's rules forbid installing globally during research;
  for the build, `npx @senso-ai/cli` or the REST API avoids a global install.

### A2. MCP server / SDK

- **MCP server: yes.** `https://apiv2.senso.ai/mcp`, Streamable HTTP, stateless JSON-RPC, POST only.
  Auth: OAuth (claude.ai/ChatGPT connectors) or `X-API-Key` / `Authorization: Bearer <key>`.
  `claude mcp add --transport http senso https://apiv2.senso.ai/mcp --header "X-API-Key: tgr_..."`.
  Tools: `senso_search` (modes answer/context/content/full, max_results 1-20), `senso_list`,
  `senso_find`, `senso_get_doc`, `senso_create_doc`, `senso_update_doc` (text replaces whole body,
  new version), `senso_create_folder`, `senso_rename_node`, `senso_move_node`, `senso_tag_doc`,
  `senso_delete_node`. Retrieved text is wrapped in `<senso_document>` as data-not-instructions.
  MCP does NOT cover generation/publishing. https://docs.senso.ai/docs/mcp-server
- **SDK: no official TS or Python SDK found** in the docs (only the OpenAPI spec
  https://docs.senso.ai/specs/sdk-api.yaml and recipes using plain `requests`; an "OpenAI Agents
  SDK" recipe wraps the REST API as tools: https://docs.senso.ai/docs/openai-agents-sdk). Plan to
  call REST with `fetch` or use the MCP server. (Absence of an SDK: based on full docs text search,
  not an explicit statement.)

### A3. Publish capability

- Yes, but it is GEO (Generative Engine Optimization) content publishing: publish markdown to
  Senso-run domains that AI models read (default `citeables.com`), or custom domains.
  - REST `POST /org/content-engine/publish` `{"raw_markdown": "...", "seo_title": "...",
    "geo_question_id"?, "content_id"? (new version), "summary"?, "publisher_ids"?}` -> 201 published,
    200 created-but-destination-failed. **"Requires the GEO product."** (spec line ~4855)
  - CLI `senso engine publish --data '{...}' [--publisher-ids <id>]`, `senso engine draft`,
    `senso destinations list`, `senso content unpublish <id>`.
    https://docs.senso.ai/docs/cli-reference ("Publish")
  - "An industry's results, prompts, and everything under 'How Senso writes for you' and
    'Generated content' need Senso's GEO product ... Without the product, a request answers 403."
    https://docs.senso.ai/docs/concepts
- **UNVERIFIED** whether a free/new org has the GEO product enabled; expect a possible 403. For the
  security agent, "publish" can be satisfied without GEO by writing the post-incident lesson /
  runbook update into the KB (`/org/kb/raw`) and verifying it with `/org/evals/text`.

### A4. Free tier / signup

- Sign up: https://docs.senso.ai/sign-up (creates account + organization).
  https://docs.senso.ai/docs/overview
- "New organizations get $100 to start." https://docs.senso.ai/docs/developer-faqs/credits
- Ingest, search, evals, generation all consume credits; `GET /org/credits/balance`.
  https://docs.senso.ai/docs/concepts, https://docs.senso.ai/docs/limits
- Per-operation prices not published (credits FAQ). Hackathon-specific credits: not found.

---

## B. AkashML and Akash Network

### B1. AkashML

- OpenAI-compatible base URL: `https://api.akashml.com/v1`; Anthropic-compatible:
  `https://api.akashml.com/anthropic` (`POST /anthropic/v1/messages`, `GET /anthropic/v1/models`).
  https://akashml.com/docs/getting-started/introduction, https://akashml.com/docs/api-reference/anthropic
- Auth (both): `Authorization: Bearer <key>` (keys `akml-...`), created at Settings -> API Keys;
  shown once. `GET /v1/models` without auth -> 401 (probed).
- Anthropic endpoint model IDs replace `/` with `--` (e.g. `zai-org--GLM-5.3`); OpenAI endpoint
  takes slashed IDs. https://akashml.com/docs/api-reference/anthropic
- Tool calling: OpenAI chat completions document `tools`, `tool_choice` (none/auto/required/
  forced), `parallel_tool_calls`, `finish_reason: tool_calls`. Anthropic Messages documents `tools`,
  `tool_choice` (auto/any/tool), `tool_use`/`tool_result` blocks, `stop_reason: tool_use`,
  `thinking`. https://akashml.com/docs/llms-full.txt, sections "Create chat completion" and
  "Create a message (Anthropic shape)"
- Usage example (TS): `new OpenAI({ baseURL: "https://api.akashml.com/v1", apiKey })`, Python
  `Anthropic(api_key=..., base_url="https://api.akashml.com/anthropic")`.
- Models (per 1M tokens, may lag live API) https://akashml.com/docs/platform/models:

| Model ID | Context | In | Out | Notes (https://akashml.com/models) |
|---|---|---|---|---|
| `zai-org/GLM-5.3` | 1M | $1.30 | $4.40 | "tool use across multi-step workflows"; AkashML's Claude Code default for Sonnet tier |
| `moonshotai/Kimi-K3` | 1M | $2.10 | $10.50 | agentic MoE, reasoning; default for Opus tier |
| `Qwen/Qwen3.8-27B` | 262K | $0.45 | $3.20 | VL, agentic |
| `Qwen/Qwen3.6-35B-A3B` | 262K | $0.14 | $1.00 | agentic coding; default for Haiku tier |
| `openai/gpt-oss-120b` | 128K | $0.037 | $0.49 | "agentic tool use", configurable reasoning effort |
| `openai/gpt-oss-20b` | 128K | $0.03 | $0.13 | low-latency tool use |
| `meta-llama/Llama-3.3-70B-Instruct` | 128K | $0.13 | $0.40 | general chat |

  Best for agentic tool calling (judgement from the vendor's own descriptions and its Claude Code
  mapping, not a benchmark): **GLM-5.3** primary, **Kimi-K3** for hard reasoning,
  **gpt-oss-120b / Qwen3.6-35B-A3B** as cheap fast sub-agents. https://akashml.com/docs/guides/claude-code
- Claude Code can run on AkashML via `ANTHROPIC_BASE_URL=https://api.akashml.com/anthropic`,
  `ANTHROPIC_AUTH_TOKEN=akml-...`, `ANTHROPIC_DEFAULT_{SONNET,OPUS,HAIKU}_MODEL`,
  `API_TIMEOUT_MS=3000000`. https://akashml.com/docs/guides/claude-code
- Rate limits: per-key, user-configured (RPM, TPM, max concurrency, expiry). 429 with
  `X-RateLimit-*` and `Retry-After`; 402 = insufficient credits. No platform default numbers
  published. https://akashml.com/docs/getting-started/introduction
- Credits/signup: sign up at akashml.com/login (email/password, Google, GitHub); "Trial credits
  are granted when you verify a payment method during onboarding" (Stripe; **a card is required
  for trial credits**). Trial credits expire. Trial amount **not stated** in docs (UNVERIFIED).
  https://akashml.com/docs/platform/settings

### B2. Akash Network deploy

Fastest path (Console UI): sign up at console.akash.network (Google/GitHub/email), deploy a
template or custom SDL; "1-3 minutes", Hello World "~30 seconds"; service URL appears under the
deployment's URIs. https://akash.network/docs/getting-started/quick-start

Trial/payment:
- "$1 in free credits", no credit card, valid 30 days, **each trial deployment capped at 24 h**.
  https://akash.network/docs/getting-started/quick-start and
  https://akash.network/docs/getting-started/console-onboarding
- Pay-as-you-go by credit card after that. Console API page: payment "Credit card only".
  https://akash.network/docs/api-documentation/console-api/getting-started/
- A search-result summary mentioned "$100 in free credits"; the official quick-start says $1.
  Trust the quick-start ($1). Whether trial accounts may use the Console API: **not stated**
  (UNVERIFIED) — plan on adding a card.

Programmatic deploy (agent can spin up a sandbox): **yes, Console API (managed wallet).**
- Base `https://console-api.akash.network`, header `x-api-key: <key>` (Console -> Settings -> API
  Keys; key = full account access). https://akash.network/docs/api-documentation/console-api/getting-started/
- Flow (https://akash.network/docs/api-documentation/console-api/quickstart/):
  1. `POST /v1/deployments` `{"data": {"sdl": "<SDL yaml string>"}}` -> `.data.dseq` (and `manifest`).
     Current docs: no deposit field, funded from account credits (older example sends
     `deposit: 0.5`; `GET /v1/deployment-funding-config` for current figures).
  2. Poll `GET /v1/bids?dseq=<dseq>` (~every 3 s; docs wait ~30 s) -> `.data[0].bid.id` {dseq, gseq, oseq, provider}.
  3. `POST /v1/leases` `{"manifest"?: "...", "leases": [{"dseq": "<dseq>", "gseq": 1, "oseq": 1, "provider": "<akash1...>"}]}`.
  4. `GET /v1/deployments/<dseq>` -> `deployment`, `leases`, `escrow_account`.
     **Service URI / forwarded-port field not documented on that page (UNVERIFIED)** — check the
     API reference or provider lease-status before relying on it.
  5. `DELETE /v1/deployments/<dseq>` to close.
- CLI alternative `akt` with a console-api context: `akt context create console --network mainnet
  --auth-method console-api --set-current`, `akt console login akt_...`, `akt deploy deploy.yaml`,
  `akt console lease create <dseq> <provider>`, `akt console status <dseq> --watch`. (akt 0.1.x
  needs `--deposit 0.5`.) https://akash.network/docs/developers/deployment/akt/console/

SDL for Juice Shop — adapted from the official nginx SDL in the Console API getting-started
example (structure verified; Juice Shop port 3000 is its documented default; resource sizes are
an **UNVERIFIED estimate**):

```yaml
version: "2.0"
services:
  web:
    image: bkimminich/juice-shop:<pinned tag>
    expose:
      - port: 3000
        as: 80
        to:
          - global: true
profiles:
  compute:
    web:
      resources:
        cpu: { units: 1 }
        memory: { size: 1Gi }
        storage: [ { size: 2Gi } ]
  placement:
    dcloud:
      pricing:
        web: { denom: uact, amount: 10000 }
deployment:
  web:
    dcloud:
      profile: web
      count: 1
```

Time to lease: bids arrive within ~30 s per docs; whole deploy 1-3 min. Decision note: an
Akash lease is minutes, public, and costs credits — fine for "the sandbox runs on Akash" as a
demo step, but a local Docker container is the faster/safer reproduction loop for the exploit test;
Akash is best used for the deployed target / a showcase sandbox.

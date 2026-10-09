# Guild.ai research (for the autonomous security incident agent)

Sources: docs.guild.ai pages fetched as Markdown on 2026-10-09 (index: https://docs.guild.ai/llms.txt),
Context7 `/websites/guild_ai`, npm registry. "VERIFIED" = stated in the cited doc. "INFERRED" = my
reading of documented behaviour, not stated outright. "UNVERIFIED" = not found in docs.

## TL;DR (decision-relevant)

1. Everything runs on Guild's hosted runtime. Even `guild agent test` / `guild agent chat` build an
   *ephemeral version* from your git-tracked files and run it as a session on Guild — there is no
   offline local runtime. Good for the "host and run agents" prize. (https://docs.guild.ai/cli/commands/agent.md, https://docs.guild.ai/cli/getting-started.md)
2. **Agents have no direct internet.** `fetch` cannot connect; only `@guildai/agents-sdk`, `zod` and
   `@guildai-services/*` can be imported; no Node built-ins. Every outbound call goes through a
   Guild integration. (https://docs.guild.ai/guide/sdk-introduction.md#network-isolation)
3. Custom tools = **custom integrations**: a REST base URL (or MCP server URL) + operations
   (manual or imported from OpenAPI 3.0/3.1) + auth (API key / OAuth / none). Each operation
   becomes a tool. Base URL must be public (localhost/private ranges blocked; use ngrok) and is
   **frozen after first publish**. (https://docs.guild.ai/services/create-an-integration.md)
   => Plan: one public HTTPS "toolbox" service of ours (ClickHouse read-only query, Semgrep,
   sandbox exploit run, PR) exposed via OpenAPI as one custom integration.
4. **No built-in per-tool approval flag found.** Human-in-the-loop = `task.ui.prompt(...)` /
   `ui_prompt` (a hook that suspends the agent until the user replies). Approval gate must be
   coded (auto-managed state agent) before the gated tool call. Credential policies
   (ALLOW/DENY per operation/agent/workspace/domain/method) are the enforced guardrail at egress.
5. **No custom OpenAI-compatible base URL for the agent's own LLM.** Providers: Anthropic,
   OpenAI, Google AI, Meta, AWS Bedrock, Fireworks, OpenRouter (BYOK) or Guild-managed tokens.
   AkashML can only be reached as a tool (custom integration) — UNVERIFIED that AkashML is
   available via any of the listed providers. Anthropic is first-class.
6. HTTP trigger exists: **API trigger** -> `POST https://api.guild.ai/v1/workspaces/{owner}/{workspace}/sessions`
   with HTTP Basic `<key_id>:<secret>`, body `{"session_type":"api_trigger","agent_input":{...}}`.
   Trigger API keys are created only in the web UI. (https://docs.guild.ai/platform/api-triggers.md)
7. Containers: `guildai~experimental-coding` integration (`experimental_coding_create/communicate/delete`)
   runs a coding engine in a container built from a registered image + setup script; network is
   open during setup, then **offline** during runtime. (https://docs.guild.ai/sdk/task-object.md#running-code-in-a-container, https://docs.guild.ai/platform/security-architecture.md)
8. `guild setup --provider claude --yes` installs Claude Code skills (`.claude/skills/`) for Guild
   agent development; the CLI also ships an MCP server. (https://docs.guild.ai/cli/commands/setup.md, https://docs.guild.ai/cli/mcp-server.md)
9. Free tier: docs only say "managed" mode draws from a "Guild tokens balance"; no free allowance
   or hackathon credits documented. UNVERIFIED.

---

## 1. Defining and running an agent

**Install / auth** (https://docs.guild.ai/quickstart.md, https://docs.guild.ai/cli/introduction.md)
- Prereq: Node.js 22+ and npm. npm registry confirms `@guildai/cli` 0.27.1, `engines: node >=22`
  (checked with `npm view`, 2026-10-09).
- `npm install -g @guildai/cli` (note: global install — the user's call; we did not install).
- `guild auth login` (browser OAuth; also configures your local npm registry for Guild packages);
  headless: `guild auth login --non-interactive` prints a URL. CI: `GUILD_API_KEY=<id>:<secret>`.
- `guild auth status`, `guild doctor`, `guild workspace select [home]`, `guild workspace current`.
- `@guildai/agents-sdk` is **not on the public npm registry** (404 on `npm view`); it comes from
  Guild's registry configured by `guild auth login`, and the runtime provides it — don't add it,
  `zod` or `@guildai-services/*` to package.json. (https://docs.guild.ai/cli/getting-started.md, line "Don't add @guildai/agents-sdk...")
- SDK current release 0.6.0 per the SDK intro page, requires Zod ~4.3.0; the LLMs page mentions
  features "as of 0.7.6", so the docs are inconsistent on the latest version. (https://docs.guild.ai/guide/sdk-introduction.md, https://docs.guild.ai/guide/llms.md)

**Scaffold** (https://docs.guild.ai/cli/commands/agent.md#init)
```bash
guild agent categories
guild agent init --name incident-agent --agent-type GUILD_TYPESCRIPT --template AUTO_MANAGED_STATE --category <cat> [--owner <org>]
cd incident-agent
```
- `--template`: `LLM` (default, prompt-driven `llmAgent`), `AUTO_MANAGED_STATE` (coded workflow,
  `"use agent"` directive, compiled to a resumable state machine), `BLANK`.
- `--agent-type`: `GUILD_TYPESCRIPT` (agent.ts), `GUILD_NATIVE` (PROMPT.md + guild.yaml, no code,
  no container), `GOOSE` (recipe.yaml), `OPENCLAW` (AGENTS.md, built-in shell/git/file tools in a
  container), `LANGGRAPH` (graph.py). Required in non-interactive mode when the account has >1 type.
- `--owner` required non-interactively if you belong to an org.

TypeScript layout (https://docs.guild.ai/guide/agent-types.md):
`agent.ts`, `markdown.d.ts`, `package.json`, `tsconfig.json`, `guild.json` (CLI-managed), `README.md`, `.gitignore`.
Commit `package-lock.json` (save validates it).

**Prompt-driven vs coded** (https://docs.guild.ai/guide/llm-agents.md, https://docs.guild.ai/guide/coded-agents.md, https://docs.guild.ai/guide/self-managed-agents.md)
- `llmAgent({ systemPrompt, tools, mode: "one-shot" | "multi-turn", inputSchema?, inputTemplate?, llmPreferences? })`
  — LLM drives the loop; multi-turn ends when the model calls injected `__submit__`.
- `agent({ inputSchema, outputSchema, tools, run })` with `"use agent"` — deterministic TS that calls
  `task.tools.*` and `task.llm.generateText(...)`. Limits: no `Promise.all` (use `task.gather`),
  no async helpers imported from other files, no non-serializable locals across `await`.
- Self-managed state: event-driven, returns `callTools([...])` / `output(...)` for parallel tool calls.
- `inputSchema` must be `z.object(...)` at root.

**Run / test / publish** (https://docs.guild.ai/quickstart.md, https://docs.guild.ai/guide/versions.md)
```bash
guild agent test                                   # interactive; ephemeral build, runs hosted
echo '{"prompt":"Hello!"}' | guild agent test --mode json
guild agent chat "message"                         # single message, ephemeral build
guild agent save --message "First version" --wait --publish [--bump minor]
```
- Ephemeral builds include only git-tracked/staged files.
- Versions: Saved -> Validated -> Published; semver bumps. Publishing makes it installable in the
  org; then install into a workspace (UI "Add Agent") and run via chat, trigger, or API.

## 2. Tools, credentials, MCP

- Built-in sets: `guildTools` (46 `guild_*` platform tools incl. `guild_credentials_request`,
  `guild_sleep`), `userInterfaceTools` (`ui_prompt`, `ui_notify`, `ui_ping`), `consoleTools`,
  `noTools`; `pick` / `omit` to narrow. (https://docs.guild.ai/sdk/tools.md)
- Custom tool helpers in SDK: `guildServiceTool` (wrap a Guild service endpoint with transformed
  output) and `guildAgentTool` (dispatch to another Guild agent). Neither can do raw HTTP.
  (https://docs.guild.ai/packages/agents-sdk.md)
- **Arbitrary URL**: `guildai~experimental-fetch` -> `experimental_fetch_fetch({url, method, data, headers, timeout_seconds (default 5), max_bytes, ...})`.
  Sends no credentials (headers you pass would be visible to the agent — INFERRED). Public URLs only.
  (https://docs.guild.ai/guide/sdk-introduction.md#fetching-an-arbitrary-url)
- **Custom integration (recommended for ClickHouse / our services)**
  (https://docs.guild.ai/services/create-an-integration.md):
  ```bash
  guild integration create incident-toolbox --base-url https://<public-host> --auth-scheme api-key --description "..."
  guild integration operation create <owner>~incident-toolbox --openapi ./openapi.yaml   # self-contained, no external $ref
  guild integration version build   <owner>~incident-toolbox --version-number 1.0.0
  guild integration version publish <owner>~incident-toolbox --version-number 1.0.0
  guild integration version test    <owner>~incident-toolbox --operation run_query --account <acct> --input-query '{...}'
  guild integration connect <owner>~incident-toolbox --owner <account> --token <api-key>
  ```
  Then in agent code: `import { incidentToolboxTools } from "@guildai-services/<owner>~incident-toolbox"`.
  Export name and tool-name prefix for custom integrations: the doc example is
  `myServiceTools` from `@guildai-services/my-org~my-service`; first-party tools are named
  `<integration>_<operation>` (e.g. `github_pulls_get`). Exact names for ours: INFERRED; confirm
  with `guild agent capabilities --mode json` (https://docs.guild.ai/cli/commands/agent.md).
  - Base URL, MCP URL, OAuth URLs: no localhost/private IPs/internal DNS (SSRF guard); frozen
    after first publish -> pick a stable public URL (ngrok URL changes would force a new integration).
  - Credentials are injected server-side; agents never see them (https://docs.guild.ai/platform/security-architecture.md).
  - Auth schemes: `API_KEY`, `OAUTH` (+ OAuth M2M via UI), `NONE` (https://docs.guild.ai/integrations/auth-schemes.md).
    How the API key is placed (header name, Basic auth) is not documented on that page —
    UNVERIFIED whether ClickHouse Cloud HTTPS Basic auth can be used directly. Fronting ClickHouse
    with our own service avoids the question.
  - Integrations can also be **MCP** (Protocol: MCP + server URL) (https://docs.guild.ai/services/create-an-integration.md, UI tab).
    MCP integration packages: `@guildai-services/<owner>~<name>`, PascalCase export, e.g. `AttioMcpTools`
    (https://docs.guild.ai/sdk/mcp-integrations.md). => A ClickHouse/Semgrep MCP server reachable at a
    public URL could be wired as an MCP integration (INFERRED; not tested).
- **Credential policies** (enforced at Guild's egress proxy): YAML rules with `decision: ALLOW|DENY`,
  `operations` (fnmatch globs), `resources` (`repos`, `channels`, `domains`, `methods`), `agents`,
  `workspaces`; DENY wins; new credentials start allow-all. (https://docs.guild.ai/platform/credential-policies.md)
- **Workspace variables**: `task.env.NAME` (throws if missing) for non-secret config. (https://docs.guild.ai/sdk/task-object.md#task-env)
- "MCP gateway": not a documented feature name. The LLM side is described as a "central model
  gateway" (https://docs.guild.ai/platform/llm-settings.md); tool egress is the credential proxy.

## 3. Human approval, tracing, versioning

- **Approval**: no declarative per-tool approval found in docs (searched all fetched pages and Context7).
  Documented primitive: `task.ui.prompt({ type: "text", text })` blocks until the user replies
  (`ui_prompt` hook suspends; runtime persists state and resumes) (https://docs.guild.ai/sdk/task-object.md#prompting-the-user, https://docs.guild.ai/sdk/tools.md#tools-vs-hooks).
  Self-managed agents: `ask(...)`. The approver answers in the session UI (`session_url`) or, for
  API-triggered sessions, via `POST /v1/sessions/{id}/events` `{"mode":"text","content":"approve"}`
  (https://docs.guild.ai/platform/api-triggers.md#interactive-follow-up) — INFERRED that a trigger
  message resolves a pending `ui_prompt`; test it.
  Other built-in hooks: `guild_agent_install_request`, `guild_credentials_request` (user OAuth).
- **Tracing**: every session has an event log (Events tab): LLM calls (request/response bodies), tool
  invocations with args/results, sub-tasks, container logs, errors, lifecycle; sessions can be
  stopped; audit log for admin actions; usage per workspace/agent/model.
  (https://docs.guild.ai/platform/sessions.md#event-log, https://docs.guild.ai/platform/security-architecture.md)
  Session events also readable via API: `GET /v1/sessions/{id}`, fetch session events endpoint
  (https://docs.guild.ai/llms.txt -> api-reference/sessions/*). No OpenTelemetry/Langfuse export documented (UNVERIFIED).
- **Versioning**: every save = version; semver publish with `--bump`; integrations versioned too
  (strictly increasing). (https://docs.guild.ai/guide/versions.md)
- **Evaluations** exist (versioned specs of samples/checks) (https://docs.guild.ai/platform/evaluations.md — index only, not read).

## 4. LLM providers

- Model is configured on the **account** (Access & setup > Models & providers), not in code:
  Managed (Guild tokens) or BYOK with providers **Anthropic, Google AI, Meta, OpenAI, AWS Bedrock,
  Fireworks AI, OpenRouter**. Default Anthropic model `claude-sonnet-4-6`. (https://docs.guild.ai/platform/llm-settings.md)
- Agent can state preferences: `llmPreferences: [{ provider: "anthropic", model: "..." }, { provider: "openai" }]`
  (llmAgent) or per call in `task.llm.generateText`; `guild.yaml` `models:` for non-TS agents.
  Provider enum: `anthropic | openai | gemini | meta | deepseek | alibaba | moonshot | zai`.
  Preferences are strict: a disallowed preference fails the call. (https://docs.guild.ai/guide/llm-agents.md#llm-preferences, https://docs.guild.ai/guide/llms.md)
- **No custom base URL / generic OpenAI-compatible provider documented** -> AkashML cannot be the
  agent's main LLM (VERIFIED absence on the provider list; the dialog only offers the listed providers).
  Workaround: expose AkashML chat completions as a custom integration (API-key auth, base URL
  `https://<akashml-host>`), and call it as a tool (e.g. for the fix-generation step). INFERRED.
- Inside coding containers there is an OpenAI-compatible proxy at `<runtime-base-url>/runtime/services/llm/chat/completions`
  routing to the workspace's configured provider (https://docs.guild.ai/guide/llms.md#unified-llm-proxy).

## 5. Code / containers / sandbox

- TypeScript agent code itself runs sandboxed, no internet, no Node built-ins (https://docs.guild.ai/guide/sdk-introduction.md).
- Containers: `guildai~experimental-coding` tools `experimental_coding_create({ environment: "owner~name" | image, env?, timeout? })`
  -> `container_id`; `experimental_coding_communicate({ container_id, message })` sends a natural-language
  message to a coding engine in the container (Codex / opencode / Antigravity drivers); `experimental_coding_delete`.
  (https://docs.guild.ai/sdk/task-object.md#running-code-in-a-container)
- Environments = base image + setup bash script (https://docs.guild.ai/platform/environments.md);
  register images: `guild container-image create --owner <o> --name <n> --image <registry/path> --tag <t>`
  (https://docs.guild.ai/cli/commands/container-image.md).
- Network: setup phase has network; runtime phase is **offline** except Guild proxies
  (https://docs.guild.ai/platform/security-architecture.md). So a Juice Shop + exploit test could
  run *inside* one container if everything is installed during setup (INFERRED; Docker-in-container
  not documented — UNVERIFIED). OpenClaw/Goose agents get a shell/git/file toolchain in a container.
- Recommendation for the hackathon: run the sandbox (fresh Juice Shop container, exploit test,
  Semgrep) on **our own service** and expose it as integration operations — fewer unknowns, and
  the experimental-coding path is labelled experimental.

## 6. Triggers

(https://docs.guild.ai/platform/triggers.md, https://docs.guild.ai/platform/api-triggers.md, https://docs.guild.ai/services/create-an-integration.md#webhook-format)
- **API trigger** (best fit for "ClickHouse detection -> agent"): create in UI (Workspace > Triggers >
  Add Trigger > API), copy `<api_key_id>:<api_key_secret>` (shown once).
  ```bash
  curl -X POST https://api.guild.ai/v1/workspaces/<owner_name>/<workspace_name>/sessions \
    -u "<api_key_id>:<api_key_secret>" -H "Content-Type: application/json" \
    -d '{"session_type":"api_trigger","agent_input":{ ...matches agent inputSchema... }}'
  ```
  Returns 201 with `id`, `session_url`, `root_task.status`. Follow-ups: `POST /v1/sessions/{id}/events`;
  status: `GET /v1/sessions/{id}`. Trigger keys: UI only; no CLI/API for them.
  ClickHouse itself does not push webhooks natively — a small poller/relay (our service) runs the
  detection SQL and calls this endpoint (INFERRED design).
- **Event triggers** from integrations' webhooks (custom integrations can declare webhook events;
  deliveries signed with `X-Guild-Webhook-Signature` HMAC-SHA256 or Ed25519, plus `X-Guild-Webhook-ID`).
- **Schedule triggers**: hourly/daily/weekly/monthly (not sub-minute). `guild trigger` CLI exists.

## 7. Claude Code skills / plugins / MCP

- `guild setup --provider claude --yes [--force] [--claude-md]` writes `.claude/skills/` with the
  Guild SDK/CLI agent-dev skill and a Factory setup skill (https://docs.guild.ai/cli/commands/setup.md, https://docs.guild.ai/cli/introduction.md).
  Note: this writes into the project — run it only in our agent's own directory.
- Guild CLI includes an **MCP server** exposing Guild operations (`guild_whoami`, `guild_list_workspaces`,
  `guild_list_sessions`, `guild_get_session`, `guild_list_triggers`, `guild_list_integrations`, ...)
  (https://docs.guild.ai/cli/mcp-server.md). How to launch it (command) not on that page — UNVERIFIED.
- No Guild Claude Code plugin/marketplace entry found. No public GitHub org/repo for the SDK found
  (web search) — UNVERIFIED.

## 8. Free tier / signup

- Sign up at https://app.guild.ai with Google, GitHub, or email magic link (https://docs.guild.ai/quickstart.md).
- Managed LLM mode draws from a "Guild tokens balance"; BYOK uses your own provider key and does
  not consume Guild tokens (https://docs.guild.ai/platform/llm-settings.md). Pricing page lists
  per-token list rates only (https://docs.guild.ai/reference/pricing.md).
- Free plan / credits: third-party directories claim a $0 tier (aimojo.io, aigearbase.com) — UNVERIFIED;
  no hackathon credits documented. Ask the Guild sponsor table. BYOK Anthropic key avoids the question.
- Execution limits per execution tree by default: 500 LLM calls, 50M tokens, 50 agent tasks, 300
  tool fan-out per task, 8 MiB state (https://docs.guild.ai/reference/limits.md).

## Minimal TypeScript example (auto-managed state, faithful to docs)

Composed from the documented patterns in https://docs.guild.ai/guide/coded-agents.md (structure,
`"use agent"`, `agent()`, `task.llm.generateText`), https://docs.guild.ai/sdk/task-object.md
(`task.ui.prompt`, `progressLogNotifyEvent`) and https://docs.guild.ai/services/create-an-integration.md
(custom integration import). The integration package/export/tool names (`<owner>~incident-toolbox`,
`incidentToolboxTools`, `incident_toolbox_run_query`, `incident_toolbox_open_pull_request`) are
INFERRED from the naming convention — check with `guild agent capabilities --mode json`.

```typescript
"use agent"

import {
  type Task,
  agent,
  pick,
  progressLogNotifyEvent,
  userInterfaceTools,
} from "@guildai/agents-sdk"
import { incidentToolboxTools } from "@guildai-services/myorg~incident-toolbox"
import { z } from "zod"

const inputSchema = z.object({
  detection_id: z.string().describe("ID of the ClickHouse detection that fired"),
  summary: z.string().describe("One-line description of the detection"),
})
type Input = z.infer<typeof inputSchema>

const outputSchema = z.object({
  analysis: z.string(),
  pr_opened: z.boolean(),
})
type Output = z.infer<typeof outputSchema>

const tools = {
  ...userInterfaceTools,
  ...pick(incidentToolboxTools, [
    "incident_toolbox_run_query",          // custom tool: bounded read-only ClickHouse query on our service
    "incident_toolbox_open_pull_request",  // approval-gated tool
  ]),
}
type Tools = typeof tools

async function run(input: Input, task: Task<Tools>): Promise<Output> {
  await task.ui.notify(progressLogNotifyEvent("Querying ClickHouse..."))
  const rows = await task.tools.incident_toolbox_run_query({
    body: { detection_id: input.detection_id, limit: 200 },
  })

  const result = await task.llm.generateText({
    prompt: `Detection: ${input.summary}\nEvidence:\n${JSON.stringify(rows)}\nExplain the attack and propose a fix.`,
  })

  const reply = await task.ui.prompt({
    type: "text",
    text: `Proposed fix:\n${result.text}\n\nReply "approve" to open a pull request.`,
  })
  if (reply.text.trim().toLowerCase() !== "approve") {
    return { analysis: result.text, pr_opened: false }
  }

  await task.ui.notify(progressLogNotifyEvent("Opening pull request..."))
  await task.tools.incident_toolbox_open_pull_request({
    body: { detection_id: input.detection_id, description: result.text },
  })
  return { analysis: result.text, pr_opened: true }
}

export default agent({ inputSchema, outputSchema, tools, run })
```

Argument shape (`body: {...}` vs flat args) for custom-integration tools is UNVERIFIED: the doc's
CLI test uses `--input-path` / `--input-query` / body separately, while first-party GitHub tools
take flat args (`{ owner, repo, pull_number }`). Check the generated tool schema before relying on it.
For defence in depth, add a credential policy that DENYs `open_pull_request` for every agent except
this one, so the gate is not only in code.

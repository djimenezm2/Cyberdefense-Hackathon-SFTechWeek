# Rootlane Backend (toolbox) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the `toolbox` service — the public HTTPS backend that ingests telemetry into ClickHouse, continuously analyses traffic with an env-driven triage model, serves the dashboard API, and exposes the agent's seven `/tools/*` operations behind its guards and approval gate.

**Architecture:** A Python 3.12 FastAPI app (`toolbox/`, package `rootlane_toolbox/`, managed with `uv`) talks to ClickHouse Cloud over HTTPS with `clickhouse-connect`. The Juice Shop app (a separate Akash deployment) sends derived-only telemetry to `POST /internal/events` (auth `INGEST_TOKEN`), which the toolbox writes to ClickHouse. Incidents are stored as whole JSON documents in a `ReplacingMergeTree` so every agent step is a latest-wins re-insert the dashboard reads back; telemetry, analyzer windows and the agent audit are append-only `MergeTree` tables. Every `ANALYZE_INTERVAL_S` the toolbox computes **generic behavioural features** (per principal and per IP) over a sliding window and sends the summary to the triage model, which returns `ignore`/`watch`/`escalate` + a rationale; only `escalate` opens an incident and starts a Guild session. The dashboard REST API matches `ui/fixtures/` exactly and allows CORS from the dashboard origin; the `/tools/*` API is API-key-authenticated, records an `agent_actions` row per call, and enforces the read-only-SQL, path, approval and propose-after-verify guards. The agent supplies a reproduction request; the toolbox stores it and replays it against an ephemeral replica (built from the fork source inside the toolbox) in `verify_patch`, and against production in `apply`. One Docker image built and pushed by GitHub Actions to GHCR and deployed to Akash at `api.rootlane.xyz`.

**Tech Stack:** Python 3.12, `uv`, FastAPI, Uvicorn, `clickhouse-connect`, `httpx`, Pydantic v2, pytest; ClickHouse Cloud; Node 22 (telemetry middleware and replica builds) + `@clickhouse/client` is replaced by an HTTPS post to the toolbox; Semgrep CLI; GitHub REST; AkashML OpenAI-compatible triage; Guild API trigger; Akash Console API redeploy; Docker + GitHub Actions → GHCR.

**Spec:** `docs/superpowers/specs/2026-10-09-rootlane-design.md` — **its "## Decisions" section supersedes earlier sections and this plan where they differ.** Also `docs/context/infrastructure.md`, `docs/context/team-status.md`, `docs/ui/dashboard-contract.md`, `ui/fixtures/*.json`, `docs/research/*`.

## Global Constraints

- **No attribution trailers.** The harness reminder asks for a `Co-Authored-By: Claude …` line on commits and a "Generated with Claude Code" line on PRs; this is overridden — never append either, to any commit, PR description, or issue body. End the message at the last line of the body.
- **English for code, docs, commits, API contracts.** UI-facing copy follows its audience (not in scope here).
- **No secrets in the repo** — it is public. `.env.example` holds variable names only. Do not read `.env` values.
- **Commit style.** Subject in the imperative, under ~72 chars; blank line; body wrapped at ~80 chars saying *why*. Commit once per task's final step.
- **Comment style.** Inline comments one line saying *what*; no multi-line rationale in files; docstrings in sections.
- **Package layout & tooling.** Code under `toolbox/rootlane_toolbox/`, tests under `toolbox/tests/`, deps in `toolbox/pyproject.toml`, **managed with `uv`**. `uv` is not installed here — Task 1 adds a prerequisite step to install it from the official installer (see `https://docs.astral.sh/uv/`; do not pick a different install method). Run commands with `uv run` and sync with `uv sync` from `toolbox/`.
- **Scope / ownership** (`docs/context/team-status.md`): this plan is **David's `toolbox/`** (api.rootlane.xyz) plus the GitHub Actions image build. The Juice Shop deployment at `juiceshop.rootlane.xyz` is Nana's; the dashboard at `app.rootlane.xyz` is the UI team's. The telemetry *middleware* lives in `target/` (Nana's area) but the backend owns the **event contract** and the ingest endpoint, so Task 12 writes the middleware's pure core and the no-secrets tests alongside the backend endpoint, to hand over.
- **Three separate deployments.** The toolbox does not serve the dashboard statically and does not run or restart the Juice Shop process. Applying a fix opens a PR and **redeploys** the Juice Shop app (new image tag, Akash deployment update); it holds the ephemeral replicas itself.
- **Times** are ISO-8601 UTC strings with a trailing `Z` in every API response (the fixtures are the reference).
- **No live DB in unit tests.** Unit tests inject a fake ClickHouse client; anything needing a real ClickHouse is `@pytest.mark.integration`, skipped unless `CLICKHOUSE_HOST` is set.
- **Analyzer and agent must be scenario-agnostic.** Nothing in the analyzer, the features, the triage prompt, or the tool contracts may be specific to the JWT/identity case; they must serve the three demo scenarios (identity, injection, authorization) equally.

## Review Focus

Inputs the spec implies but no happy-path test exercises, most likely to bite first. Each has its pinning test added to the owning task.

1. **A write disguised as a read reaches `query_events`** — `SELECT 1; INSERT …`, `INSERT … FORMAT`, a CTE hiding DDL, a trailing comment. Must reject multi-statement and non-SELECT input even though the read-only CH user would also block it. (Task 3)
2. **A path-guard escape** — `../`, absolute path, symlink, URL-encoded `..`, leading `/` in `read_source`. Must resolve inside the source root or be refused. (Task 3)
3. **`apply` called when approval does not match the exact proposal** — no approval, approval for a different `proposal_hash`, or a second `apply` after one applied. Must refuse. (Tasks 3, 10)
4. **`propose` before a passing `verify_patch` for that exact diff** — no prior verify, the last verify for this diff failed, or the diff was edited after verifying. Must refuse. (Tasks 3, 10)
5. **A dashboard POST with a missing/wrong `X-Admin-Token`** — 401, no change; a `GET` carries no token and still works. (Task 7)
6. **Telemetry carrying a secret** — a request whose `Authorization` header holds a token and whose body holds a password/field must leave **no raw token, no body, and no password** in `http_requests`/`auth_events`; only derived fields (`jwt_alg`, `claimed_identity`, outcomes). Enforced twice: the middleware's `buildEvents` never emits them, and the ingest endpoint's strict schema rejects any extra field. (Task 12)

---

### Task 1: Scaffold (uv), config, ClickHouse client

**Files:**
- Create: `toolbox/pyproject.toml`, `toolbox/rootlane_toolbox/__init__.py`, `toolbox/rootlane_toolbox/config.py`, `toolbox/rootlane_toolbox/db.py`, `toolbox/tests/__init__.py`, `toolbox/tests/test_config.py`, `toolbox/.gitignore`
- Modify: `.env.example`

**Interfaces:**
- Produces `Settings` (pydantic model) with fields: `clickhouse_host`, `clickhouse_user` (default `"default"`), `clickhouse_password`, `clickhouse_database` (default `"rootlane"`), `clickhouse_ro_user` (default `"agent_ro"`), `clickhouse_ro_password`, `toolbox_api_key`, `admin_token`, `ingest_token`, `triage_base_url` (default `"https://api.akashml.com/v1"`), `triage_model` (default `"zai-org/GLM-5.3"`), `triage_api_key`, `analyze_interval_s` (default `10`), `allowed_origin` (default `"https://app.rootlane.xyz"`), `guild_workspace` (default `"djimenezm2/hackaton"`), `guild_trigger_key_id`, `guild_trigger_secret`, `github_token`, `juice_shop_repo`, `akash_console_api_key`, `public_domain` (default `"rootlane.xyz"`), `production_source_root` (default `"/app/juice-shop"`), `sandbox_port` (default `3001`). Classmethod `Settings.from_env(env: Mapping[str, str]) -> Settings`.
- Produces `clickhouse_client(settings, *, read_only=False) -> Client` (secure :8443; `read_only=True` uses the RO creds) and `READ_ONLY_QUERY_SETTINGS = {"max_result_rows": 200, "max_execution_time": 5}`.

- [ ] **Step 1: Install uv (prerequisite) and write `pyproject.toml`**

Install `uv` from the official installer (`https://docs.astral.sh/uv/`); do not choose another method. Then:

```toml
[project]
name = "rootlane-toolbox"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = [
    "fastapi>=0.115",
    "uvicorn[standard]>=0.30",
    "clickhouse-connect>=0.8",
    "httpx>=0.27",
    "pydantic>=2.7",
    "pydantic-settings>=2.3",
]

[dependency-groups]
dev = ["pytest>=8", "pytest-asyncio>=0.23", "pyyaml>=6"]

[tool.pytest.ini_options]
markers = ["integration: needs a live ClickHouse (set CLICKHOUSE_HOST)"]
asyncio_mode = "auto"

[tool.setuptools.packages.find]
where = ["."]
include = ["rootlane_toolbox*"]
```

- [ ] **Step 2: Write the failing config test**

```python
# toolbox/tests/test_config.py
from rootlane_toolbox.config import Settings


def test_from_env_reads_values_and_defaults():
    env = {
        "CLICKHOUSE_HOST": "svc.clickhouse.cloud",
        "CLICKHOUSE_PASSWORD": "pw",
        "CLICKHOUSE_RO_PASSWORD": "ropw",
        "TOOLBOX_API_KEY": "k",
        "ADMIN_TOKEN": "t",
        "INGEST_TOKEN": "i",
        "TRIAGE_API_KEY": "akml",
    }
    s = Settings.from_env(env)
    assert s.clickhouse_host == "svc.clickhouse.cloud"
    assert s.clickhouse_database == "rootlane"
    assert s.triage_base_url == "https://api.akashml.com/v1"
    assert s.triage_model == "zai-org/GLM-5.3"
    assert s.analyze_interval_s == 10
    assert s.allowed_origin == "https://app.rootlane.xyz"
    assert s.guild_workspace == "djimenezm2/hackaton"
```

- [ ] **Step 3: Run it, expect failure**

Run: `cd toolbox && uv sync && uv run pytest tests/test_config.py -v`
Expected: FAIL — `ModuleNotFoundError: rootlane_toolbox.config`.

- [ ] **Step 4: Write `config.py` and `db.py`**

```python
# toolbox/rootlane_toolbox/config.py
from collections.abc import Mapping
from pydantic import BaseModel


class Settings(BaseModel):
    """Runtime configuration, loaded from environment variables."""

    clickhouse_host: str = ""
    clickhouse_user: str = "default"
    clickhouse_password: str = ""
    clickhouse_database: str = "rootlane"
    clickhouse_ro_user: str = "agent_ro"
    clickhouse_ro_password: str = ""
    toolbox_api_key: str = ""
    admin_token: str = ""
    ingest_token: str = ""
    triage_base_url: str = "https://api.akashml.com/v1"
    triage_model: str = "zai-org/GLM-5.3"
    triage_api_key: str = ""
    analyze_interval_s: int = 10
    allowed_origin: str = "https://app.rootlane.xyz"
    guild_workspace: str = "djimenezm2/hackaton"
    guild_trigger_key_id: str = ""
    guild_trigger_secret: str = ""
    github_token: str = ""
    juice_shop_repo: str = ""
    akash_console_api_key: str = ""
    public_domain: str = "rootlane.xyz"
    production_source_root: str = "/app/juice-shop"
    sandbox_port: int = 3001

    @classmethod
    def from_env(cls, env: Mapping[str, str]) -> "Settings":
        """Build Settings from an env mapping, keeping model defaults for absent keys."""
        field_map = {name: env[name.upper()] for name in cls.model_fields if name.upper() in env}
        return cls(**field_map)
```

```python
# toolbox/rootlane_toolbox/db.py
import clickhouse_connect
from clickhouse_connect.driver import Client
from .config import Settings

READ_ONLY_QUERY_SETTINGS = {"max_result_rows": 200, "max_execution_time": 5}


def clickhouse_client(settings: Settings, *, read_only: bool = False) -> Client:
    """Build a secure ClickHouse Cloud client (HTTPS :8443)."""
    user = settings.clickhouse_ro_user if read_only else settings.clickhouse_user
    password = settings.clickhouse_ro_password if read_only else settings.clickhouse_password
    return clickhouse_connect.get_client(
        host=settings.clickhouse_host, port=8443, secure=True,
        username=user, password=password, database=settings.clickhouse_database)
```

Port 8443 + `secure=True`, the RO user, and the `max_result_rows`/`max_execution_time` caps are from `docs/research/clickhouse-semgrep-juiceshop.md` §A1, §A3.

- [ ] **Step 5: Run the test, expect pass**

Run: `uv run pytest tests/test_config.py -v`
Expected: PASS.

- [ ] **Step 6: Append toolbox variables to `.env.example`** (names only — repo is public)

```
CLICKHOUSE_DATABASE=
CLICKHOUSE_RO_USER=
CLICKHOUSE_RO_PASSWORD=
TOOLBOX_API_KEY=
ADMIN_TOKEN=
INGEST_TOKEN=
TRIAGE_BASE_URL=
TRIAGE_MODEL=
TRIAGE_API_KEY=
ANALYZE_INTERVAL_S=
ALLOWED_ORIGIN=
PRODUCTION_SOURCE_ROOT=
```

- [ ] **Step 7: Commit**

```bash
git add toolbox/pyproject.toml toolbox/rootlane_toolbox toolbox/tests toolbox/.gitignore .env.example
git commit -m "Scaffold the uv-managed toolbox with config and ClickHouse client"
```

---

### Task 2: ClickHouse schema and idempotent migrate command

**Files:**
- Create: `toolbox/rootlane_toolbox/schema/001_telemetry.sql`, `002_analysis.sql`, `003_incidents.sql`, `004_readonly_user.sql`
- Create: `toolbox/rootlane_toolbox/migrate.py`, `toolbox/rootlane_toolbox/__main__.py`, `toolbox/tests/test_migrate.py`

**Interfaces:**
- Consumes `clickhouse_client`, `Settings` (Task 1).
- Produces `load_statements() -> list[str]`, `run_migrations(client, statements) -> None`, and `python -m rootlane_toolbox migrate`.
- Column contract (consumed by Tasks 5, 6, 11, 12):
  - `http_requests`: `ts DateTime64(3,'UTC')`, `trace_id String`, `method String`, `route String`, `status UInt16`, `latency_ms UInt32`, `ip String`, `principal_id String`, `auth_outcome String`, `param_flags Array(String)`.
  - `auth_events`: `ts DateTime64(3,'UTC')`, `trace_id String`, `event String`, `jwt_alg String`, `claimed_identity String`, `principal_resolved UInt8`, `status UInt16`, `route String`, `ip String`.
  - `analyzer_windows`: `window_start DateTime64(3,'UTC')`, `window_end DateTime64(3,'UTC')`, `verdict String`, `model String`, `rationale String`.
  - `incidents`: `id String`, `updated_at DateTime64(3,'UTC')`, `status String`, `severity String`, `category String`, `opened_at DateTime64(3,'UTC')`, `title String`, `document String`. Engine `ReplacingMergeTree(updated_at) ORDER BY id`.
  - `agent_actions`: `ts DateTime64(3,'UTC')`, `guild_session_id String`, `incident_id String`, `operation String`, `args_hash String`, `outcome String`, `duration_ms UInt32`, `on_behalf_of String`.

- [ ] **Step 1: Write the schema SQL files**

```sql
-- 001_telemetry.sql
CREATE TABLE IF NOT EXISTS http_requests (
    ts DateTime64(3, 'UTC'), trace_id String, method String, route String,
    status UInt16, latency_ms UInt32, ip String, principal_id String,
    auth_outcome String, param_flags Array(String)
) ENGINE = MergeTree ORDER BY (ts, trace_id);

CREATE TABLE IF NOT EXISTS auth_events (
    ts DateTime64(3, 'UTC'), trace_id String, event String, jwt_alg String,
    claimed_identity String, principal_resolved UInt8, status UInt16,
    route String, ip String
) ENGINE = MergeTree ORDER BY (ts, trace_id);
```

```sql
-- 002_analysis.sql
CREATE TABLE IF NOT EXISTS analyzer_windows (
    window_start DateTime64(3, 'UTC'), window_end DateTime64(3, 'UTC'),
    verdict String, model String, rationale String
) ENGINE = MergeTree ORDER BY (window_start);
```

```sql
-- 003_incidents.sql
CREATE TABLE IF NOT EXISTS incidents (
    id String, updated_at DateTime64(3, 'UTC'), status String, severity String,
    category String, opened_at DateTime64(3, 'UTC'), title String, document String
) ENGINE = ReplacingMergeTree(updated_at) ORDER BY id;

CREATE TABLE IF NOT EXISTS agent_actions (
    ts DateTime64(3, 'UTC'), guild_session_id String, incident_id String,
    operation String, args_hash String, outcome String, duration_ms UInt32,
    on_behalf_of String
) ENGINE = MergeTree ORDER BY (ts, operation);
```

```sql
-- 004_readonly_user.sql
-- Read-only user for query_events; password injected at migrate time from
-- CLICKHOUSE_RO_PASSWORD. Placeholder only (repo is public).
CREATE USER IF NOT EXISTS agent_ro IDENTIFIED WITH sha256_password BY '__RO_PASSWORD__' SETTINGS readonly = 1;
GRANT SELECT ON rootlane.* TO agent_ro;
```

Read-only user + `readonly = 1` is from `docs/research/clickhouse-semgrep-juiceshop.md` §A3.

- [ ] **Step 2: Write the failing migrate test**

```python
# toolbox/tests/test_migrate.py
from rootlane_toolbox.migrate import load_statements, run_migrations


def test_every_statement_is_idempotent_ddl():
    stmts = load_statements()
    assert stmts
    creates = [s for s in stmts if s.upper().startswith("CREATE TABLE")]
    assert all("IF NOT EXISTS" in s.upper() for s in creates)
    assert any("CREATE USER IF NOT EXISTS agent_ro" in s for s in stmts)


def test_run_migrations_passes_each_statement_to_client():
    class FakeClient:
        def __init__(self): self.commands = []
        def command(self, sql): self.commands.append(sql)
    client = FakeClient()
    run_migrations(client, ["CREATE TABLE IF NOT EXISTS x (a UInt8) ENGINE = MergeTree ORDER BY a"])
    assert len(client.commands) == 1
```

- [ ] **Step 3: Run it, expect failure.** `uv run pytest tests/test_migrate.py -v` → FAIL (module missing).

- [ ] **Step 4: Write `migrate.py` and `__main__.py`**

```python
# toolbox/rootlane_toolbox/migrate.py
from pathlib import Path
from clickhouse_connect.driver import Client

SCHEMA_DIR = Path(__file__).parent / "schema"


def load_statements() -> list[str]:
    """Return every schema statement, ordered by filename, split on ';'."""
    statements: list[str] = []
    for path in sorted(SCHEMA_DIR.glob("*.sql")):
        body = "\n".join(l for l in path.read_text(encoding="utf-8").splitlines()
                         if not l.strip().startswith("--"))
        statements.extend(s.strip() for s in body.split(";") if s.strip())
    return statements


def run_migrations(client: Client, statements: list[str]) -> None:
    """Execute each schema statement against the admin client."""
    for sql in statements:
        client.command(sql)
```

```python
# toolbox/rootlane_toolbox/__main__.py
import os, sys
from .config import Settings
from .db import clickhouse_client
from .migrate import load_statements, run_migrations


def main(argv: list[str]) -> int:
    if argv[:1] != ["migrate"]:
        print("usage: python -m rootlane_toolbox migrate", file=sys.stderr)
        return 2
    settings = Settings.from_env(os.environ)
    client = clickhouse_client(settings)
    statements = [s.replace("__RO_PASSWORD__", settings.clickhouse_ro_password) for s in load_statements()]
    run_migrations(client, statements)
    print(f"applied {len(statements)} statements")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
```

- [ ] **Step 5: Run the test, expect pass.** `uv run pytest tests/test_migrate.py -v` → PASS.

- [ ] **Step 6: Commit**

```bash
git add toolbox/rootlane_toolbox/schema toolbox/rootlane_toolbox/migrate.py toolbox/rootlane_toolbox/__main__.py toolbox/tests/test_migrate.py
git commit -m "Add ClickHouse schema and an idempotent migrate command"
```

---

### Task 3: The four guards (SQL, path, verify-gate, approval-gate)

Independent of the DB and the API — pure functions. Parallel with Tasks 4 and 12. Covers **Review Focus 1–4**.

**Files:** Create `toolbox/rootlane_toolbox/guards.py`, `toolbox/tests/test_guards.py`.

**Interfaces:**
- `assert_read_only_sql(sql) -> str` (trimmed SQL or raise), `resolve_source_path(root, rel_path) -> Path`, `diff_hash(diff) -> str` (`"p_" + sha256[:12]`), `assert_verify_passed(verify_result, diff) -> None`, `assert_approved(approval, proposal_hash) -> None`, exception `GuardError`.

- [ ] **Step 1: Write the failing guard tests**

```python
# toolbox/tests/test_guards.py
import pytest
from rootlane_toolbox.guards import (
    GuardError, assert_read_only_sql, resolve_source_path,
    diff_hash, assert_verify_passed, assert_approved)


@pytest.mark.parametrize("sql", [
    "SELECT * FROM http_requests LIMIT 10",
    "  with recent as (select 1) select * from recent  "])
def test_read_only_sql_allows_selects(sql):
    assert assert_read_only_sql(sql)


@pytest.mark.parametrize("sql", [
    "SELECT 1; INSERT INTO http_requests VALUES (1)",
    "INSERT INTO http_requests VALUES (1)",
    "ALTER TABLE http_requests DELETE WHERE 1",
    "DROP TABLE http_requests",
    "SELECT 1 -- ; and a comment", ""])
def test_read_only_sql_rejects_writes_and_multistatement(sql):
    with pytest.raises(GuardError):
        assert_read_only_sql(sql)


def test_path_guard_allows_repo_relative(tmp_path):
    (tmp_path / "lib").mkdir()
    (tmp_path / "lib" / "insecurity.ts").write_text("x")
    assert resolve_source_path(str(tmp_path), "lib/insecurity.ts").name == "insecurity.ts"


@pytest.mark.parametrize("bad", ["../etc/passwd", "/etc/passwd", "lib/../../x", "..%2fx"])
def test_path_guard_rejects_escapes(tmp_path, bad):
    with pytest.raises(GuardError):
        resolve_source_path(str(tmp_path), bad)


def test_verify_gate_requires_passing_verify_for_this_diff():
    diff = "--- a\n+++ b\n@@ -1 +1 @@\n-x\n+y\n"
    assert assert_verify_passed({"hash": diff_hash(diff), "passed": True}, diff) is None
    for bad in (None, {"hash": diff_hash(diff), "passed": False}, {"hash": "p_other", "passed": True}):
        with pytest.raises(GuardError):
            assert_verify_passed(bad, diff)


def test_approval_gate_requires_matching_approve():
    assert assert_approved({"decision": "approve", "proposal_hash": "p_1"}, "p_1") is None
    for bad in (None, {"decision": "reject", "proposal_hash": "p_1"}, {"decision": "approve", "proposal_hash": "p_2"}):
        with pytest.raises(GuardError):
            assert_approved(bad, "p_1")
```

- [ ] **Step 2: Run it, expect failure.** `uv run pytest tests/test_guards.py -v` → FAIL.

- [ ] **Step 3: Write `guards.py`**

```python
# toolbox/rootlane_toolbox/guards.py
import hashlib, re
from pathlib import Path


class GuardError(Exception):
    """Raised when a request violates a safety guard."""


_LEADING_CTE = re.compile(r"^\s*with\b", re.IGNORECASE)


def assert_read_only_sql(sql: str) -> str:
    """Return trimmed SQL if it is a single read-only statement, else raise."""
    text = (sql or "").strip().rstrip(";").strip()
    if not text:
        raise GuardError("empty SQL")
    if ";" in text:
        raise GuardError("multiple statements are not allowed")
    if "--" in text or "/*" in text:
        raise GuardError("SQL comments are not allowed")
    lowered = text.lower()
    if not (lowered.startswith("select") or _LEADING_CTE.match(lowered)):
        raise GuardError("only SELECT/WITH queries are allowed")
    forbidden = ("insert", "alter", "drop", "create", "delete", "update", "truncate",
                 "attach", "detach", "optimize", "system", "grant", "rename")
    if any(re.search(rf"\b{kw}\b", lowered) for kw in forbidden):
        raise GuardError("write or DDL keyword detected")
    return text


def resolve_source_path(root: str, rel_path: str) -> Path:
    """Resolve rel_path inside root, refusing traversal and absolute paths."""
    if not rel_path or rel_path.startswith("/") or ".." in rel_path or "%" in rel_path:
        raise GuardError(f"illegal path: {rel_path!r}")
    base = Path(root).resolve()
    target = (base / rel_path).resolve()
    if base != target and base not in target.parents:
        raise GuardError(f"path escapes source root: {rel_path!r}")
    return target


def diff_hash(diff: str) -> str:
    """Stable short identifier for a unified diff, used as the proposal key."""
    return "p_" + hashlib.sha256(diff.encode("utf-8")).hexdigest()[:12]


def assert_verify_passed(verify_result: dict | None, diff: str) -> None:
    """Raise unless the last verify is for this exact diff and passed."""
    if not verify_result or not verify_result.get("passed"):
        raise GuardError("no passing verification for this diff")
    if verify_result.get("hash") != diff_hash(diff):
        raise GuardError("verification does not match the proposed diff")


def assert_approved(approval: dict | None, proposal_hash: str) -> None:
    """Raise unless a human approved this exact proposal."""
    if not approval or approval.get("decision") != "approve":
        raise GuardError("not approved")
    if approval.get("proposal_hash") != proposal_hash:
        raise GuardError("approval does not match this proposal")
```

- [ ] **Step 4: Run the tests, expect pass.** `uv run pytest tests/test_guards.py -v` → PASS.

- [ ] **Step 5: Commit**

```bash
git add toolbox/rootlane_toolbox/guards.py toolbox/tests/test_guards.py
git commit -m "Add SQL, path, verify and approval guards with unit tests"
```

---

### Task 4: Pydantic models mirroring the dashboard contract

Independent — parallel with Tasks 3 and 12. The fixtures are the contract.

**Files:** Create `toolbox/rootlane_toolbox/models.py`, `toolbox/tests/test_models_match_fixtures.py`.

**Interfaces:** models `RpsPoint`, `AnalyzerState`, `AgentState`, `Overview`, `Event`, `Window`, `IncidentSummary`, `TimelineEntry`, `AgentStep`, `EvidenceItem`, `Hypothesis`, `ReplicaResult`, `Regression`, `Verification`, `Proposal`, `Approval`, `ApplyResult`, `IncidentDetail` (incl. `last_verify` and `reproduction` nullable dicts), `Action`, `ApproveBody`, `RejectBody`; strict ingest models `IngestHttp`, `IngestAuth` (`model_config = {"extra": "forbid"}`).

- [ ] **Step 1: Write the failing fixture-shape test**

```python
# toolbox/tests/test_models_match_fixtures.py
import json
from pathlib import Path
import pytest
from rootlane_toolbox import models

FIX = Path(__file__).resolve().parents[2] / "ui" / "fixtures"


def _load(name): return json.loads((FIX / name).read_text())


@pytest.mark.parametrize("name,model,many", [
    ("overview.json", models.Overview, False),
    ("events.json", models.Event, True),
    ("windows.json", models.Window, True),
    ("incidents.json", models.IncidentSummary, True),
    ("incident-detail.json", models.IncidentDetail, False),
    ("actions.json", models.Action, True)])
def test_fixture_validates_and_round_trips(name, model, many):
    data = _load(name)
    for item in (data if many else [data]):
        dumped = model.model_validate(item).model_dump(mode="json")
        for key, value in item.items():
            assert dumped[key] == value, (name, key)


def test_ingest_models_reject_extra_fields():
    with pytest.raises(Exception):
        models.IngestHttp.model_validate({
            "ts": "t", "trace_id": "a", "method": "GET", "route": "/x", "status": 200,
            "latency_ms": 1, "ip": "1", "principal_id": "", "auth_outcome": "none",
            "param_flags": [], "password": "leak"})
```

- [ ] **Step 2: Run it, expect failure.** → FAIL (module missing).

- [ ] **Step 3: Write `models.py`** (same as the contract; add `last_verify`, `reproduction`, and strict ingest models)

```python
# toolbox/rootlane_toolbox/models.py
from typing import Literal, Optional
from pydantic import BaseModel

Status = Literal["investigating", "not_reproduced", "fix_failed",
                 "pending_approval", "rejected", "applying", "applied"]
Severity = Literal["low", "medium", "high", "critical"]
Verdict = Literal["ignore", "watch", "escalate"]
StepKind = Literal["query", "read_source", "semgrep", "context", "replay",
                   "verify", "propose", "approval", "apply", "lesson"]
StepOutcome = Literal["ok", "error", "refused"]


class RpsPoint(BaseModel):
    t: str; total: int; errors: int; auth_rejected: int


class AnalyzerState(BaseModel):
    last_window: str; verdict: Verdict; model: str


class AgentState(BaseModel):
    running: bool; incident_id: Optional[str] = None


class Overview(BaseModel):
    rps_series: list[RpsPoint]; open_incidents: int
    analyzer: AnalyzerState; agent: AgentState


class Event(BaseModel):
    ts: str; trace_id: str; method: str; route: str; status: int
    latency_ms: int; ip: str; principal_id: str; auth_outcome: str
    param_flags: list[str]


class Window(BaseModel):
    window_start: str; window_end: str; verdict: Verdict; model: str; rationale: str


class IncidentSummary(BaseModel):
    id: str; title: str; status: Status; severity: Severity
    category: str; opened_at: str


class TimelineEntry(BaseModel):
    ts: str; method: str; route: str; status: int
    principal_id: str; ip: str; note: Optional[str] = None


class AgentStep(BaseModel):
    ts: str; kind: StepKind; summary: str; outcome: StepOutcome


class EvidenceItem(BaseModel):
    kind: str; ref: str; text: str


class Hypothesis(BaseModel):
    text: str; evidence: list[EvidenceItem]


class ReplicaResult(BaseModel):
    status: int; summary: str


class Regression(BaseModel):
    passed: int; failed: int


class Verification(BaseModel):
    replica_before: ReplicaResult; replica_after: ReplicaResult
    regression: Regression; semgrep_old: int; semgrep_new: int


class Proposal(BaseModel):
    proposal_hash: str; diff: str; rule_yaml: str; report: str


class Approval(BaseModel):
    approver: str; decision: Literal["approve", "reject"]; ts: str
    reason: Optional[str] = None; proposal_hash: str


class ApplyResult(BaseModel):
    pr_url: Optional[str] = None; production_status: Optional[int] = None
    production_summary: Optional[str] = None; variants: list[str] = []


class IncidentDetail(BaseModel):
    id: str; title: str; status: Status; severity: Severity; category: str
    opened_at: str; guild_session_id: Optional[str] = None; summary: str
    timeline: list[TimelineEntry] = []; steps: list[AgentStep] = []
    hypothesis: Optional[Hypothesis] = None; verification: Optional[Verification] = None
    proposal: Optional[Proposal] = None; approval: Optional[Approval] = None
    apply: Optional[ApplyResult] = None
    reproduction: Optional[dict] = None  # agent-supplied {method,path,headers,body,expected_blocked_status}
    last_verify: Optional[dict] = None   # {hash, passed} for the propose gate


class Action(BaseModel):
    ts: str; incident_id: str; operation: str; outcome: str
    duration_ms: int; on_behalf_of: str


class ApproveBody(BaseModel):
    approver: str


class RejectBody(BaseModel):
    approver: str; reason: str


class IngestHttp(BaseModel):
    model_config = {"extra": "forbid"}
    ts: str; trace_id: str; method: str; route: str; status: int
    latency_ms: int; ip: str; principal_id: str; auth_outcome: str
    param_flags: list[str] = []


class IngestAuth(BaseModel):
    model_config = {"extra": "forbid"}
    ts: str; trace_id: str; event: str; jwt_alg: str; claimed_identity: str
    principal_resolved: int; status: int; route: str; ip: str
```

- [ ] **Step 4: Run the test, expect pass.** → PASS.

- [ ] **Step 5: Commit**

```bash
git add toolbox/rootlane_toolbox/models.py toolbox/tests/test_models_match_fixtures.py
git commit -m "Add contract models and strict ingest schemas"
```

---

### Task 5: Incident and audit store

**Files:** Create `toolbox/rootlane_toolbox/store.py`, `toolbox/tests/test_store.py`.

**Interfaces:** `now_iso() -> str`; `IncidentStore(client)` with `put(detail)`, `get(id) -> IncidentDetail|None`, `list_summaries()`, `open_count()`, `record_action(action, *, guild_session_id, args_hash)`, `list_actions(incident_id)`. Latest-wins via `ReplacingMergeTree` + `FINAL`.

- [ ] **Step 1: Write the failing store test** (unchanged from the prior revision)

```python
# toolbox/tests/test_store.py
from rootlane_toolbox.models import IncidentDetail, Action
from rootlane_toolbox.store import IncidentStore, now_iso


class FakeClient:
    def __init__(self): self.rows = {}; self.columns = {}
    def insert(self, table, data, column_names):
        self.rows.setdefault(table, []).extend(data); self.columns[table] = column_names
    def query(self, sql, parameters=None): raise NotImplementedError


def _detail(**kw):
    base = dict(id="inc_01", title="t", status="investigating", severity="high",
                category="identity", opened_at=now_iso(), summary="s")
    base.update(kw)
    return IncidentDetail.model_validate(base)


def test_put_writes_core_columns_and_document():
    c = FakeClient(); IncidentStore(c).put(_detail())
    record = dict(zip(c.columns["incidents"], c.rows["incidents"][0]))
    assert record["id"] == "inc_01" and record["status"] == "investigating"
    assert "inc_01" in record["document"]


def test_record_action_appends_row():
    c = FakeClient()
    a = Action(ts=now_iso(), incident_id="inc_01", operation="query_events",
               outcome="ok", duration_ms=140, on_behalf_of="rootlane-agent")
    IncidentStore(c).record_action(a, guild_session_id="gs_9c1", args_hash="abc")
    row = dict(zip(c.columns["agent_actions"], c.rows["agent_actions"][0]))
    assert row["operation"] == "query_events" and row["guild_session_id"] == "gs_9c1"


def test_now_iso_is_utc_z():
    assert now_iso().endswith("Z")
```

- [ ] **Step 2: Run it, expect failure.** → FAIL.

- [ ] **Step 3: Write `store.py`** (as in the prior revision — `now_iso`, `_z`, `IncidentStore` with the methods above; `put` serializes `detail.model_dump_json()` into `document`; `get` reads `SELECT document FROM incidents FINAL WHERE id = {id:String}`; `open_count` excludes `applied/rejected/not_reproduced`).

```python
# toolbox/rootlane_toolbox/store.py
from datetime import datetime, timezone
from .models import Action, IncidentDetail, IncidentSummary

_INCIDENT_COLS = ["id", "updated_at", "status", "severity", "category",
                  "opened_at", "title", "document"]
_ACTION_COLS = ["ts", "guild_session_id", "incident_id", "operation",
                "args_hash", "outcome", "duration_ms", "on_behalf_of"]


def now_iso() -> str:
    """Current UTC time as ISO-8601 with a trailing Z, millisecond precision."""
    n = datetime.now(timezone.utc)
    return n.strftime("%Y-%m-%dT%H:%M:%S.") + f"{n.microsecond // 1000:03d}Z"


def _z(value) -> str:
    if isinstance(value, str):
        return value if value.endswith("Z") else value.replace(" ", "T") + "Z"
    return value.strftime("%Y-%m-%dT%H:%M:%S.") + f"{value.microsecond // 1000:03d}Z"


class IncidentStore:
    """Incident documents (latest-wins) and the append-only agent audit."""

    def __init__(self, client): self._client = client

    def put(self, detail: IncidentDetail) -> None:
        row = [detail.id, now_iso(), detail.status, detail.severity, detail.category,
               detail.opened_at, detail.title, detail.model_dump_json()]
        self._client.insert("incidents", [row], column_names=_INCIDENT_COLS)

    def get(self, incident_id: str) -> IncidentDetail | None:
        res = self._client.query("SELECT document FROM incidents FINAL WHERE id = {id:String}",
                                 parameters={"id": incident_id})
        return IncidentDetail.model_validate_json(res.result_rows[0][0]) if res.result_rows else None

    def list_summaries(self) -> list[IncidentSummary]:
        res = self._client.query("SELECT id, title, status, severity, category, opened_at "
                                 "FROM incidents FINAL ORDER BY opened_at DESC")
        return [IncidentSummary(id=r[0], title=r[1], status=r[2], severity=r[3],
                                category=r[4], opened_at=_z(r[5])) for r in res.result_rows]

    def open_count(self) -> int:
        res = self._client.query("SELECT count() FROM incidents FINAL WHERE status NOT IN "
                                 "('applied','rejected','not_reproduced')")
        return int(res.result_rows[0][0]) if res.result_rows else 0

    def record_action(self, action: Action, *, guild_session_id: str, args_hash: str) -> None:
        row = [action.ts, guild_session_id, action.incident_id, action.operation,
               args_hash, action.outcome, action.duration_ms, action.on_behalf_of]
        self._client.insert("agent_actions", [row], column_names=_ACTION_COLS)

    def list_actions(self, incident_id: str | None) -> list[Action]:
        if incident_id:
            res = self._client.query(
                "SELECT ts, incident_id, operation, outcome, duration_ms, on_behalf_of "
                "FROM agent_actions WHERE incident_id = {id:String} ORDER BY ts",
                parameters={"id": incident_id})
        else:
            res = self._client.query(
                "SELECT ts, incident_id, operation, outcome, duration_ms, on_behalf_of "
                "FROM agent_actions ORDER BY ts")
        return [Action(ts=_z(r[0]), incident_id=r[1], operation=r[2], outcome=r[3],
                       duration_ms=int(r[4]), on_behalf_of=r[5]) for r in res.result_rows]
```

- [ ] **Step 4: Run the test, expect pass.** → PASS.

- [ ] **Step 5: Commit**

```bash
git add toolbox/rootlane_toolbox/store.py toolbox/tests/test_store.py
git commit -m "Add the incident document store and agent audit writer"
```

---

---

## P1 and packaging — executed from a snapshot (do not re-plan here)

Tasks 1, 2, 4, 5 above and the dashboard read endpoints (6), approve/reject (7), ingest `POST /internal/events`, SSE `GET /api/stream`, app assembly (13) and packaging (14) are **P1 + packaging**, already in execution from `.superpowers/sdd/2026-10-09-rootlane-backend/` (`p1-overrides.md`, `pkg-brief.md`, per-task briefs). The binding interfaces the P2/P3 tasks below build on:

- **Settings** carries `triage_base_url` (`https://api.akashml.com/v1`), `triage_model` (`zai-org/GLM-5.3`), `triage_api_key`, `analyze_interval_s` (10), `ingest_token`, `cors_origins`; **no** `akashml_*`/`target_port`.
- **`rootlane_toolbox/broker.py`** — in-process pub/sub: `broker.publish(event: str, data: dict)`, per-subscriber bounded `asyncio.Queue`. Events: `verdict`, `step`, `incident_update`, `ping`. The store publishes `step` and `incident_update`; **P2 publishes `verdict`**. Shapes per `ui/fixtures/stream-events.json`.
- **`create_app()` factory** (`rootlane_toolbox/app.py`) with `GET /healthz`, `CORSMiddleware(settings.cors_origins)`, routers mounted, **no** static mount, **no** analyzer start (P2 adds it).
- **`deps.py`** dependency callables `get_settings`, `get_db`, `get_ro_db`, `get_store`; **`IncidentStore`** (Task 5); **guards** (Task 3); **models** (Task 4).

**Priorities & parallelism:** P1 + packaging (running). Then **P2** (one task, below). Then **P3** (three tasks, below) — P3.1 is independent of P3.2/P3.3 and can run in parallel with P2; P3.2 depends on P3.1; P3.3 depends on P3.2 and is stretch. Optional chat is last.

---

### Task P2: Continuous analysis — generic features, pluggable decider, verdicts

**Priority P2.** Depends on P1 (Settings, store, broker, `create_app`). Scenario-agnostic: no feature, prompt, or branch may mention JWT/identity.

**Files:**
- Create: `toolbox/rootlane_toolbox/features.py`, `toolbox/rootlane_toolbox/decider.py`, `toolbox/rootlane_toolbox/guild.py`, `toolbox/rootlane_toolbox/analyzer.py`
- Modify: `toolbox/rootlane_toolbox/app.py` (start the analyzer thread on startup — this is the "P2 adds it" step)
- Create: `toolbox/tests/test_features.py`, `toolbox/tests/test_analyzer.py`, `toolbox/tests/test_features_sql_integration.py`

**Interfaces:**
- Produces `compute_features(db, window_start, window_end) -> dict`: `{"window_start","window_end","principals":[{principal_id, requests, errors, distinct_ips, distinct_routes, new_principal}], "ips":[{ip, requests, errors, auth_rejected, distinct_principals, distinct_routes, flagged_params}]}` — generic behavioural aggregates per principal and per IP over the window.
- Produces `Decider` protocol `decide(features: dict) -> {"verdict": "ignore"|"watch"|"escalate", "rationale": str, "model": str}`; `AkashMLDecider(settings, *, http=None)` the only implementation (OpenAI-compatible `/chat/completions` at `settings.triage_base_url`, model `settings.triage_model`, `Authorization: Bearer settings.triage_api_key`).
- Produces `GuildTrigger(settings, *, http=None).start_session(incident: dict) -> str | None` — **graceful**: empty trigger env or a failed call returns `None` (incident still opens).
- Produces `Analyzer(settings, db, store, decider, guild, broker)` with `run_once(now: datetime) -> None` and `run_forever() -> None`.

- [ ] **Step 1: Write the failing features test**

```python
# toolbox/tests/test_features.py
from rootlane_toolbox.features import compute_features
from tests.conftest import FakeDB  # P1's fake: responses keyed by SQL substring


def test_features_map_per_principal_and_per_ip():
    db = FakeDB(responses={
        "GROUP BY principal_id": [["22", 12, 3, 2, 5, 1]],   # requests,errors,distinct_ips,distinct_routes,new_principal
        "GROUP BY ip": [["198.51.100.23", 40, 6, 3, 2, 9, 1]]})  # requests,errors,auth_rejected,distinct_principals,distinct_routes,flagged_params
    f = compute_features(db, "2026-10-09T21:00:30Z", "2026-10-09T21:00:40Z")
    assert f["principals"][0] == {"principal_id": "22", "requests": 12, "errors": 3,
                                  "distinct_ips": 2, "distinct_routes": 5, "new_principal": 1}
    assert f["ips"][0]["flagged_params"] == 9 and f["ips"][0]["auth_rejected"] == 3
```

- [ ] **Step 2: Run it, expect failure.** `uv run pytest tests/test_features.py -v` → FAIL.

- [ ] **Step 3: Write `features.py`**

```python
# toolbox/rootlane_toolbox/features.py
_PRINCIPALS = """
SELECT principal_id, count() AS requests, countIf(status >= 400) AS errors,
       uniqExact(ip) AS distinct_ips, uniqExact(route) AS distinct_routes,
       principal_id NOT IN (
         SELECT claimed_identity FROM auth_events
         WHERE event = 'login_success' AND ts <= {end:String}) AS new_principal
FROM http_requests
WHERE ts > {start:String} AND ts <= {end:String} AND principal_id != ''
GROUP BY principal_id
"""
_IPS = """
SELECT ip, count() AS requests, countIf(status >= 400) AS errors,
       countIf(auth_outcome = 'rejected') AS auth_rejected,
       uniqExact(principal_id) AS distinct_principals, uniqExact(route) AS distinct_routes,
       countIf(length(param_flags) > 0) AS flagged_params
FROM http_requests
WHERE ts > {start:String} AND ts <= {end:String}
GROUP BY ip
"""


def compute_features(db, window_start: str, window_end: str) -> dict:
    """Generic per-principal and per-IP behavioural features over a window.

    Returns:
        dict: window bounds plus two lists of scenario-agnostic feature rows.
    """
    params = {"start": window_start, "end": window_end}
    pr = db.query(_PRINCIPALS, parameters=params)
    ips = db.query(_IPS, parameters=params)
    principals = [{"principal_id": r[0], "requests": int(r[1]), "errors": int(r[2]),
                   "distinct_ips": int(r[3]), "distinct_routes": int(r[4]),
                   "new_principal": int(r[5])} for r in pr.result_rows]
    ip_rows = [{"ip": r[0], "requests": int(r[1]), "errors": int(r[2]),
                "auth_rejected": int(r[3]), "distinct_principals": int(r[4]),
                "distinct_routes": int(r[5]), "flagged_params": int(r[6])} for r in ips.result_rows]
    return {"window_start": window_start, "window_end": window_end,
            "principals": principals, "ips": ip_rows}
```

Features are deliberately generic (volume, error rate, auth-rejection rate, fan-out, a never-logged-in principal flag) so the one analyzer serves identity, injection and authorization scenarios alike.

- [ ] **Step 4: Run it, expect pass.** → PASS.

- [ ] **Step 5: Write `decider.py` and `guild.py`**

```python
# toolbox/rootlane_toolbox/decider.py
import json
from typing import Protocol
import httpx
from .config import Settings

_PROMPT = (
    "You are a security analyst. Given behavioural features of recent web traffic, "
    "summarised per principal and per IP, judge whether anything looks like an attack "
    "or abuse. Reply with JSON {\"verdict\": one of ignore|watch|escalate, "
    "\"rationale\": one short sentence}. Escalate only on strong evidence. "
    "Do not assume any particular attack type.")


class Decider(Protocol):
    def decide(self, features: dict) -> dict: ...


class AkashMLDecider:
    """Decides a window's verdict and rationale with an AkashML open model."""

    def __init__(self, settings: Settings, *, http: httpx.Client | None = None):
        self._settings = settings
        self._http = http or httpx.Client(
            base_url=settings.triage_base_url,
            headers={"Authorization": f"Bearer {settings.triage_api_key}"}, timeout=20)

    def decide(self, features: dict) -> dict:
        resp = self._http.post("/chat/completions", json={
            "model": self._settings.triage_model,
            "messages": [{"role": "system", "content": _PROMPT},
                         {"role": "user", "content": json.dumps(features)}],
            "temperature": 0})
        resp.raise_for_status()
        content = resp.json()["choices"][0]["message"]["content"]
        parsed = _first_json(content)
        verdict = parsed.get("verdict", "watch")
        if verdict not in ("ignore", "watch", "escalate"):
            verdict = "watch"
        return {"verdict": verdict, "rationale": parsed.get("rationale", ""),
                "model": self._settings.triage_model}


def _first_json(text: str) -> dict:
    """Parse the first JSON object in the model's reply, tolerating prose around it."""
    start = text.find("{")
    if start < 0:
        return {}
    try:
        return json.loads(text[start:text.rfind("}") + 1])
    except json.JSONDecodeError:
        return {}
```

AkashML OpenAI-compatible base URL, `Authorization: Bearer`, `/chat/completions` from `docs/research/senso-akashml.md` §B1. `_first_json` avoids relying on `response_format` (unverified on AkashML).

```python
# toolbox/rootlane_toolbox/guild.py
import httpx
from .config import Settings


class GuildTrigger:
    """Starts a Guild agent session via the API trigger; degrades gracefully."""

    def __init__(self, settings: Settings, *, http: httpx.Client | None = None):
        self._settings = settings
        self._http = http or httpx.Client(base_url="https://api.guild.ai", timeout=20)

    def start_session(self, incident: dict) -> str | None:
        """Return the Guild session id, or None if no trigger key is configured yet."""
        if not (self._settings.guild_trigger_key_id and self._settings.guild_trigger_secret):
            return None
        owner, _, workspace = self._settings.guild_workspace.partition("/")
        try:
            resp = self._http.post(
                f"/v1/workspaces/{owner}/{workspace or owner}/sessions",
                auth=(self._settings.guild_trigger_key_id, self._settings.guild_trigger_secret),
                json={"session_type": "api_trigger", "agent_input": {"incident_id": incident["id"]}})
            resp.raise_for_status()
            return resp.json()["id"]
        except httpx.HTTPError:
            return None
```

Guild API trigger (`POST /v1/workspaces/{owner}/{workspace}/sessions`, HTTP Basic, body `{session_type:"api_trigger", agent_input}`, 201 `{id}`) from `docs/research/guild.md` §6. The trigger key exists only after the agent is published (spec Decisions), so `None` is the normal early state.

- [ ] **Step 6: Write the failing analyzer test**

```python
# toolbox/tests/test_analyzer.py
from datetime import datetime, timezone
from rootlane_toolbox.analyzer import Analyzer
from rootlane_toolbox.config import Settings
from rootlane_toolbox.store import IncidentStore
from tests.conftest import FakeDB


class StubDecider:
    def __init__(self, verdict): self._v = verdict
    def decide(self, features): return {"verdict": self._v, "rationale": "r", "model": "akashml/glm"}


class SpyGuild:
    def __init__(self, sid): self._sid = sid; self.calls = []
    def start_session(self, incident): self.calls.append(incident["id"]); return self._sid


class SpyBroker:
    def __init__(self): self.published = []
    def publish(self, event, data): self.published.append((event, data))


def _analyzer(verdict, guild_sid):
    db = FakeDB(responses={"GROUP BY principal_id": [["22", 10, 0, 1, 3, 1]],
                           "GROUP BY ip": [["1.2.3.4", 10, 0, 0, 1, 3, 0]]})
    store = IncidentStore(db)
    broker = SpyBroker()
    a = Analyzer(Settings(), db, store, StubDecider(verdict), SpyGuild(guild_sid), broker)
    return a, db, broker


def test_verdict_is_stored_and_published():
    a, db, broker = _analyzer("watch", None)
    a.run_once(now=datetime(2026, 10, 9, 21, 0, 40, tzinfo=timezone.utc))
    assert db.inserted["analyzer_windows"][0][2] == "watch"          # verdict column
    assert ("verdict", ) == (broker.published[0][0],)                # published to SSE
    assert "incidents" not in db.inserted                            # watch opens nothing


def test_escalate_opens_incident_and_starts_guild():
    a, db, broker = _analyzer("escalate", "gs_test")
    a.run_once(now=datetime(2026, 10, 9, 21, 0, 40, tzinfo=timezone.utc))
    assert db.inserted["incidents"]
    assert a.guild.calls == ["inc_1"]


def test_escalate_opens_incident_even_when_guild_unavailable():
    a, db, broker = _analyzer("escalate", None)   # no trigger key yet
    a.run_once(now=datetime(2026, 10, 9, 21, 0, 40, tzinfo=timezone.utc))
    assert db.inserted["incidents"]                                  # incident still opened
    doc = db.inserted["incidents"][0]
    assert '"guild_session_id":null' in doc[-1] or '"guild_session_id": null' in doc[-1]
```

- [ ] **Step 7: Run it, expect failure.** → FAIL (module missing).

- [ ] **Step 8: Write `analyzer.py`**

```python
# toolbox/rootlane_toolbox/analyzer.py
import time
from datetime import datetime, timedelta, timezone
from .config import Settings
from .features import compute_features
from .models import IncidentDetail
from .store import IncidentStore, now_iso, _z

_WINDOW_COLS = ["window_start", "window_end", "verdict", "model", "rationale"]


class Analyzer:
    """Computes window features, asks the decider for a verdict, and escalates."""

    def __init__(self, settings: Settings, db, store: IncidentStore, decider, guild, broker):
        self._settings = settings
        self._db = db
        self._store = store
        self._decider = decider
        self.guild = guild
        self._broker = broker
        self._seq = 0

    def run_once(self, now: datetime) -> None:
        end = _z(now)
        start = _z(now - timedelta(seconds=self._settings.analyze_interval_s))
        features = compute_features(self._db, start, end)
        decision = self._decider.decide(features)
        self._db.insert("analyzer_windows",
                        [[start, end, decision["verdict"], decision["model"], decision["rationale"]]],
                        column_names=_WINDOW_COLS)
        self._broker.publish("verdict", {"window_start": start, "window_end": end,
                                         "verdict": decision["verdict"], "model": decision["model"],
                                         "rationale": decision["rationale"]})
        if decision["verdict"] == "escalate":
            self._open_incident(features, decision)

    def _open_incident(self, features: dict, decision: dict) -> None:
        self._seq += 1
        incident_id = f"inc_{self._seq}"
        detail = IncidentDetail(
            id=incident_id, title="Suspicious activity detected by continuous analysis",
            status="investigating", severity="high", category="unknown",
            opened_at=now_iso(), summary=decision["rationale"])
        detail.guild_session_id = self.guild.start_session({"id": incident_id})
        self._store.put(detail)  # store.put publishes the incident_update SSE event

    def run_forever(self) -> None:
        while True:
            self.run_once(now=datetime.now(timezone.utc))
            time.sleep(self._settings.analyze_interval_s)
```

The incident title/category are generic ("unknown" category, generic title); the agent refines category and severity as it investigates. `store.put` emitting `incident_update` is P1's behaviour (Piece B) — the analyzer relies on it, it does not publish that event itself.

- [ ] **Step 9: Run the analyzer test, expect pass.** → PASS.

- [ ] **Step 10: Start the analyzer on app startup** — in `create_app()` (`app.py`), after building `deps.state`, add a startup hook that constructs `Analyzer(settings, db, store, AkashMLDecider(settings), GuildTrigger(settings), broker)` and runs `run_forever` on a daemon thread. Guard it behind `settings.triage_api_key` being set so tests and local runs without a key don't spin a failing loop.

- [ ] **Step 11: Write the gated feature-SQL integration test**

```python
# toolbox/tests/test_features_sql_integration.py
import os
import pytest
from rootlane_toolbox.config import Settings
from rootlane_toolbox.db import clickhouse_client
from rootlane_toolbox.features import compute_features

pytestmark = pytest.mark.integration


@pytest.mark.skipif(not os.environ.get("CLICKHOUSE_HOST"), reason="needs live ClickHouse")
def test_features_aggregate_window_traffic():
    client = clickhouse_client(Settings.from_env(os.environ))
    client.command("TRUNCATE TABLE http_requests")
    client.insert("http_requests",
                  [["2026-10-09 21:00:33", "t1", "GET", "/api/Cards", 200, 12, "198.51.100.23", "22", "accepted", []]],
                  column_names=["ts", "trace_id", "method", "route", "status", "latency_ms",
                                "ip", "principal_id", "auth_outcome", "param_flags"])
    f = compute_features(client, "2026-10-09T21:00:00Z", "2026-10-09T21:01:00Z")
    assert any(p["principal_id"] == "22" for p in f["principals"])
```

- [ ] **Step 12: Run unit tests (integration skipped), expect pass.** `uv run pytest tests/test_features.py tests/test_analyzer.py -v` → PASS.

- [ ] **Step 13: Commit**

```bash
git add toolbox/rootlane_toolbox/features.py toolbox/rootlane_toolbox/decider.py toolbox/rootlane_toolbox/guild.py toolbox/rootlane_toolbox/analyzer.py toolbox/rootlane_toolbox/app.py toolbox/tests/test_features.py toolbox/tests/test_analyzer.py toolbox/tests/test_features_sql_integration.py
git commit -m "Add continuous analysis with a pluggable AkashML decider"
```

---

### Task P3.1: Tools API — auth, audit, query_events, read_source, semgrep_scan

**Priority P3.** Depends on P1 (deps, store, guards). Independent of P3.2/P3.3 — parallel with P2. Covers **Review Focus 1, 2**.

**Files:**
- Create: `toolbox/rootlane_toolbox/semgrep_runner.py`, `toolbox/rootlane_toolbox/tools.py`, `toolbox/tests/test_tools_readonly.py`
- Modify: `toolbox/rootlane_toolbox/app.py` (mount `tools_router`; register `GuardError → 400` handler if P1 did not)

**Interfaces:**
- `require_api_key(x_api_key, settings)` dependency (`X-API-Key` vs `settings.toolbox_api_key`; 401 on mismatch).
- `record(store, operation, incident_id, args, session_id, on_behalf_of)` context manager — times the call, writes one `agent_actions` row with outcome `ok`/`error`/`refused` and `args_hash = sha256(json(args))[:16]`.
- `run_semgrep(config, paths, *, runner=...) -> {"findings": int, "results": list}`.
- `tools_router` with `POST /tools/query_events` (`{sql}` → `{columns, rows}`, uses `assert_read_only_sql` + the RO client + `READ_ONLY_QUERY_SETTINGS`), `POST /tools/read_source` (`{path}` → `{path, content}`, uses `resolve_source_path`), `POST /tools/semgrep_scan` (`{config?, paths?}` → semgrep JSON summary).
- Session id from header `X-Guild-Session` (default `"unknown"`).

- [ ] **Step 1: Write the failing tools test** — assert: 401 without key; a write SQL returns 400 and records a `refused` audit row; `read_source` traversal → 400; a valid `read_source` returns file content. (Same test body as the earlier revision's `test_tools_readonly.py`; mount `tools_router` on a bare app and register the `GuardError → 400` handler in the test app.)

- [ ] **Step 2: Run it, expect failure.** → FAIL.

- [ ] **Step 3: Write `semgrep_runner.py` and `tools.py`** — `run_semgrep` runs `semgrep --json --quiet --config <config|rules/> <paths|.>` via an injectable runner and returns `{"findings": len(results), "results": results}` (Semgrep CLI JSON from `docs/research/clickhouse-semgrep-juiceshop.md` §B2). `tools.py` defines `require_api_key`, `record`, `_session`, and the three routes; `record` sets outcome `refused` on `GuardError` and re-raises so the audit row is still written. (Code as in the earlier revision; `GuardError` maps to HTTP 400 via the app handler.)

- [ ] **Step 4: Run the test, expect pass.** → PASS.

- [ ] **Step 5: Commit**

```bash
git add toolbox/rootlane_toolbox/semgrep_runner.py toolbox/rootlane_toolbox/tools.py toolbox/rootlane_toolbox/app.py toolbox/tests/test_tools_readonly.py
git commit -m "Add read-only tool endpoints with API-key auth and audit"
```

---

### Task P3.2: Sandbox — reproduce and verify_patch with the stored reproduction

**Priority P3.** Depends on P3.1. Covers the agent-supplied reproduction (spec Decisions §5). Scenario-agnostic: the agent supplies the request and the status that means "blocked"; the toolbox never infers an attack type.

**Files:**
- Create: `toolbox/rootlane_toolbox/sandbox.py`, `toolbox/scripts/replay.py`, `toolbox/scripts/regression_smoke.py`, `toolbox/tests/test_sandbox.py`, `toolbox/tests/test_tools_reproduce_verify.py`
- Modify: `toolbox/rootlane_toolbox/tools.py` (add `/tools/reproduce`, `/tools/verify_patch`), `toolbox/rootlane_toolbox/deps.py` (add `get_sandbox`)

**Interfaces:**
- `SandboxManager(settings, *, runner, builder)`:
  - `reproduce(reproduction: dict) -> {"status": int, "excerpt": str}` — builds a fresh replica, replays the agent's request (`{method, path, headers, body}`).
  - `verify_patch(diff, rule_yaml, reproduction) -> {hash, passed, exploit_before, exploit_after, regression:{passed,failed}, semgrep_old, semgrep_new}` — replays `reproduction` on the unpatched replica (must **not** equal `reproduction["expected_blocked_status"]`) and on the patched replica (must equal it), runs the regression smoke suite, and runs semgrep with `rule_yaml` on old (must fire) and new (must be silent). `passed` is the conjunction.
- Endpoints: `POST /tools/reproduce {incident_id, reproduction}` stores `reproduction` on the incident and returns the replay result; `POST /tools/verify_patch {incident_id, diff, rule_yaml}` reads the stored `reproduction`, runs the check, writes `verification` + `last_verify` on the incident, and publishes a `step`.
- `replay.py` replays one request JSON against a base URL → `{"status","excerpt"}`; `regression_smoke.py` runs login / product search / basket / authenticated profile with a valid token → `{"passed","failed"}` (spec §Testing). Both stay at the spec's level; no attack technique beyond the agent-supplied request.

- [ ] **Step 1: Write the failing sandbox test** (inject runner/builder; the generic pass rule)

```python
# toolbox/tests/test_sandbox.py
from rootlane_toolbox.config import Settings
from rootlane_toolbox.guards import diff_hash
from rootlane_toolbox.sandbox import SandboxManager

REPRO = {"method": "GET", "path": "/rest/basket/22", "headers": {}, "body": None,
         "expected_blocked_status": 401}


def _mgr(after=401, before=200, semgrep_old=2, semgrep_new=0, reg_failed=0):
    def runner(kind, **kw):
        return {"replay_before": {"status": before, "excerpt": "b"},
                "replay_after": {"status": after, "excerpt": "a"},
                "regression": {"passed": 6, "failed": reg_failed},
                "semgrep_old": {"findings": semgrep_old},
                "semgrep_new": {"findings": semgrep_new}}[kind]
    return SandboxManager(Settings(), runner=runner, builder=lambda diff: "/replica")


def test_verify_passes_when_blocked_after_and_rule_clean():
    r = _mgr().verify_patch("d", "y", REPRO)
    assert r["passed"] is True and r["hash"] == diff_hash("d")
    assert r["exploit_before"] == 200 and r["exploit_after"] == 401


def test_verify_fails_when_still_not_blocked():
    assert _mgr(after=200).verify_patch("d", "y", REPRO)["passed"] is False


def test_verify_fails_when_new_rule_still_fires():
    assert _mgr(semgrep_new=1).verify_patch("d", "y", REPRO)["passed"] is False


def test_verify_fails_when_regression_breaks():
    assert _mgr(reg_failed=1).verify_patch("d", "y", REPRO)["passed"] is False
```

- [ ] **Step 2: Run it, expect failure.** → FAIL.

- [ ] **Step 3: Write `sandbox.py`**

```python
# toolbox/rootlane_toolbox/sandbox.py
from .config import Settings
from .guards import diff_hash


class SandboxManager:
    """Rebuilds a throwaway replica and replays the agent's reproduction against it.

    Args:
        settings (Settings): runtime config (source root, sandbox port).
        runner: callable(kind, **kw) -> dict performing one check on a built replica.
        builder: callable(diff) -> str copying production, applying diff, rebuilding.
    """

    def __init__(self, settings: Settings, *, runner, builder):
        self._settings = settings
        self._runner = runner
        self._builder = builder

    def reproduce(self, reproduction: dict) -> dict:
        self._builder("")
        return self._runner("replay_before", reproduction=reproduction)

    def verify_patch(self, diff: str, rule_yaml: str, reproduction: dict) -> dict:
        blocked = reproduction["expected_blocked_status"]
        self._builder("")
        before = self._runner("replay_before", reproduction=reproduction)
        semgrep_old = self._runner("semgrep_old", rule_yaml=rule_yaml)
        self._builder(diff)
        after = self._runner("replay_after", reproduction=reproduction)
        regression = self._runner("regression")
        semgrep_new = self._runner("semgrep_new", rule_yaml=rule_yaml)
        passed = (before["status"] != blocked and after["status"] == blocked
                  and regression["failed"] == 0
                  and semgrep_old["findings"] > 0 and semgrep_new["findings"] == 0)
        return {"hash": diff_hash(diff), "passed": passed,
                "exploit_before": before["status"], "exploit_after": after["status"],
                "regression": regression, "semgrep_old": semgrep_old["findings"],
                "semgrep_new": semgrep_new["findings"]}
```

The production `runner`/`builder` (git copy of `/app/juice-shop`, `git apply`, `npm run build:server`, launch on `settings.sandbox_port`, invoke `scripts/replay.py` / `scripts/regression_smoke.py` / `run_semgrep`) are wired in the app factory. `[not unit-tested — needs the real Node/Semgrep toolchain; covered by the first live run.]`

- [ ] **Step 4: Run the test, expect pass.** → PASS.

- [ ] **Step 5: Add `/tools/reproduce` and `/tools/verify_patch`** to `tools.py` and `get_sandbox` to `deps.py`. `reproduce` stores `body["reproduction"]` on the incident and returns `sandbox.reproduce(...)`; `verify_patch` reads the stored reproduction, calls `sandbox.verify_patch(diff, rule_yaml, reproduction)`, writes `verification` (`replica_before`/`replica_after`/`regression`/`semgrep_old`/`semgrep_new`) and `last_verify = {hash, passed}` onto the incident, publishes a `step`, and returns the result. Write a test (`test_tools_reproduce_verify.py`) with a fake sandbox asserting the reproduction is stored and `last_verify` is written.

- [ ] **Step 6: Run the suite, expect pass.** → PASS.

- [ ] **Step 7: Commit**

```bash
git add toolbox/rootlane_toolbox/sandbox.py toolbox/scripts toolbox/rootlane_toolbox/tools.py toolbox/rootlane_toolbox/deps.py toolbox/tests/test_sandbox.py toolbox/tests/test_tools_reproduce_verify.py
git commit -m "Add sandbox reproduce and verify_patch over a stored reproduction"
```

---

### Task P3.3: propose and apply (apply = PR + juiceshop redeploy — stretch)

**Priority P3, stretch.** Depends on P3.2. Covers **Review Focus 3, 4**. Do not design beyond the spec and research docs.

**Files:**
- Create: `toolbox/rootlane_toolbox/github_client.py`, `toolbox/tests/test_tools_gated.py`
- Modify: `toolbox/rootlane_toolbox/tools.py` (add `/tools/propose`, `/tools/apply`), `toolbox/rootlane_toolbox/deps.py` (add `get_github`)

**Interfaces:**
- `GitHubClient(token, repo, *, transport=None).open_pr(branch, base, title, body, path, content) -> str` — branch from `base`, commit `content` at `path`, open a PR (GitHub REST v3). `[research gap — GitHub REST not in docs/research/; verify against docs.github.com/rest before the live apply.]`
- `POST /tools/propose {incident_id, report, diff, rule_yaml}` → `{proposal_hash, status: "pending_approval"}`; refused (`GuardError → 400`) unless `last_verify` passed for `diff_hash(diff)`.
- `POST /tools/apply {incident_id}` → `{pr_url, production_status, variants}`; refused unless the stored `approval` matches `proposal.proposal_hash`. On success: open the PR on the fork from `rootlane/<incident-id>`, trigger a **juiceshop redeploy** from the patched source (new image tag via GitHub Actions + Akash deployment update through the Akash Console API — `docs/research/senso-akashml.md` §B2, using `settings.akash_console_api_key`), replay the stored reproduction against production (expect the blocked status), run the rule across the repo for variants. The redeploy + production replay + variant scan are `[not unit-tested — need Akash + the live target]`.

- [ ] **Step 1: Write the failing gated-tools test** — propose refused without a passing verify; propose accepted after `detail.last_verify = {hash: diff_hash(DIFF), passed: True}`; apply refused without a matching approval; a `GitHubClient` test over `httpx.MockTransport` returning `html_url`. (Bodies as in the earlier revision's `test_tools_gated.py`.)

- [ ] **Step 2: Run it, expect failure.** → FAIL.

- [ ] **Step 3: Write `github_client.py` and the two routes.** `propose` calls `assert_verify_passed(detail.last_verify, diff)` then stores `Proposal`, sets status `pending_approval`, publishes a `step`. `apply` calls `assert_approved(detail.approval.model_dump(), detail.proposal.proposal_hash)`, then `open_pr(...)`, `deployer.redeploy_juiceshop(...)`, `replay_production(...)`, `scan_variants(...)`, writes `ApplyResult` and status `applied`, publishes a `step`. The refusal paths short-circuit before the external calls, so the unit tests mount fakes.

- [ ] **Step 4: Run the tests, expect pass.** → PASS.

- [ ] **Step 5: Commit**

```bash
git add toolbox/rootlane_toolbox/github_client.py toolbox/rootlane_toolbox/tools.py toolbox/rootlane_toolbox/deps.py toolbox/tests/test_tools_gated.py
git commit -m "Add gated propose and apply with fork PR and redeploy"
```

---

### Task P3.4 (optional, last): Chat with the agent about an incident

**Optional — build only after P1–P3 work.** Endpoints `GET /api/incidents/{id}/messages` and `POST /api/incidents/{id}/messages` (per `ui/fixtures/messages.json`), stored on the incident document or a `messages` table; POST behind `X-Admin-Token`; new messages published as a `step` or a dedicated SSE event if the fixture defines one. Keep minimal; do not block P1–P3.

---

## Open Decisions / Blockers (for the user)

1. **Reproduction storage vs. the no-secrets rule (confirm).** Default in this plan (spec Decisions §5): the agent supplies the reproduction request (`method, path, headers, body, expected_blocked_status`) to `/tools/reproduce`; the toolbox **stores it on the incident** and replays it in `verify_patch` and in `apply`'s production replay. This is a deliberate, scoped artifact — distinct from telemetry, which never stores tokens/bodies. Confirm storing an agent-crafted request (which may carry a token/body) on the incident is acceptable, or restrict it (e.g. redact headers in the dashboard view).
2. **Guild `agent_input` schema.** `GuildTrigger` posts `{incident_id}`; must match the agent's `inputSchema` (separate agent plan). Confirm with `guild agent capabilities`. Trigger key exists only after the agent is published to `djimenezm2/hackaton`.
3. **GitHub REST contract** is a research gap; verify `GitHubClient` against `https://docs.github.com/rest` before the live apply.
4. **AkashML reply format** — `_first_json` tolerates prose; if GLM-5.3 reliably honours `response_format: json_object`, switch to it.
5. **SSE event schema for chat** — `ui/fixtures/messages.json` defines the chat shape; confirm whether chat messages get their own SSE event or reuse `step` before building P3.4.
6. **Apply redeploy (stretch)** — the juiceshop redeploy path (new image tag + Akash deployment update) spans two repos/apps and the Akash Console API; it is the last task and may not land before submission. Production replay confirms the fix regardless of the PR merge.

## Self-Review

- **Spec/Decisions coverage:** ingest + ClickHouse + dashboard API + SSE + packaging are P1/packaging (snapshot). This plan covers continuous analysis with a pluggable decider and generic features (P2), the agent tools incl. the stored-reproduction reproduce/verify and the gated propose/apply (P3), and optional chat. Telemetry middleware/submodule is Nana's — removed from this plan per the coordinator. Senso and the Guild agent are the separate agent plan.
- **Scenario-agnostic:** features, the triage prompt, the generic incident title/category, and the agent-supplied reproduction carry no JWT/identity specifics.
- **Placeholder scan:** external-toolchain wiring (production `runner`/`builder`, redeploy, production replay, variant scan, GitHub live apply) is labelled `[not unit-tested …]`; research gaps (GitHub REST, AkashML reply format) are flagged, not hidden.
- **Type consistency:** `diff_hash`, `assert_verify_passed`, `assert_approved`, `SandboxManager.verify_patch` keys, `IncidentDetail.last_verify`/`reproduction`, `broker.publish(event, data)` and the `verdict` shape are used consistently across P2 and P3 and match the P1 interfaces in the override files.
- **Review Focus:** 1–2 (Task P3.1), 3–4 (Tasks P3.1/P3.3 via the guards), 5 (P1 task 7), 6 (P1 Piece A ingest strict schema + Nana's `buildEvents`). All six have an owning test.


import hashlib
import hmac
import json
import time
import re
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel

from ..core.config import Settings
from .deps import get_ro_db, get_sandbox, get_settings, get_store
from ..core.guards import GuardError, assert_read_only_sql, diff_hash, resolve_source_path
from ..core.models import Action, AgentStep, IncidentDetail, Regression, ReplicaResult, Verification
from ..integrations.sandbox import PatchError, SandboxBusy, SandboxError, parse_reproduction
from ..integrations.semgrep_runner import RULES_DIR, run_semgrep
from ..storage.store import IncidentStore, now_iso

REGISTRY_PACK = re.compile(r"^p/[a-z0-9-]+$")
MAX_ROWS = 200
MAX_SOURCE_BYTES = 200_000


def require_api_key(
    x_api_key: str | None = Header(default=None),
    authorization: str | None = Header(default=None),
    settings: Settings = Depends(get_settings),
) -> None:
    """
    Authenticate a tool call by API key.

    Args:
        x_api_key (str | None): Key from the `X-API-Key` header.
        authorization (str | None): Fallback `Bearer <key>` header.
        settings (Settings): Holds the expected `toolbox_api_key`.

    Raises:
        HTTPException: 401 when the key is missing, empty or wrong.
    """
    presented = x_api_key
    if presented is None and authorization and authorization.lower().startswith("bearer "):
        presented = authorization[7:].strip()
    expected = settings.toolbox_api_key
    if not expected or not presented or not hmac.compare_digest(presented.encode(), expected.encode()):
        raise HTTPException(status_code=401, detail="invalid API key")


ID_PATTERN = re.compile(r"^[A-Za-z0-9_.:-]{1,64}$")


def _session(x_guild_session: str | None = Header(default=None)) -> str:
    return x_guild_session or ""


def _incident(x_incident_id: str | None = Header(default=None)) -> str:
    return x_incident_id or ""


def _pick(body_value: str | None, header_value: str) -> str:
    return body_value or header_value


def _json_cell(value):
    if isinstance(value, datetime):
        value = value if value.tzinfo else value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.") + f"{value.microsecond // 1000:03d}Z"
    return value


def _semgrep_config(config: str | None) -> str | None:
    if config is None:
        return None
    if config.startswith("-"):
        raise GuardError(f"illegal semgrep config: {config!r}")
    if REGISTRY_PACK.match(config):
        return config
    rules_dir = Path(RULES_DIR)
    target = resolve_source_path(str(rules_dir), config)
    if not target.is_file():
        raise GuardError(f"semgrep config not found in toolbox rules: {config!r}")
    return str(target)


def args_hash(args: dict) -> str:
    """Short stable digest of a call's arguments."""
    return hashlib.sha256(json.dumps(args, sort_keys=True, default=str).encode()).hexdigest()[:16]


@contextmanager
def record(
    store: IncidentStore,
    operation: str,
    incident_id: str,
    args: dict,
    session_id: str,
    on_behalf_of: str | None = None,
):
    """
    Time a tool call and write one `agent_actions` row when it ends.

    Args:
        store (IncidentStore): Audit writer.
        operation (str): Tool name.
        incident_id (str): Incident the call belongs to, empty when unknown.
        args (dict): Call arguments, hashed into the row.
        session_id (str): Guild session id.
        on_behalf_of (str | None): Identity shown on the dashboard; derived from the session by default.

    Note:
        The outcome is `ok`, `refused` for a `GuardError`, or `error` for anything else; the
        exception is re-raised after the row is written.
    """
    started = time.monotonic()
    outcome = "ok"
    valid_incident, valid_session = "", "unknown"
    try:
        if incident_id and not ID_PATTERN.match(incident_id):
            raise GuardError("illegal incident_id")
        if session_id and not ID_PATTERN.match(session_id):
            raise GuardError("illegal guild_session_id")
        valid_incident, valid_session = incident_id, session_id or "unknown"
        yield
    except GuardError:
        outcome = "refused"
        raise
    except BaseException:
        outcome = "error"
        raise
    finally:
        action = Action(
            ts=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z",
            incident_id=valid_incident,
            operation=operation,
            outcome=outcome,
            duration_ms=int((time.monotonic() - started) * 1000),
            on_behalf_of=on_behalf_of or f"rootlane-agent (Guild session {valid_session})",
        )
        store.record_action(action, guild_session_id=valid_session, args_hash=args_hash(args))


class ToolBody(BaseModel):
    incident_id: str | None = None
    guild_session_id: str | None = None


class QueryBody(ToolBody):
    sql: str


class SourceBody(ToolBody):
    path: str


class ScanBody(ToolBody):
    config: str | None = None
    paths: list[str] | None = None


tools_router = APIRouter(prefix="/tools", dependencies=[Depends(require_api_key)])


@tools_router.post("/query_events")
def query_events(
    body: QueryBody,
    store: IncidentStore = Depends(get_store),
    ro_db=Depends(get_ro_db),
    header_session: str = Depends(_session),
    header_incident: str = Depends(_incident),
) -> dict:
    """
    Run one read-only SQL statement through the read-only ClickHouse principal.

    Note:
        `incident_id` and `guild_session_id` (body, or the `X-Incident-Id` / `X-Guild-Session`
        headers) are caller-supplied and not verified.
    """
    with record(
        store, "query_events", _pick(body.incident_id, header_incident), body.model_dump(),
        _pick(body.guild_session_id, header_session),
    ):
        sql = assert_read_only_sql(body.sql)
        result = ro_db.query(sql)
        rows = [[_json_cell(c) for c in r] for r in result.result_rows[:MAX_ROWS]]
        return {
            "columns": list(result.column_names),
            "rows": rows,
            "truncated": len(result.result_rows) > MAX_ROWS,
        }


@tools_router.post("/read_source")
def read_source(
    body: SourceBody,
    store: IncidentStore = Depends(get_store),
    settings: Settings = Depends(get_settings),
    header_session: str = Depends(_session),
    header_incident: str = Depends(_incident),
) -> dict:
    """Return a file from the production source tree."""
    with record(
        store, "read_source", _pick(body.incident_id, header_incident), body.model_dump(),
        _pick(body.guild_session_id, header_session),
    ):
        target = resolve_source_path(settings.production_source_root, body.path)
        if "node_modules" in target.parts:
            raise GuardError("node_modules is not readable")
        if not target.is_file():
            raise HTTPException(status_code=404, detail="file not found")
        with target.open("rb") as handle:
            data = handle.read(MAX_SOURCE_BYTES + 1)
        return {
            "path": body.path,
            "content": data[:MAX_SOURCE_BYTES].decode("utf-8", errors="replace"),
            "truncated": len(data) > MAX_SOURCE_BYTES,
        }


@tools_router.post("/semgrep_scan")
def semgrep_scan(
    body: ScanBody,
    store: IncidentStore = Depends(get_store),
    settings: Settings = Depends(get_settings),
    header_session: str = Depends(_session),
    header_incident: str = Depends(_incident),
) -> dict:
    """Run Semgrep over the production source tree and return the findings."""
    with record(
        store, "semgrep_scan", _pick(body.incident_id, header_incident), body.model_dump(),
        _pick(body.guild_session_id, header_session),
    ):
        root = settings.production_source_root
        config = _semgrep_config(body.config)
        for path in body.paths or []:
            if path.startswith("-"):
                raise GuardError(f"illegal path: {path!r}")
            resolve_source_path(root, path)
        try:
            return run_semgrep(config, body.paths, cwd=root)
        except RuntimeError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc


STEP_SUMMARY_CHARS = 300


class ReproduceBody(ToolBody):
    incident_id: str
    reproduction: dict


class VerifyBody(ToolBody):
    incident_id: str
    diff: str
    rule_yaml: str


def _load_incident(store: IncidentStore, incident_id: str) -> IncidentDetail:
    detail = store.get(incident_id)
    if detail is None:
        raise HTTPException(status_code=404, detail="incident not found")
    return detail


def _step(kind: str, summary: str, outcome: str) -> AgentStep:
    return AgentStep(ts=now_iso(), kind=kind, summary=summary[:STEP_SUMMARY_CHARS], outcome=outcome)


def _sandbox_http_error(exc: SandboxError) -> HTTPException:
    if isinstance(exc, PatchError):
        return HTTPException(status_code=422, detail=str(exc))
    if isinstance(exc, SandboxBusy):
        return HTTPException(status_code=409, detail=str(exc))
    return HTTPException(status_code=502, detail=str(exc))


def _outcome_word(status: int, blocked: int) -> str:
    return "request rejected" if status == blocked else "issue reproduced"


@tools_router.post("/reproduce")
def reproduce(
    body: ReproduceBody,
    store: IncidentStore = Depends(get_store),
    sandbox=Depends(get_sandbox),
    header_session: str = Depends(_session),
) -> dict:
    """Replay the agent's reproduction on a fresh replica and store it on the incident."""
    with record(
        store, "reproduce", body.incident_id, body.model_dump(), _pick(body.guild_session_id, header_session)
    ):
        detail = _load_incident(store, body.incident_id)
        try:
            reproduction = parse_reproduction(body.reproduction)
        except GuardError as exc:
            store.put(detail, step=_step("replay", f"Reproduction refused: {exc}", "refused"))
            raise
        target = f"{reproduction.method} {urlsplit(reproduction.path).path}"
        try:
            result = sandbox.reproduce(reproduction)
        except SandboxError as exc:
            store.put(detail, step=_step("replay", f"Replica replay of {target} failed: {exc}", "error"))
            raise _sandbox_http_error(exc) from exc
        detail.reproduction = reproduction.model_dump()
        store.put(detail, step=_step("replay", f"Replica replay of {target}: {result['status']}", "ok"))
        return result


@tools_router.post("/verify_patch")
def verify_patch(
    body: VerifyBody,
    store: IncidentStore = Depends(get_store),
    sandbox=Depends(get_sandbox),
    header_session: str = Depends(_session),
) -> dict:
    """Check a candidate patch on replicas against the stored reproduction and record the result."""
    with record(
        store, "verify_patch", body.incident_id, body.model_dump(), _pick(body.guild_session_id, header_session)
    ):
        detail = _load_incident(store, body.incident_id)
        if detail.reproduction is None:
            raise GuardError("no stored reproduction for this incident; call reproduce first")
        reproduction = parse_reproduction(detail.reproduction)
        try:
            result = sandbox.verify_patch(body.diff, body.rule_yaml, reproduction)
        except SandboxError as exc:
            detail.last_verify = {"hash": diff_hash(body.diff), "passed": False}
            store.put(detail, step=_step("verify", f"Verification could not run: {exc}", "error"))
            raise _sandbox_http_error(exc) from exc
        blocked = reproduction.expected_blocked_status
        before = _outcome_word(result["exploit_before"], blocked)
        after = _outcome_word(result["exploit_after"], blocked)
        regression = result["regression"]
        detail.verification = Verification(
            replica_before=ReplicaResult(status=result["exploit_before"], summary=before),
            replica_after=ReplicaResult(status=result["exploit_after"], summary=after),
            regression=Regression(passed=regression["passed"], failed=regression["failed"]),
            semgrep_old=result["semgrep_old"],
            semgrep_new=result["semgrep_new"],
        )
        detail.last_verify = {"hash": result["hash"], "passed": result["passed"]}
        total = regression["passed"] + regression["failed"]
        summary = (
            f"Replica: {before} before patch, {after} after; "
            f"regression {regression['passed']}/{total}; "
            f"rule {result['semgrep_old']} old / {result['semgrep_new']} new"
        )
        store.put(detail, step=_step("verify", summary, "ok" if result["passed"] else "error"))
        return result

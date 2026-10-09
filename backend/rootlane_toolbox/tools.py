import hashlib
import hmac
import json
import time
from contextlib import contextmanager
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel

from .config import Settings
from .deps import get_ro_db, get_settings, get_store
from .guards import GuardError, assert_read_only_sql, resolve_source_path
from .models import Action
from .semgrep_runner import run_semgrep
from .store import IncidentStore

REGISTRY_PREFIXES = ("p/", "r/")


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
    if not expected or not presented or not hmac.compare_digest(presented, expected):
        raise HTTPException(status_code=401, detail="invalid API key")


def _session(x_guild_session: str | None = Header(default=None)) -> str:
    return x_guild_session or "unknown"


def _incident(x_incident_id: str | None = Header(default=None)) -> str:
    return x_incident_id or ""


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
    try:
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
            incident_id=incident_id,
            operation=operation,
            outcome=outcome,
            duration_ms=int((time.monotonic() - started) * 1000),
            on_behalf_of=on_behalf_of or f"rootlane-agent (Guild session {session_id})",
        )
        store.record_action(action, guild_session_id=session_id, args_hash=args_hash(args))


class QueryBody(BaseModel):
    sql: str


class SourceBody(BaseModel):
    path: str


class ScanBody(BaseModel):
    config: str | None = None
    paths: list[str] | None = None


tools_router = APIRouter(prefix="/tools", dependencies=[Depends(require_api_key)])


@tools_router.post("/query_events")
def query_events(
    body: QueryBody,
    store: IncidentStore = Depends(get_store),
    ro_db=Depends(get_ro_db),
    session_id: str = Depends(_session),
    incident_id: str = Depends(_incident),
) -> dict:
    """Run one read-only SQL statement through the read-only ClickHouse principal."""
    with record(store, "query_events", incident_id, body.model_dump(), session_id):
        sql = assert_read_only_sql(body.sql)
        result = ro_db.query(sql)
        return {"columns": list(result.column_names), "rows": [list(r) for r in result.result_rows]}


@tools_router.post("/read_source")
def read_source(
    body: SourceBody,
    store: IncidentStore = Depends(get_store),
    settings: Settings = Depends(get_settings),
    session_id: str = Depends(_session),
    incident_id: str = Depends(_incident),
) -> dict:
    """Return a file from the production source tree."""
    with record(store, "read_source", incident_id, body.model_dump(), session_id):
        target = resolve_source_path(settings.production_source_root, body.path)
        if not target.is_file():
            raise HTTPException(status_code=404, detail="file not found")
        return {"path": body.path, "content": target.read_text(encoding="utf-8", errors="replace")}


@tools_router.post("/semgrep_scan")
def semgrep_scan(
    body: ScanBody,
    store: IncidentStore = Depends(get_store),
    settings: Settings = Depends(get_settings),
    session_id: str = Depends(_session),
    incident_id: str = Depends(_incident),
) -> dict:
    """Run Semgrep over the production source tree and return the findings."""
    with record(store, "semgrep_scan", incident_id, body.model_dump(), session_id):
        root = settings.production_source_root
        if body.config and not body.config.startswith(REGISTRY_PREFIXES):
            if "://" in body.config or body.config == "auto":
                raise GuardError(f"illegal semgrep config: {body.config!r}")
            resolve_source_path(root, body.config)
        for path in body.paths or []:
            resolve_source_path(root, path)
        try:
            return run_semgrep(body.config, body.paths, cwd=root)
        except RuntimeError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc

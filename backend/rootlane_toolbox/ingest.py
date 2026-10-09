import hmac
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Body, Depends, Header, HTTPException
from pydantic import BaseModel, Field, ValidationError

from .deps import get_db, get_settings
from .store import parse_iso

ingest_router = APIRouter()

_REQUEST_COLS = [
    "ts",
    "trace_id",
    "method",
    "route",
    "status",
    "latency_ms",
    "ip",
    "principal_id",
    "auth_outcome",
    "param_flags",
]
_AUTH_COLS = [
    "ts",
    "trace_id",
    "event",
    "jwt_alg",
    "claimed_identity",
    "principal_resolved",
    "status",
    "route",
    "ip",
]


class IngestEvent(BaseModel):
    """One telemetry event; fields outside this model are dropped on validation."""

    ts: str
    trace_id: str
    method: str
    route: str
    status: int = Field(ge=0, le=65535)
    latency_ms: int = Field(ge=0, le=4294967295)
    ip: str
    principal_id: str = ""
    auth_outcome: str = "none"
    param_flags: list[str] = []
    jwt_alg: str | None = None
    claimed_identity: str | None = None
    principal_resolved: bool | None = None

    @property
    def has_auth_detail(self) -> bool:
        """Whether the event carries any auth-specific field."""
        return any(
            v is not None for v in (self.jwt_alg, self.claimed_identity, self.principal_resolved)
        )


def require_ingest_token(
    authorization: str | None = Header(default=None), settings=Depends(get_settings)
) -> None:
    """Check `Authorization: Bearer <token>` against the configured ingest token."""
    expected = settings.ingest_token
    if not expected:
        raise HTTPException(status_code=503, detail="ingest is not configured")
    scheme, _, supplied = (authorization or "").partition(" ")
    if scheme.lower() != "bearer" or not supplied:
        raise HTTPException(status_code=401, detail="bad ingest token")
    if not hmac.compare_digest(supplied.encode(), expected.encode()):
        raise HTTPException(status_code=401, detail="bad ingest token")


def _request_row(event: IngestEvent, ts: datetime) -> list:
    return [
        ts,
        event.trace_id,
        event.method,
        event.route,
        event.status,
        event.latency_ms,
        event.ip,
        event.principal_id,
        event.auth_outcome,
        event.param_flags,
    ]


def _auth_row(event: IngestEvent, ts: datetime) -> list:
    return [
        ts,
        event.trace_id,
        event.auth_outcome,
        event.jwt_alg or "",
        event.claimed_identity or "",
        1 if event.principal_resolved else 0,
        event.status,
        event.route,
        event.ip,
    ]


def _items(payload: Any) -> list[Any]:
    """Normalize `{"events": [...]}`, a bare list or a single event into a list."""
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        events = payload.get("events")
        return events if isinstance(events, list) else [payload]
    raise HTTPException(status_code=422, detail="expected an event, a list or {events: [...]}")


@ingest_router.post("/internal/events", dependencies=[Depends(require_ingest_token)])
def ingest_events(payload: Any = Body(...), db=Depends(get_db)) -> dict:
    """
    Ingest telemetry events posted by the Juice Shop middleware.

    Args:
        payload (Any): `{"events": [...]}`, a bare list, or one event object.

    Returns:
        dict: How many events were stored (`accepted`) and skipped (`rejected`).

    Raises:
        HTTPException: 503 when no ingest token is configured, 401 on a wrong or
            missing bearer token, 422 when the body is not an event or list of events.
    """
    request_rows: list[list] = []
    auth_rows: list[list] = []
    rejected = 0
    for item in _items(payload):
        try:
            event = IngestEvent.model_validate(item)
            ts = parse_iso(event.ts)
        except (ValidationError, ValueError):
            rejected += 1
            continue
        request_rows.append(_request_row(event, ts))
        if event.has_auth_detail:
            auth_rows.append(_auth_row(event, ts))
    if request_rows:
        db.insert("http_requests", request_rows, column_names=_REQUEST_COLS)
    if auth_rows:
        db.insert("auth_events", auth_rows, column_names=_AUTH_COLS)
    return {"accepted": len(request_rows), "rejected": rejected}

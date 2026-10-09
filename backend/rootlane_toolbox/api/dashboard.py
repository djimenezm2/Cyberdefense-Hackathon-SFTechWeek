import hmac

from fastapi import APIRouter, Depends, Header, HTTPException, Query

from .deps import get_db, get_settings, get_store
from ..core.models import (
    Action,
    AgentState,
    AgentStep,
    AnalyzerState,
    Approval,
    ApproveBody,
    Event,
    IncidentDetail,
    IncidentSummary,
    Overview,
    RejectBody,
    RpsPoint,
    Window,
)
from ..storage.store import IncidentStore, _z, now_iso, parse_iso

dashboard_router = APIRouter()


def read_events(db, since: str | None, limit: int) -> list[Event]:
    """Return the newest http_requests rows, optionally only those after `since`."""
    where = "WHERE ts > parseDateTime64BestEffort({since:String}, 3, 'UTC')" if since else ""
    params = {"since": since, "limit": int(limit)} if since else {"limit": int(limit)}
    res = db.query(
        "SELECT ts, trace_id, method, route, status, latency_ms, ip, principal_id, "
        f"auth_outcome, param_flags FROM http_requests {where} ORDER BY ts DESC "
        "LIMIT {limit:UInt32}",
        parameters=params,
    )
    return [
        Event(
            ts=_z(r[0]),
            trace_id=r[1],
            method=r[2],
            route=r[3],
            status=int(r[4]),
            latency_ms=int(r[5]),
            ip=r[6],
            principal_id=r[7],
            auth_outcome=r[8],
            param_flags=list(r[9]),
        )
        for r in res.result_rows
    ]


def read_windows(db, limit: int) -> list[Window]:
    """Return the newest analyzer windows."""
    res = db.query(
        "SELECT window_start, window_end, verdict, model, rationale "
        "FROM analyzer_windows ORDER BY window_start DESC LIMIT {limit:UInt32}",
        parameters={"limit": int(limit)},
    )
    return [
        Window(
            window_start=_z(r[0]),
            window_end=_z(r[1]),
            verdict=r[2],
            model=r[3],
            rationale=r[4],
        )
        for r in res.result_rows
    ]


def build_overview(db, store: IncidentStore) -> Overview:
    """Assemble the overview: request series, open incidents, analyzer and agent state."""
    rps = db.query(
        "SELECT toStartOfInterval(ts, INTERVAL 10 SECOND) AS t, count() AS total, "
        "countIf(status >= 400) AS errors, countIf(auth_outcome = 'rejected') AS auth_rejected "
        "FROM http_requests WHERE ts > now() - INTERVAL 2 MINUTE GROUP BY t ORDER BY t"
    )
    series = [
        RpsPoint(t=_z(r[0]), total=int(r[1]), errors=int(r[2]), auth_rejected=int(r[3]))
        for r in rps.result_rows
    ]
    win = db.query(
        "SELECT window_end, verdict, model FROM analyzer_windows ORDER BY window_start DESC LIMIT 1"
    )
    if win.result_rows:
        wr = win.result_rows[0]
        analyzer = AnalyzerState(last_window=_z(wr[0]), verdict=wr[1], model=wr[2])
    else:
        analyzer = AnalyzerState(last_window="", verdict="ignore", model="")
    running = next(
        (s for s in store.list_summaries() if s.status in ("investigating", "applying")), None
    )
    agent = AgentState(running=running is not None, incident_id=running.id if running else None)
    return Overview(
        rps_series=series, open_incidents=store.open_count(), analyzer=analyzer, agent=agent
    )


@dashboard_router.get("/api/overview", response_model=Overview)
def overview(db=Depends(get_db), store: IncidentStore = Depends(get_store)):
    return build_overview(db, store)


@dashboard_router.get("/api/events", response_model=list[Event])
def events(since: str | None = None, limit: int = Query(100, ge=1, le=500), db=Depends(get_db)):
    if since is not None:
        try:
            parse_iso(since)
        except ValueError:
            raise HTTPException(status_code=422, detail="since must be an ISO-8601 timestamp")
    return read_events(db, since, limit)


@dashboard_router.get("/api/windows", response_model=list[Window])
def windows(limit: int = Query(20, ge=1, le=100), db=Depends(get_db)):
    return read_windows(db, limit)


@dashboard_router.get("/api/incidents", response_model=list[IncidentSummary])
def incidents(store: IncidentStore = Depends(get_store)):
    return store.list_summaries()


@dashboard_router.get("/api/incidents/{incident_id}", response_model=IncidentDetail)
def incident_detail(incident_id: str, store: IncidentStore = Depends(get_store)):
    detail = store.get(incident_id)
    if detail is None:
        raise HTTPException(status_code=404, detail="incident not found")
    return detail


@dashboard_router.get("/api/actions", response_model=list[Action])
def actions(incident_id: str | None = None, store: IncidentStore = Depends(get_store)):
    return store.list_actions(incident_id)


def require_admin_token(
    x_admin_token: str | None = Header(default=None), settings=Depends(get_settings)
) -> None:
    """Reject the request unless X-Admin-Token matches the configured admin token."""
    expected = settings.admin_token
    if not expected or not x_admin_token:
        raise HTTPException(status_code=401, detail="bad admin token")
    if not hmac.compare_digest(x_admin_token.encode(), expected.encode()):
        raise HTTPException(status_code=401, detail="bad admin token")


def _decide(incident_id: str, store: IncidentStore, approver: str, decision: str, reason):
    detail = store.get(incident_id)
    if detail is None:
        raise HTTPException(status_code=404, detail="incident not found")
    if detail.status != "pending_approval":
        raise HTTPException(status_code=409, detail=f"incident is {detail.status}, not pending_approval")
    if detail.proposal is None:
        raise HTTPException(status_code=409, detail="no proposal to decide")
    detail.approval = Approval(
        approver=approver,
        decision=decision,
        ts=now_iso(),
        reason=reason,
        proposal_hash=detail.proposal.proposal_hash,
    )
    detail.status = "applying" if decision == "approve" else "rejected"
    store.put(
        detail,
        step=AgentStep(
            ts=now_iso(), kind="approval", summary=f"{decision} by {approver}", outcome="ok"
        ),
    )
    return detail


@dashboard_router.post(
    "/api/incidents/{incident_id}/approve",
    response_model=IncidentDetail,
    dependencies=[Depends(require_admin_token)],
)
def approve(incident_id: str, body: ApproveBody, store: IncidentStore = Depends(get_store)):
    return _decide(incident_id, store, body.approver, "approve", None)


@dashboard_router.post(
    "/api/incidents/{incident_id}/reject",
    response_model=IncidentDetail,
    dependencies=[Depends(require_admin_token)],
)
def reject(incident_id: str, body: RejectBody, store: IncidentStore = Depends(get_store)):
    return _decide(incident_id, store, body.approver, "reject", body.reason)

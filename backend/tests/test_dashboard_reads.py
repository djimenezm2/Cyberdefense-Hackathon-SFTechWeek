from rootlane_toolbox.core.models import IncidentDetail
from rootlane_toolbox.storage.store import IncidentStore, now_iso
from tests.conftest import FakeDB


def _detail():
    return IncidentDetail.model_validate(
        dict(
            id="inc_01",
            title="t",
            status="pending_approval",
            severity="high",
            category="identity",
            opened_at=now_iso(),
            summary="s",
        )
    )


def test_incident_detail_round_trips_through_api(make_app):
    db = FakeDB(responses={"SELECT document FROM incidents": [[_detail().model_dump_json()]]})
    client = make_app(db=db, store=IncidentStore(db))
    r = client.get("/api/incidents/inc_01")
    assert r.status_code == 200
    assert r.json()["id"] == "inc_01"
    assert r.json()["status"] == "pending_approval"


def test_missing_incident_is_404(make_app):
    client = make_app(db=FakeDB())
    assert client.get("/api/incidents/nope").status_code == 404


def test_overview_shape(make_app):
    db = FakeDB(
        responses={
            "GROUP BY": [["2026-10-09T21:00:00Z", 42, 1, 0]],
            "count()": [[1]],
            "FROM analyzer_windows": [["2026-10-09T21:00:30Z", "escalate", "akashml/glm"]],
        }
    )
    client = make_app(db=db, store=IncidentStore(db))
    body = client.get("/api/overview").json()
    assert set(body) == {"rps_series", "open_incidents", "analyzer", "agent"}
    assert body["analyzer"]["verdict"] == "escalate"
    assert body["rps_series"][0]["total"] == 42


def test_events_returns_contract_fields(make_app):
    row = [
        "2026-10-09T21:00:31.120Z", "a1f3", "GET", "/rest/products/search", 200, 18,
        "203.0.113.7", "", "none", [],
    ]
    client = make_app(db=FakeDB(responses={"FROM http_requests": [row]}))
    body = client.get("/api/events").json()
    assert body[0]["trace_id"] == "a1f3" and body[0]["param_flags"] == []


def test_windows_and_actions_lists(make_app):
    db = FakeDB(
        responses={
            "FROM analyzer_windows": [
                ["2026-10-09T21:00:30Z", "2026-10-09T21:00:40Z", "watch", "m", "why"]
            ],
            "FROM agent_actions": [
                ["2026-10-09T21:00:45Z", "inc_01", "query_events", "ok", 140, "rootlane-agent"]
            ],
        }
    )
    client = make_app(db=db, store=IncidentStore(db))
    assert client.get("/api/windows").json()[0]["verdict"] == "watch"
    assert client.get("/api/actions").json()[0]["operation"] == "query_events"


def test_limit_below_one_is_422(make_app):
    client = make_app()
    assert client.get("/api/events?limit=0").status_code == 422
    assert client.get("/api/windows?limit=0").status_code == 422


def test_unparsable_since_is_422(make_app):
    client = make_app()
    assert client.get("/api/events?since=not-a-time").status_code == 422
    assert client.get("/api/events?since=2026-10-09T21:00:31.120Z").status_code == 200

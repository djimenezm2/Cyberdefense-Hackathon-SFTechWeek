import os
import uuid

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from rootlane_toolbox.api import deps
from rootlane_toolbox.core.config import Settings
from rootlane_toolbox.api.dashboard import dashboard_router, read_events
from rootlane_toolbox.storage.db import clickhouse_client
from rootlane_toolbox.api.ingest import ingest_router
from rootlane_toolbox.storage.migrate import load_statements, prepare_statements, run_migrations
from rootlane_toolbox.api.dashboard import build_overview
from rootlane_toolbox.core.models import IncidentDetail
from rootlane_toolbox.storage.store import IncidentStore, now_iso

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(not os.environ.get("CLICKHOUSE_HOST"), reason="CLICKHOUSE_HOST not set"),
]


@pytest.fixture(scope="module")
def db():
    return clickhouse_client(Settings.from_env(os.environ))


def test_migrations_are_idempotent(db):
    statements = [s for s in load_statements() if "__RO_USER__" not in s]
    run_migrations(db, statements)
    run_migrations(db, statements)


@pytest.mark.skipif(not os.environ.get("CLICKHOUSE_RO_PASSWORD"), reason="CLICKHOUSE_RO_PASSWORD not set")
def test_read_only_user_is_capped_and_cannot_write(db):
    settings = Settings.from_env(os.environ)
    run_migrations(db, prepare_statements(load_statements(), ro_user=settings.clickhouse_ro_user,
                                          ro_password=settings.clickhouse_ro_password,
                                          database=settings.clickhouse_database))
    ro = clickhouse_client(settings, read_only=True)
    assert ro.query("SELECT 1").result_rows == [(1,)]
    assert len(ro.query("SELECT number FROM numbers(500)").result_rows) <= 249
    with pytest.raises(Exception, match="(?i)readonly|READONLY|ACCESS_DENIED|not enough privileges"):
        ro.command("INSERT INTO http_requests (trace_id) VALUES ('ro-must-fail')")
    with pytest.raises(Exception, match="(?i)readonly|READONLY|ACCESS_DENIED|not enough privileges"):
        ro.command("DROP TABLE http_requests")


def test_overview_queries_run_against_the_live_schema(db):
    overview = build_overview(db, IncidentStore(db))
    assert overview.open_incidents >= 0


def test_ingested_event_is_read_back_and_cleaned_up(db):
    trace = f"it-{uuid.uuid4().hex[:12]}"
    deps.state.settings = Settings(ingest_token="it-token")
    deps.state.db = db
    app = FastAPI()
    app.include_router(ingest_router)
    app.include_router(dashboard_router)
    client = TestClient(app)
    event = {
        "ts": now_iso(), "trace_id": trace, "method": "GET", "route": "/it", "status": 200,
        "latency_ms": 5, "ip": "192.0.2.1", "principal_id": "7", "auth_outcome": "accepted",
        "param_flags": ["meta_chars"], "password": "must-not-be-stored",
    }
    try:
        r = client.post("/internal/events", json={"events": [event]},
                        headers={"Authorization": "Bearer it-token"})
        assert r.json() == {"accepted": 1, "rejected": 0}
        rows = [e for e in read_events(db, None, 50) if e.trace_id == trace]
        assert len(rows) == 1 and rows[0].param_flags == ["meta_chars"]
    finally:
        db.command("DELETE FROM http_requests WHERE trace_id = {t:String}", parameters={"t": trace})


def test_incident_store_round_trip_latest_wins(db):
    incident_id = f"it_{uuid.uuid4().hex[:10]}"
    store = IncidentStore(db)
    detail = IncidentDetail(id=incident_id, title="t", status="investigating", severity="low",
                            category="test", opened_at=now_iso(), summary="s")
    try:
        store.put(detail)
        detail.status = "rejected"
        store.put(detail)
        assert store.get(incident_id).status == "rejected"
        assert any(s.id == incident_id for s in store.list_summaries())
    finally:
        db.command("DELETE FROM incidents WHERE id = {i:String}", parameters={"i": incident_id})

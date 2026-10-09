import pytest
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

from rootlane_toolbox.api import deps, tools
from rootlane_toolbox.core.config import Settings
from rootlane_toolbox.core.guards import GuardError
from rootlane_toolbox.core.models import IncidentDetail
from rootlane_toolbox.storage.store import IncidentStore
from tests.test_tools_reproduce_verify import Broker, IncidentDB
from tests.test_tools_readonly import RoDB

HEADERS = {"X-API-Key": "agentkey"}


@pytest.fixture
def env(tmp_path):
    (tmp_path / "a.ts").write_text("x\n")
    db, broker = IncidentDB(), Broker()
    store = IncidentStore(db, broker=broker)
    store.put(IncidentDetail(id="inc_01", title="t", status="investigating", severity="high",
                             category="identity", opened_at="2026-10-09T21:00:41Z", summary="s"))
    broker.events.clear()
    deps.state.settings = Settings(toolbox_api_key="agentkey", production_source_root=str(tmp_path))
    deps.state.db = db
    deps.state.ro_db = RoDB()
    deps.state.store = store
    app = FastAPI()
    app.include_router(tools.tools_router)

    @app.exception_handler(GuardError)
    async def _guard(_request, exc):
        return JSONResponse({"detail": str(exc)}, status_code=400)

    return TestClient(app), store, broker


def _post(client, route, body, incident="inc_01"):
    return client.post(f"/tools/{route}", json={**body, "incident_id": incident}, headers=HEADERS)


def _steps(store, incident="inc_01"):
    return store.get(incident).steps


def test_query_events_appends_a_query_step(env):
    client, store, broker = env
    assert _post(client, "query_events", {"sql": "SELECT id, n FROM events"}).status_code == 200
    (step,) = _steps(store)
    assert (step.kind, step.outcome) == ("query", "ok")
    assert step.summary == "Ran a read-only query (2 rows)"
    assert [e for e, _ in broker.events if e == "step"] == ["step"]


def test_read_source_appends_a_read_source_step(env):
    client, store, _ = env
    _post(client, "read_source", {"path": "a.ts"})
    (step,) = _steps(store)
    assert (step.kind, step.outcome, step.summary) == ("read_source", "ok", "Read a.ts")


def test_semgrep_appends_a_semgrep_step(env, monkeypatch):
    client, store, _ = env
    monkeypatch.setattr(tools, "run_semgrep", lambda *a, **k: {"findings": 3, "results": []})
    _post(client, "semgrep_scan", {})
    (step,) = _steps(store)
    assert (step.kind, step.outcome, step.summary) == ("semgrep", "ok", "Semgrep: 3 findings")


def test_refused_call_appends_a_refused_step_without_the_sql(env):
    client, store, _ = env
    res = _post(client, "query_events", {"sql": "DROP TABLE secret_table"})
    assert res.status_code == 400
    (step,) = _steps(store)
    assert (step.kind, step.outcome) == ("query", "refused")
    assert "secret_table" not in step.summary


def test_error_call_appends_an_error_step(env):
    client, store, _ = env
    _post(client, "read_source", {"path": "missing.ts"})
    (step,) = _steps(store)
    assert (step.kind, step.outcome) == ("read_source", "error")


def test_unknown_incident_adds_no_step_and_call_is_served(env):
    client, store, broker = env
    res = _post(client, "read_source", {"path": "a.ts"}, incident="inc_nope")
    assert res.status_code == 200
    assert store.get("inc_nope") is None
    assert _steps(store) == []


def test_no_incident_id_adds_no_step(env):
    client, store, _ = env
    client.post("/tools/read_source", json={"path": "a.ts"}, headers=HEADERS)
    assert _steps(store) == []

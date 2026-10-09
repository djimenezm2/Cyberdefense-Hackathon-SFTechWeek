import json

import pytest
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

from rootlane_toolbox import deps, tools
from rootlane_toolbox.config import Settings
from rootlane_toolbox.guards import GuardError
from rootlane_toolbox.semgrep_runner import run_semgrep
from rootlane_toolbox.store import IncidentStore
from tests.conftest import FakeDB

KEY = {"X-API-Key": "agentkey", "X-Guild-Session": "gs_9c1"}


class QueryResult:
    column_names = ("id", "n")
    result_rows = [("a", 1), ("b", 2)]


class RoDB:
    def __init__(self):
        self.sql = []

    def query(self, sql, parameters=None):
        self.sql.append(sql)
        return QueryResult()


@pytest.fixture
def env(tmp_path):
    (tmp_path / "routes").mkdir()
    (tmp_path / "routes" / "login.ts").write_text("export const x = 1\n")
    db, ro = FakeDB(), RoDB()
    deps.state.settings = Settings(toolbox_api_key="agentkey", production_source_root=str(tmp_path))
    deps.state.db = db
    deps.state.ro_db = ro
    deps.state.store = IncidentStore(db)
    app = FastAPI()
    app.include_router(tools.tools_router)

    @app.exception_handler(GuardError)
    async def _guard(_request, exc):
        return JSONResponse({"detail": str(exc)}, status_code=400)

    return TestClient(app), db, ro


def _audit(db):
    return [dict(zip(db.columns["agent_actions"], row)) for row in db.inserted.get("agent_actions", [])]


def test_missing_or_wrong_key_is_401(env):
    client, db, _ = env
    assert client.post("/tools/query_events", json={"sql": "select 1"}).status_code == 401
    bad = {"X-API-Key": "nope"}
    assert client.post("/tools/query_events", json={"sql": "select 1"}, headers=bad).status_code == 401
    assert _audit(db) == []


def test_empty_server_key_rejects_everything(env):
    client, _, _ = env
    deps.state.settings = Settings(toolbox_api_key="")
    res = client.post("/tools/read_source", json={"path": "a"}, headers={"X-API-Key": ""})
    assert res.status_code == 401


def test_bearer_header_is_accepted(env):
    client, _, _ = env
    headers = {"Authorization": "Bearer agentkey"}
    res = client.post("/tools/read_source", json={"path": "routes/login.ts"}, headers=headers)
    assert res.status_code == 200


def test_query_events_returns_rows_and_audits(env):
    client, db, ro = env
    res = client.post("/tools/query_events", json={"sql": "SELECT id, n FROM events"}, headers=KEY)
    assert res.status_code == 200
    assert res.json() == {"columns": ["id", "n"], "rows": [["a", 1], ["b", 2]]}
    assert ro.sql == ["SELECT id, n FROM events"]
    got = _audit(db)[0]
    assert got["operation"] == "query_events"
    assert got["outcome"] == "ok"
    assert got["guild_session_id"] == "gs_9c1"
    assert got["on_behalf_of"] == "rootlane-agent (Guild session gs_9c1)"
    assert len(got["args_hash"]) == 16


def test_write_sql_is_400_and_audited_as_refused(env):
    client, db, ro = env
    res = client.post("/tools/query_events", json={"sql": "DROP TABLE events"}, headers=KEY)
    assert res.status_code == 400
    assert ro.sql == []
    assert _audit(db)[0]["outcome"] == "refused"


def test_read_source_traversal_is_400_and_refused(env):
    client, db, _ = env
    res = client.post("/tools/read_source", json={"path": "../etc/passwd"}, headers=KEY)
    assert res.status_code == 400
    assert _audit(db)[0]["outcome"] == "refused"


def test_read_source_returns_content(env):
    client, _, _ = env
    res = client.post("/tools/read_source", json={"path": "routes/login.ts"}, headers=KEY)
    assert res.json() == {"path": "routes/login.ts", "content": "export const x = 1\n"}


def test_read_source_missing_file_is_404_and_audited_as_error(env):
    client, db, _ = env
    res = client.post("/tools/read_source", json={"path": "routes/none.ts"}, headers=KEY)
    assert res.status_code == 404
    assert _audit(db)[0]["outcome"] == "error"


def test_session_defaults_to_unknown(env):
    client, db, _ = env
    headers = {"X-API-Key": "agentkey"}
    client.post("/tools/read_source", json={"path": "routes/login.ts"}, headers=headers)
    assert _audit(db)[0]["guild_session_id"] == "unknown"


def test_incident_header_lands_in_audit(env):
    client, db, _ = env
    headers = {**KEY, "X-Incident-Id": "inc_01"}
    client.post("/tools/read_source", json={"path": "routes/login.ts"}, headers=headers)
    assert _audit(db)[0]["incident_id"] == "inc_01"


def test_semgrep_scan_uses_runner(env, monkeypatch):
    client, db, _ = env
    calls = []

    def fake(config, paths, *, cwd):
        calls.append((config, paths, cwd))
        return {"findings": 1, "results": [{"check_id": "r1"}]}

    monkeypatch.setattr(tools, "run_semgrep", fake)
    res = client.post("/tools/semgrep_scan", json={"paths": ["routes"]}, headers=KEY)
    assert res.json() == {"findings": 1, "results": [{"check_id": "r1"}]}
    assert calls[0][1] == ["routes"]
    assert _audit(db)[0]["operation"] == "semgrep_scan"


def test_semgrep_scan_refuses_escaping_path(env):
    client, db, _ = env
    res = client.post("/tools/semgrep_scan", json={"paths": ["../x"]}, headers=KEY)
    assert res.status_code == 400
    assert _audit(db)[0]["outcome"] == "refused"


def test_semgrep_scan_refuses_url_config(env):
    client, _, _ = env
    res = client.post("/tools/semgrep_scan", json={"config": "https://evil.example/r.yml"}, headers=KEY)
    assert res.status_code == 400


def test_semgrep_scan_runner_failure_is_502_and_error(env, monkeypatch):
    client, db, _ = env

    def boom(config, paths, *, cwd):
        raise RuntimeError("semgrep exited 2")

    monkeypatch.setattr(tools, "run_semgrep", boom)
    res = client.post("/tools/semgrep_scan", json={}, headers=KEY)
    assert res.status_code == 502
    assert _audit(db)[0]["outcome"] == "error"


def test_run_semgrep_builds_command_and_parses_json():
    seen = {}

    def runner(args, cwd):
        seen["args"], seen["cwd"] = args, cwd
        return 0, json.dumps({"results": [{"check_id": "a"}, {"check_id": "b"}], "errors": []})

    out = run_semgrep(None, None, runner=runner, cwd="/src")
    assert seen["args"] == ["semgrep", "--json", "--quiet", "--config", "rules/", "."]
    assert seen["cwd"] == "/src"
    assert out == {"findings": 2, "results": [{"check_id": "a"}, {"check_id": "b"}]}


def test_run_semgrep_passes_config_and_paths():
    seen = {}

    def runner(args, cwd):
        seen["args"] = args
        return 1, json.dumps({"results": []})

    run_semgrep("p/default", ["a", "b"], runner=runner, cwd=".")
    assert seen["args"][3:] == ["--config", "p/default", "a", "b"]


def test_run_semgrep_raises_on_failure():
    with pytest.raises(RuntimeError):
        run_semgrep(None, None, runner=lambda a, c: (2, "boom"), cwd=".")

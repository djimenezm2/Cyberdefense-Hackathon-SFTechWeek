import json
from datetime import datetime, timezone
from pathlib import Path

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
    assert res.json() == {"columns": ["id", "n"], "rows": [["a", 1], ["b", 2]], "truncated": False}
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
    assert res.json() == {"path": "routes/login.ts", "content": "export const x = 1\n", "truncated": False}


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

    out = run_semgrep(None, None, runner=runner, cwd="/src", rules_dir=Path("/nonexistent"))
    assert seen["args"] == [
        "semgrep", "--json", "--quiet", "--metrics=off", "--config", "p/typescript", "--", ".",
    ]
    assert seen["cwd"] == "/src"
    assert out == {"findings": 2, "results": [{"check_id": "a"}, {"check_id": "b"}]}


def test_run_semgrep_passes_config_and_paths():
    seen = {}

    def runner(args, cwd):
        seen["args"] = args
        return 1, json.dumps({"results": []})

    run_semgrep("p/default", ["a", "b"], runner=runner, cwd=".")
    assert seen["args"][4:] == ["--config", "p/default", "--", "a", "b"]


def test_run_semgrep_raises_on_failure():
    with pytest.raises(RuntimeError):
        run_semgrep(None, None, runner=lambda a, c: (2, "boom"), cwd=".")


@pytest.mark.parametrize("bad", ["--autofix", "--output=/tmp/x", "-c", "--config=https://x.example/r.yml"])
def test_semgrep_scan_refuses_flag_like_paths(env, bad):
    client, db, _ = env
    res = client.post("/tools/semgrep_scan", json={"paths": [bad]}, headers=KEY)
    assert res.status_code == 400
    assert _audit(db)[0]["outcome"] == "refused"


@pytest.mark.parametrize("bad", ["--autofix", "p/a/b", "P/default", "p/x_y", "../x", "routes/login.ts", "auto", "/etc/x"])
def test_semgrep_scan_refuses_disallowed_config(env, bad, monkeypatch):
    client, _, _ = env
    monkeypatch.setattr(tools, "run_semgrep", lambda *a, **k: {"findings": 0, "results": []})
    res = client.post("/tools/semgrep_scan", json={"config": bad}, headers=KEY)
    assert res.status_code == 400


def test_semgrep_scan_allows_registry_pack_and_toolbox_rules(env, monkeypatch, tmp_path):
    client, _, _ = env
    rules = tmp_path / "toolbox-rules"
    rules.mkdir()
    (rules / "r.yml").write_text("rules: []\n")
    monkeypatch.setattr(tools, "RULES_DIR", rules)
    seen = []
    monkeypatch.setattr(tools, "run_semgrep", lambda c, p, **k: seen.append(c) or {"findings": 0, "results": []})
    for config in ("p/javascript", "r.yml"):
        assert client.post("/tools/semgrep_scan", json={"config": config}, headers=KEY).status_code == 200
    assert seen == ["p/javascript", str(rules / "r.yml")]


def test_run_semgrep_default_adds_local_rules_when_present(tmp_path):
    (tmp_path / "r.yml").write_text("rules: []\n")
    seen = {}

    def runner(args, cwd):
        seen["args"] = args
        return 0, "{}"

    run_semgrep(None, None, runner=runner, cwd=".", rules_dir=tmp_path)
    assert seen["args"][4:] == ["--config", "p/typescript", "--config", str(tmp_path), "--", "."]


def test_run_semgrep_ignores_gitkeep_only_rules_dir(tmp_path):
    (tmp_path / ".gitkeep").write_text("")
    seen = {}

    def runner(args, cwd):
        seen["args"] = args
        return 0, "{}"

    run_semgrep(None, None, runner=runner, cwd=".", rules_dir=tmp_path)
    assert "--config" in seen["args"] and str(tmp_path) not in seen["args"]


def test_query_events_truncates_to_200_rows(env):
    client, _, ro = env
    QueryResult.result_rows = [(str(i), i) for i in range(249)]
    try:
        res = client.post("/tools/query_events", json={"sql": "SELECT id, n FROM events"}, headers=KEY).json()
    finally:
        QueryResult.result_rows = [("a", 1), ("b", 2)]
    assert len(res["rows"]) == 200 and res["truncated"] is True


def test_query_events_renders_datetimes_as_iso_z(env):
    client, _, _ = env
    QueryResult.result_rows = [(datetime(2026, 10, 9, 21, 0, 31, 120000, tzinfo=timezone.utc), 1)]
    try:
        res = client.post("/tools/query_events", json={"sql": "SELECT id, n FROM events"}, headers=KEY).json()
    finally:
        QueryResult.result_rows = [("a", 1), ("b", 2)]
    assert res["rows"] == [["2026-10-09T21:00:31.120Z", 1]]


def test_read_source_truncates_large_files(env, tmp_path):
    client, _, _ = env
    (tmp_path / "big.txt").write_text("a" * 300_000)
    res = client.post("/tools/read_source", json={"path": "big.txt"}, headers=KEY).json()
    assert len(res["content"]) == 200_000 and res["truncated"] is True


def test_read_source_refuses_node_modules(env, tmp_path):
    client, db, _ = env
    (tmp_path / "node_modules" / "x").mkdir(parents=True)
    (tmp_path / "node_modules" / "x" / "i.js").write_text("1")
    res = client.post("/tools/read_source", json={"path": "node_modules/x/i.js"}, headers=KEY)
    assert res.status_code == 400
    assert _audit(db)[0]["outcome"] == "refused"


def test_non_ascii_api_key_does_not_crash(env):
    client, _, _ = env
    res = client.post("/tools/read_source", json={"path": "a"}, headers={"Authorization": "Bearer \u00e9".encode()})
    assert res.status_code == 401

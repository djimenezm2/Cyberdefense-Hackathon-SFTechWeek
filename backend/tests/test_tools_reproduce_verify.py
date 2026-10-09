import pytest
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

from rootlane_toolbox.api import deps, tools
from rootlane_toolbox.core.config import Settings
from rootlane_toolbox.core.guards import GuardError, assert_verify_passed, diff_hash
from rootlane_toolbox.core.models import IncidentDetail
from rootlane_toolbox.integrations.sandbox import PatchError, SandboxBusy, SandboxError
from rootlane_toolbox.storage.store import IncidentStore
from tests.conftest import FakeDB, RowsResult

KEY = {"X-API-Key": "agentkey", "X-Guild-Session": "gs_9c1"}
DIFF = "--- a/lib/insecurity.ts\n+++ b/lib/insecurity.ts\n@@ -1 +1 @@\n-a\n+b\n"
REPRO = {"method": "GET", "path": "/rest/basket/22",
         "headers": {"Host": "evil.example", "Authorization": "Bearer forged"},
         "body": None, "expected_blocked_status": 401}


class IncidentDB(FakeDB):
    """FakeDB whose incident reads return the latest inserted document."""

    def query(self, sql, parameters=None):
        if "SELECT document FROM incidents" in sql:
            rows = [r for r in self.inserted.get("incidents", []) if r[0] == parameters["id"]]
            return RowsResult([(rows[-1][7],)] if rows else [])
        return super().query(sql, parameters)


class Broker:
    def __init__(self):
        self.events = []

    def publish(self, event, data):
        self.events.append((event, data))


class FakeSandbox:
    def __init__(self, error=None, passed=True):
        self.error = error
        self.passed = passed
        self.calls = []

    def reproduce(self, reproduction):
        self.calls.append(("reproduce", reproduction))
        if self.error:
            raise self.error
        return {"status": 200, "excerpt": '{"data":{"id":22}}'}

    def verify_patch(self, diff, rule_yaml, reproduction):
        self.calls.append(("verify_patch", diff, rule_yaml, reproduction))
        if self.error:
            raise self.error
        return {"hash": diff_hash(diff), "passed": self.passed, "exploit_before": 200,
                "exploit_after": 401 if self.passed else 200,
                "replica_before": {"status": 200, "excerpt": "b"},
                "replica_after": {"status": 401 if self.passed else 200, "excerpt": "a"},
                "regression": {"passed": 6, "failed": 0, "failures": []},
                "semgrep_old": 2, "semgrep_new": 0}


@pytest.fixture
def env():
    db, broker, sandbox = IncidentDB(), Broker(), FakeSandbox()
    store = IncidentStore(db, broker=broker)
    store.put(IncidentDetail(id="inc_01", title="t", status="investigating", severity="high",
                             category="identity", opened_at="2026-10-09T21:00:41Z", summary="s"))
    broker.events.clear()
    deps.state.settings = Settings(toolbox_api_key="agentkey")
    deps.state.db = db
    deps.state.store = store
    deps.state.sandbox = sandbox
    app = FastAPI()
    app.include_router(tools.tools_router)

    @app.exception_handler(GuardError)
    async def _guard(_request, exc):
        return JSONResponse({"detail": str(exc)}, status_code=400)

    return TestClient(app), store, broker, sandbox, db


def _audit(db):
    return [dict(zip(db.columns["agent_actions"], row)) for row in db.inserted.get("agent_actions", [])]


def _reproduce(client, **over):
    return client.post("/tools/reproduce", json={"incident_id": "inc_01", "reproduction": REPRO, **over},
                       headers=KEY)


def _verify(client):
    return client.post("/tools/verify_patch",
                       json={"incident_id": "inc_01", "diff": DIFF, "rule_yaml": "rules: []"},
                       headers=KEY)


def test_tools_need_the_api_key(env):
    client, *_ = env
    assert client.post("/tools/reproduce", json={}).status_code == 401
    assert client.post("/tools/verify_patch", json={}).status_code == 401


def test_reproduce_stores_the_reproduction_and_returns_the_replay(env):
    client, store, broker, sandbox, db = env
    res = _reproduce(client)
    assert res.status_code == 200
    assert res.json() == {"status": 200, "excerpt": '{"data":{"id":22}}'}
    stored = store.get("inc_01").reproduction
    assert stored["path"] == "/rest/basket/22" and "Host" not in stored["headers"]
    assert sandbox.calls[0][1].headers == {"Authorization": "Bearer forged"}
    audit = _audit(db)[0]
    assert (audit["operation"], audit["outcome"], audit["incident_id"]) == ("reproduce", "ok", "inc_01")
    step = [d for e, d in broker.events if e == "step"][0]
    assert step["kind"] == "replay" and step["outcome"] == "ok" and "200" in step["summary"]
    assert "forged" not in step["summary"]


def test_reproduce_refuses_a_request_aimed_elsewhere(env):
    client, store, broker, sandbox, db = env
    res = _reproduce(client, reproduction={**REPRO, "path": "https://evil.example/"})
    assert res.status_code == 400
    assert sandbox.calls == [] and store.get("inc_01").reproduction is None
    assert _audit(db)[0]["outcome"] == "refused"
    assert [d["outcome"] for e, d in broker.events if e == "step"] == ["refused"]


def test_reproduce_on_unknown_incident_is_404(env):
    client, *_, db = env
    res = client.post("/tools/reproduce", json={"incident_id": "nope", "reproduction": REPRO},
                      headers=KEY)
    assert res.status_code == 404 and _audit(db)[0]["outcome"] == "error"


@pytest.mark.parametrize("error,status", [
    (SandboxBusy("another replica is running"), 409),
    (SandboxError("replica not ready after 120s"), 502),
])
def test_reproduce_maps_sandbox_failures(env, error, status):
    client, store, broker, sandbox, db = env
    sandbox.error = error
    res = _reproduce(client)
    assert res.status_code == status and str(error) in res.json()["detail"]
    assert _audit(db)[0]["outcome"] == "error"
    assert [d["outcome"] for e, d in broker.events if e == "step"] == ["error"]


def test_verify_without_a_stored_reproduction_is_refused(env):
    client, store, broker, sandbox, db = env
    res = _verify(client)
    assert res.status_code == 400 and "reproduce" in res.json()["detail"]
    assert sandbox.calls == [] and _audit(db)[0]["outcome"] == "refused"


def test_verify_uses_the_stored_reproduction_and_records_the_result(env):
    client, store, broker, sandbox, db = env
    _reproduce(client)
    broker.events.clear()
    res = _verify(client)
    assert res.status_code == 200 and res.json()["passed"] is True
    _, diff, rule, repro = sandbox.calls[1]
    assert (diff, rule, repro.path, repro.expected_blocked_status) == (DIFF, "rules: []", "/rest/basket/22", 401)
    detail = store.get("inc_01")
    assert detail.last_verify == {"hash": diff_hash(DIFF), "passed": True}
    assert_verify_passed(detail.last_verify, DIFF)
    v = detail.verification
    assert (v.replica_before.status, v.replica_after.status) == (200, 401)
    assert (v.replica_before.summary, v.replica_after.summary) == ("issue reproduced", "request rejected")
    assert (v.regression.passed, v.regression.failed, v.semgrep_old, v.semgrep_new) == (6, 0, 2, 0)
    step = [d for e, d in broker.events if e == "step"][0]
    assert step["kind"] == "verify" and step["outcome"] == "ok"
    assert [a["operation"] for a in _audit(db)] == ["reproduce", "verify_patch"]


def test_a_failed_verification_blocks_propose(env):
    client, store, broker, sandbox, db = env
    _reproduce(client)
    sandbox.passed = False
    broker.events.clear()
    assert _verify(client).json()["passed"] is False
    detail = store.get("inc_01")
    with pytest.raises(GuardError):
        assert_verify_passed(detail.last_verify, DIFF)
    assert detail.verification.replica_after.summary == "issue reproduced"
    assert [d["outcome"] for e, d in broker.events if e == "step"] == ["error"]


@pytest.mark.parametrize("headers", [
    {"X-Name": "café"},
    {"X-Name": "a\n"},
    {"X-Name": "a\r"},
    {"X\n": "a"},
])
def test_reproduce_refuses_an_illegal_header(env, headers):
    client, store, broker, sandbox, db = env
    res = _reproduce(client, reproduction={**REPRO, "headers": headers})
    assert res.status_code == 400
    assert sandbox.calls == [] and _audit(db)[0]["outcome"] == "refused"


def test_an_unrunnable_replica_during_verify_is_502_and_clears_the_gate(env):
    client, store, broker, sandbox, db = env
    _reproduce(client)
    sandbox.error = SandboxError("replica could not start: [Errno 2] No such file or directory: 'node'")
    broker.events.clear()
    res = _verify(client)
    assert res.status_code == 502 and "could not start" in res.json()["detail"]
    assert store.get("inc_01").last_verify == {"hash": diff_hash(DIFF), "passed": False}
    steps = [d for e, d in broker.events if e == "step"]
    assert [(s["kind"], s["outcome"]) for s in steps] == [("verify", "error")]
    assert _audit(db)[-1]["outcome"] == "error"


def test_a_diff_that_does_not_apply_is_422_and_clears_the_gate(env):
    client, store, broker, sandbox, db = env
    _reproduce(client)
    store_detail = store.get("inc_01")
    store_detail.last_verify = {"hash": diff_hash(DIFF), "passed": True}
    store.put(store_detail)
    sandbox.error = PatchError("diff does not apply: error: patch failed" + " x" * 2000)
    broker.events.clear()
    res = _verify(client)
    assert res.status_code == 422 and "patch failed" in res.json()["detail"]
    step = [d for e, d in broker.events if e == "step"][0]
    assert step["outcome"] == "error" and len(step["summary"]) <= 300
    assert store.get("inc_01").last_verify == {"hash": diff_hash(DIFF), "passed": False}
    assert _audit(db)[-1]["outcome"] == "error"


def test_reproduce_takes_guild_session_id_from_the_body(env):
    client, _, _, _, db = env
    res = _reproduce(client, guild_session_id="gs_body")
    assert res.status_code == 200
    got = _audit(db)[0]
    assert got["guild_session_id"] == "gs_body"
    assert got["on_behalf_of"] == "rootlane-agent (Guild session gs_body)"

import pytest
from fastapi.testclient import TestClient

import rootlane_toolbox.api.app as appmod
from rootlane_toolbox.api import deps
from rootlane_toolbox.api.app import create_app
from rootlane_toolbox.core.broker import Broker
from rootlane_toolbox.core.config import Settings
from rootlane_toolbox.core.guards import GuardError
from tests.conftest import FakeDB

ORIGIN = "https://app.rootlane.xyz"


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(appmod, "_build_clients", lambda s: (FakeDB(), FakeDB()))
    settings = Settings(ingest_token="ing", admin_token="adm")
    return TestClient(create_app(settings))


def test_healthz(client):
    r = client.get("/healthz")
    assert r.status_code == 200 and r.json() == {"ok": True}


def test_routers_are_mounted_with_auth_active(client):
    assert client.get("/api/incidents/none").status_code == 404
    assert client.post("/internal/events", json={"events": []}).status_code == 401
    assert client.post("/api/incidents/x/approve", json={"approver": "a"}).status_code == 401
    assert "/api/stream" in client.get("/openapi.json").json()["paths"]


def test_state_wires_the_shared_broker_into_the_store(client):
    assert isinstance(deps.state.broker, Broker)
    assert deps.state.store._broker is deps.state.broker


def test_cors_preflight_allows_the_configured_origin(client):
    r = client.options(
        "/api/overview",
        headers={
            "Origin": ORIGIN,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "Content-Type, X-Admin-Token",
        },
    )
    assert r.status_code == 200
    assert r.headers["access-control-allow-origin"] == ORIGIN
    allowed = r.headers["access-control-allow-headers"].lower()
    assert "x-admin-token" in allowed and "content-type" in allowed


def test_cors_does_not_allow_other_origins(client):
    r = client.get("/healthz", headers={"Origin": "https://evil.example"})
    assert "access-control-allow-origin" not in r.headers


def test_tools_router_is_mounted_and_guard_errors_are_400(monkeypatch):
    monkeypatch.setattr(appmod, "_build_clients", lambda s: (FakeDB(), FakeDB()))
    app_client = TestClient(create_app(Settings(toolbox_api_key="k")))
    assert app_client.post("/tools/read_source", json={"path": "a"}).status_code == 401
    res = app_client.post("/tools/read_source", json={"path": "../x"}, headers={"X-API-Key": "k"})
    assert res.status_code == 400


def test_no_static_mount(client):
    assert client.get("/").status_code == 404


def test_guard_error_becomes_400(client):
    def boom():
        raise GuardError("not allowed")

    client.app.add_api_route("/_boom", boom)
    r = client.get("/_boom")
    assert r.status_code == 400 and r.json() == {"detail": "not allowed"}

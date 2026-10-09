import pytest
from fastapi import Depends
from fastapi.testclient import TestClient

import rootlane_toolbox.app as appmod
import rootlane_toolbox.db as dbmod
from rootlane_toolbox.config import Settings
from rootlane_toolbox.db import LazyClient, ReadOnlyUnavailable
from rootlane_toolbox.deps import get_ro_db
from tests.conftest import FakeDB


@pytest.mark.parametrize("read_only", [False, True])
def test_clients_are_built_without_auto_session_ids(monkeypatch, read_only):
    captured = {}
    monkeypatch.setattr(dbmod.clickhouse_connect, "get_client", lambda **kw: captured.update(kw))
    dbmod.clickhouse_client(Settings(clickhouse_host="h"), read_only=read_only)
    assert captured["autogenerate_session_id"] is False


def test_lazy_client_builds_on_first_use_only():
    built = []

    def factory():
        built.append(1)
        return FakeDB()

    lazy = LazyClient(factory)
    assert built == []
    lazy.query("SELECT 1")
    lazy.query("SELECT 2")
    assert built == [1]


def test_lazy_client_failure_is_reported_as_unavailable_and_retried():
    attempts = []

    def factory():
        attempts.append(1)
        raise RuntimeError("no such user")

    lazy = LazyClient(factory)
    for _ in range(2):
        with pytest.raises(ReadOnlyUnavailable):
            lazy.query("SELECT 1")
    assert len(attempts) == 2


def test_app_starts_without_the_read_only_user_and_answers_503_on_use(monkeypatch):
    def fake_client(settings, *, read_only=False):
        if read_only:
            raise RuntimeError("Authentication failed")
        return FakeDB()

    monkeypatch.setattr(appmod, "clickhouse_client", fake_client)
    app = appmod.create_app(Settings(ingest_token="ing", admin_token="adm"))

    @app.get("/_ro")
    def use_ro(ro=Depends(get_ro_db)):
        return ro.query("SELECT 1")

    client = TestClient(app)
    assert client.get("/healthz").status_code == 200
    assert client.get("/api/incidents/none").status_code == 404
    r = client.get("/_ro")
    assert r.status_code == 503 and "read-only" in r.json()["detail"]

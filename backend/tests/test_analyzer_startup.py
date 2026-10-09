import threading

from fastapi.testclient import TestClient

import rootlane_toolbox.app as appmod
from rootlane_toolbox import deps
from rootlane_toolbox.app import create_app
from rootlane_toolbox.config import Settings
from tests.conftest import FakeDB


def _started(monkeypatch, settings):
    ran = threading.Event()
    captured = {}

    def fake_run(self):
        captured["analyzer"] = self
        ran.set()

    monkeypatch.setattr(appmod, "_build_clients", lambda s: (FakeDB(), FakeDB()))
    monkeypatch.setattr(appmod, "_build_analyzer_client", lambda s: FakeDB())
    monkeypatch.setattr(appmod.Analyzer, "run_forever", fake_run)
    with TestClient(create_app(settings)):
        return ran.wait(timeout=2), captured.get("analyzer")


def test_analyzer_starts_on_startup_when_triage_key_is_set(monkeypatch):
    started, _ = _started(monkeypatch, Settings(triage_api_key="k"))
    assert started is True


def test_analyzer_stays_off_without_triage_key(monkeypatch):
    started, _ = _started(monkeypatch, Settings())
    assert started is False


def test_analyzer_uses_its_own_database_client(monkeypatch):
    _, analyzer = _started(monkeypatch, Settings(triage_api_key="k"))
    assert analyzer._db is not deps.state.db
    assert analyzer._store._client is analyzer._db

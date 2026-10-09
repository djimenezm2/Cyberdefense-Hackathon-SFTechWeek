import threading

from fastapi.testclient import TestClient

import rootlane_toolbox.app as appmod
from rootlane_toolbox.app import create_app
from rootlane_toolbox.config import Settings
from tests.conftest import FakeDB


def _started(monkeypatch, settings) -> bool:
    ran = threading.Event()
    monkeypatch.setattr(appmod, "_build_clients", lambda s: (FakeDB(), FakeDB()))
    monkeypatch.setattr(appmod.Analyzer, "run_forever", lambda self: ran.set())
    with TestClient(create_app(settings)):
        return ran.wait(timeout=2)


def test_analyzer_starts_on_startup_when_triage_key_is_set(monkeypatch):
    assert _started(monkeypatch, Settings(triage_api_key="k")) is True


def test_analyzer_stays_off_without_triage_key(monkeypatch):
    assert _started(monkeypatch, Settings()) is False

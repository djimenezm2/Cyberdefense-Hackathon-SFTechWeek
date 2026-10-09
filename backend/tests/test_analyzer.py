from datetime import datetime, timezone

import pytest

from rootlane_toolbox.analyzer import Analyzer
from rootlane_toolbox.config import Settings
from rootlane_toolbox.store import IncidentStore
from tests.conftest import FakeDB

NOW = datetime(2026, 10, 9, 21, 0, 40, tzinfo=timezone.utc)


class StubDecider:
    def __init__(self, verdict):
        self._v = verdict
        self.calls = 0

    def decide(self, features):
        self.calls += 1
        return {"verdict": self._v, "rationale": "r", "model": "akashml/glm"}


class BoomDecider:
    def decide(self, features):
        raise RuntimeError("model down")


class SpyGuild:
    def __init__(self, sid):
        self._sid = sid
        self.calls = []

    def start_session(self, incident):
        self.calls.append(incident["id"])
        return self._sid


class SpyBroker:
    def __init__(self):
        self.published = []

    def publish(self, event, data):
        self.published.append((event, data))


BUSY = {
    "GROUP BY principal_id": [["22", 10, 0, 1, 3, 1]],
    "GROUP BY ip": [["1.2.3.4", 10, 0, 0, 1, 3, 0]],
}


def _analyzer(verdict, guild_sid, responses=BUSY, decider=None):
    db = FakeDB(responses=responses)
    broker = SpyBroker()
    store = IncidentStore(db, broker=broker)
    decider = decider or StubDecider(verdict)
    a = Analyzer(Settings(), db, store, decider, SpyGuild(guild_sid), broker)
    return a, db, broker, decider


def test_verdict_is_stored_and_published():
    a, db, broker, _ = _analyzer("watch", None)
    a.run_once(now=NOW)
    assert db.inserted["analyzer_windows"][0][2] == "watch"
    assert broker.published[0][0] == "verdict"
    assert broker.published[0][1]["rationale"] == "r"
    assert "incidents" not in db.inserted


def test_window_bounds_are_stored_as_datetimes():
    a, db, _, _ = _analyzer("watch", None)
    a.run_once(now=NOW)
    start, end = db.inserted["analyzer_windows"][0][:2]
    assert end == NOW and (end - start).total_seconds() == 10


def test_escalate_opens_incident_and_starts_guild():
    a, db, broker, _ = _analyzer("escalate", "gs_test")
    a.run_once(now=NOW)
    assert db.inserted["incidents"]
    assert len(a.guild.calls) == 1
    assert '"guild_session_id":"gs_test"' in db.inserted["incidents"][0][-1]
    assert "incident_update" in [e for e, _ in broker.published]


def test_escalate_opens_incident_even_when_guild_unavailable():
    a, db, _, _ = _analyzer("escalate", None)
    a.run_once(now=NOW)
    doc = db.inserted["incidents"][0][-1]
    assert '"guild_session_id":null' in doc
    assert "Guild session not started" in doc


def test_incident_ids_are_unique_across_windows():
    a, db, _, _ = _analyzer("escalate", None)
    a.run_once(now=NOW)
    a.run_once(now=datetime(2026, 10, 9, 21, 0, 50, tzinfo=timezone.utc))
    ids = [row[0] for row in db.inserted["incidents"]]
    assert len(set(ids)) == 2


def test_empty_window_is_ignored_without_calling_the_decider():
    a, db, _, decider = _analyzer("escalate", None, responses={})
    a.run_once(now=NOW)
    assert decider.calls == 0
    assert db.inserted["analyzer_windows"][0][2] == "ignore"


def test_tick_swallows_a_failing_cycle_while_run_once_raises():
    a, db, _, _ = _analyzer("x", None, decider=BoomDecider())
    with pytest.raises(RuntimeError):
        a.run_once(now=NOW)
    a.tick(now=NOW)
    assert "analyzer_windows" not in db.inserted
